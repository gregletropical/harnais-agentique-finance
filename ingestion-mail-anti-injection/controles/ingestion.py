"""Ingestion d'un mail depuis un fichier `.eml` (barrières 1, 2 et 3).

Dans le système réel, les messages viennent d'une archive locale (export mbox ou
PST) ou d'un relevé d'API fait par un profil lecture seule. Ce dépôt ne contient
aucun connecteur : la seule source est un fichier `.eml` d'exemple, lu en octets.
L'interface est la même — des octets MIME en entrée, un `Message` inerte en sortie.

Garanties :
- barrière 1 : aucune requête réseau. Aucun import réseau dans ce module ;
  la recette le vérifie par analyse AST et sous sentinelle `socket.connect` ;
- barrière 2 : aucun rendu. Le HTML passe par `html_vers_texte`, le texte brut
  reste une chaîne ;
- barrière 3 : aucune pièce jointe ouverte. On garde le nom, le type DÉCLARÉ, la
  taille et l'empreinte SHA-256 ; les octets restent en mémoire, jamais écrits
  sur disque, jamais décompressés, jamais interprétés. Le nom de fichier n'est
  JAMAIS utilisé comme chemin. L'éventuelle extraction de texte est une étape
  séparée, conditionnelle et contrôlée (`pieces_jointes.py`).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path

from .html_texte import html_vers_texte


@dataclass(frozen=True)
class PieceJointe:
    nom: str
    type_declare: str
    taille: int
    sha256: str
    octets: bytes = field(repr=False, compare=False)


@dataclass(frozen=True)
class Message:
    fichier: str
    message_id: str
    adresse_expediteur: str
    nom_affiche: str
    domaine: str
    sujet: str
    date: str
    entetes: dict = field(repr=False, compare=False)   # nom en minuscules -> liste de valeurs
    corps_texte: str = field(repr=False)
    a_html: bool = False
    pieces: tuple = ()


def _entetes(msg) -> dict:
    """En-têtes décodés (RFC 2047) et dépliés, dans l'ordre du message (le plus haut d'abord)."""
    out: dict[str, list[str]] = {}
    for k, v in msg.items():
        try:
            valeur = str(v)
        except Exception:
            valeur = ""
        out.setdefault(k.lower(), []).append(" ".join(valeur.split()))
    return out


def analyser(brut: bytes, fichier: str = "") -> Message:
    """Octets MIME -> Message. Fonction pure : ni réseau, ni disque."""
    msg = BytesParser(policy=policy.default).parsebytes(brut)
    try:
        nom, adresse = (getaddresses([str(msg.get("From", ""))]) or [("", "")])[0]
    except Exception:
        nom, adresse = "", ""
    adresse = adresse.strip().lower()
    domaine = adresse.rsplit("@", 1)[-1] if "@" in adresse else ""

    texte = html = None
    pieces: list[PieceJointe] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        dispo = part.get_content_disposition()
        ctype = part.get_content_type()
        if dispo == "attachment" or (part.get_filename() and dispo != "inline"):
            octets = part.get_payload(decode=True) or b""
            pieces.append(PieceJointe(nom=str(part.get_filename() or ""), type_declare=ctype,
                                      taille=len(octets), sha256=hashlib.sha256(octets).hexdigest(),
                                      octets=octets))
        elif ctype == "text/plain" and texte is None:
            texte = part.get_content()
        elif ctype == "text/html" and html is None:
            html = part.get_content()

    corps = texte if texte else html_vers_texte(html or "")
    return Message(
        fichier=fichier,
        message_id=str(msg.get("Message-ID", "")).strip(),
        adresse_expediteur=adresse,
        nom_affiche=nom,
        domaine=domaine,
        sujet=str(msg.get("Subject", "")),
        date=str(msg.get("Date", "")),
        entetes=_entetes(msg),
        corps_texte=corps or "",
        a_html=html is not None,
        pieces=tuple(pieces),
    )


def lire_eml(chemin: Path) -> Message:
    """Seul accès disque de l'ingestion : lire les octets d'un fichier d'exemple."""
    chemin = Path(chemin)
    return analyser(chemin.read_bytes(), chemin.name)

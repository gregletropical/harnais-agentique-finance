"""Extraction contrôlée du TEXTE d'une pièce jointe (règle 6 du §5 bis).

Une pièce jointe ne s'ouvre jamais dans la session de l'agent. Ici, on n'« ouvre »
rien : on décide d'abord si l'extraction est permise, puis on ne traite que des
formats texte, vérifiés sur leur type RÉEL (signature des octets) et non sur leur
extension ni sur le type déclaré par l'expéditeur.

Conditions cumulatives pour extraire :
1. l'expéditeur est authentifié et en relation (`signaux.confiance`) ;
2. son domaine figure dans les domaines autorisés pour les pièces jointes
   (un domaine nouveau se présente à l'humain AVANT toute extraction) ;
3. le format est attendu (`.txt`, `.csv`) ET les octets sont bien du texte :
   une archive ZIP, un exécutable ou un PDF déguisés en `.txt` sont refusés ;
4. la taille est bornée.

Le texte extrait part au LECTEUR, dans le bloc délimité — jamais à l'orchestrateur.

Dans le système réel, les formats bureautiques (PDF, tableur, traitement de texte)
sont extraits par des outils en ligne de commande dans un répertoire temporaire
vide, par un interpréteur isolé, sans réseau. Ce dépôt se limite aux formats
texte pour rester en bibliothèque standard.
"""
from __future__ import annotations

from pathlib import PurePosixPath

FORMATS_ATTENDUS = (".txt", ".csv")
TAILLE_MAX_FICHIER = 2_000_000
TAILLE_MAX_TEXTE = 30_000

SIGNATURES_REFUSEES = {
    b"PK\x03\x04": "archive_zip",          # aussi docx, xlsx : jamais sous une extension texte
    b"%PDF": "pdf",
    b"MZ": "executable_windows",
    b"\x7fELF": "executable_elf",
    b"\xd0\xcf\x11\xe0": "ole_bureautique",  # anciens formats bureautiques, macros possibles
    b"Rar!": "archive_rar",
    b"\x1f\x8b": "archive_gzip",
}

MOTIFS = ("expediteur_non_authentifie", "domaine_non_autorise", "domaine_nouveau_a_presenter",
          "format_non_attendu", "type_reel_different", "trop_volumineux", "non_texte")


def domaine_nouveau(domaine: str, conf: dict) -> bool:
    """Domaine jamais présenté à l'humain : la passe le présente avant toute extraction."""
    return domaine not in conf.get("pj_domaines_autorises", []) and domaine not in conf.get("pj_domaines_refuses", [])


def type_reel_deguise(nom: str, octets: bytes) -> bool:
    """Vrai si les octets trahissent un format différent de l'extension annoncée (ZIP sous `.txt`, exécutable sous `.pdf`...)."""
    extension = PurePosixPath(nom.replace("\\", "/")).suffix.lower()
    attendu = {".pdf": b"%PDF", ".zip": b"PK\x03\x04", ".docx": b"PK\x03\x04", ".xlsx": b"PK\x03\x04"}.get(extension)
    for sig in SIGNATURES_REFUSEES:
        if octets.startswith(sig) and sig != attendu:
            return True
    return extension == ".pdf" and not octets.startswith(b"%PDF")


def decider_extraction(nom: str, octets: bytes, domaine: str, confiance: bool, conf: dict) -> tuple[bool, str]:
    """(extraction permise, motif). Le nom n'est lu que pour son extension, jamais comme chemin."""
    if not confiance:
        return False, "expediteur_non_authentifie"
    if domaine_nouveau(domaine, conf):
        return False, "domaine_nouveau_a_presenter"
    if domaine not in conf.get("pj_domaines_autorises", []):
        return False, "domaine_non_autorise"
    extension = PurePosixPath(nom.replace("\\", "/")).suffix.lower()
    if extension not in FORMATS_ATTENDUS:
        return False, "format_non_attendu"
    if len(octets) > TAILLE_MAX_FICHIER:
        return False, "trop_volumineux"
    if type_reel_deguise(nom, octets) or any(octets.startswith(sig) for sig in SIGNATURES_REFUSEES):
        return False, "type_reel_different"
    if b"\x00" in octets[:4096]:
        return False, "non_texte"
    return True, "ok"


def extraire_texte(nom: str, octets: bytes, domaine: str, confiance: bool, conf: dict) -> str:
    """Texte brut d'une pièce jointe, ou « [non extrait : motif] » (motif fermé)."""
    permis, motif = decider_extraction(nom, octets, domaine, confiance, conf)
    if not permis:
        return f"[non extrait : {motif}]"
    return octets.decode("utf-8", "replace")[:TAILLE_MAX_TEXTE]

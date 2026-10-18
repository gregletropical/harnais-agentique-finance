"""Moteur de règles du tri du flux, sur MÉTADONNÉES seules (jamais le corps).

Entrée : les en-têtes d'un message et ses `Signaux`. Sortie : une classe et une
action, chacune dans une liste fermée, plus l'identifiant de la règle qui les a
produites — c'est cet identifiant qui permet de mesurer chaque règle contre les
corrections de l'humain (boucle d'apprentissage).

Sémantique : règles évaluées dans l'ordre du fichier ; la classe vient de la
première règle qui en fixe une, l'action de la première règle qui en fixe une.

Niveaux : `observee` (comptée, sans effet), `proposee` (pose un libellé
`IA/...` que l'humain voit et corrige), `automatique` (geste sans validation).
**Le schéma refuse toute règle `automatique` qui n'exige pas DMARC `pass` ET un
expéditeur connu** : un fichier de règles mal formé est refusé en entier.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

FICHIER_REGLES = Path(__file__).resolve().parents[1] / "regles" / "regles_tri.json"

CLASSES = ("Clients", "Administratif", "Fournisseurs", "Projets",
           "Personnel", "Newsletters", "Notifications", "Non-classe")
ACTIONS = ("suspect", "a_traiter", "archivable", "a_trier")
NIVEAUX = ("observee", "proposee", "automatique")
CONDITIONS = ("dmarc", "expediteur_connu", "liste_diffusion", "expediteur_noreply", "domaine")

RE_NOREPLY = re.compile(r"^(no[-_.]?reply|ne[-_.]?pas[-_.]?repondre|donotreply|notifications?|mailer-daemon|bounce)", re.I)


@dataclass(frozen=True)
class Faits:
    """Ce que le moteur sait d'un message — rien d'autre n'y entre."""
    adresse: str
    domaine: str
    dmarc: str
    liste_diffusion: bool
    expediteur_connu: bool

    @property
    def expediteur_noreply(self) -> bool:
        return bool(RE_NOREPLY.match(self.adresse.split("@")[0]))


@dataclass(frozen=True)
class Decision:
    classe: str
    regle_classe: str
    action: str
    regle_action: str


def faits(message, signaux) -> Faits:
    e = message.entetes
    liste = bool(e.get("list-unsubscribe") or e.get("list-id")
                 or any(v.strip().lower() in ("bulk", "list") for v in e.get("precedence", [])))
    return Faits(message.adresse_expediteur, signaux.domaine, signaux.dmarc, liste, signaux.connu)


def _domaine_correspond(domaine: str, cible: str) -> bool:
    return domaine == cible or domaine.endswith("." + cible)


def _vrai(si: dict, f: Faits) -> bool:
    for cle, attendu in si.items():
        if cle == "dmarc":
            if f.dmarc not in (attendu if isinstance(attendu, list) else [attendu]):
                return False
        elif cle == "domaine":
            cibles = attendu if isinstance(attendu, list) else [attendu]
            if not any(_domaine_correspond(f.domaine, c) for c in cibles):
                return False
        elif getattr(f, cle) != attendu:
            return False
    return True


def valider(doc: dict) -> None:
    """Schéma fermé : un fichier de règles mal formé est refusé en entier."""
    ids = set()
    for r in doc["regles"]:
        if r["id"] in ids:
            raise ValueError(f"id de règle en double : {r['id']}")
        ids.add(r["id"])
        if r.get("niveau") not in NIVEAUX:
            raise ValueError(f"{r['id']} : niveau invalide {r.get('niveau')!r}")
        if set(r["si"]) - set(CONDITIONS):
            raise ValueError(f"{r['id']} : condition inconnue {sorted(set(r['si']) - set(CONDITIONS))}")
        if r["niveau"] == "automatique":
            if r["si"].get("dmarc") != "pass" or r["si"].get("expediteur_connu") is not True:
                raise ValueError(f"{r['id']} : automatique exige dmarc: pass et expediteur_connu: true")
        alors = r["alors"]
        if not alors or set(alors) - {"classe", "action"}:
            raise ValueError(f"{r['id']} : `alors` invalide")
        if "classe" in alors and alors["classe"] not in CLASSES:
            raise ValueError(f"{r['id']} : classe hors taxonomie {alors['classe']!r}")
        if "action" in alors and alors["action"] not in ACTIONS:
            raise ValueError(f"{r['id']} : action hors liste {alors['action']!r}")


def charger(chemin: Path = FICHIER_REGLES) -> dict:
    doc = json.loads(Path(chemin).read_text(encoding="utf-8"))
    valider(doc)
    return doc


def decider(doc: dict, f: Faits) -> Decision:
    classe = action = None
    rc = ra = "defaut"
    for r in doc["regles"]:
        if r["niveau"] == "observee" or not _vrai(r["si"], f):
            continue
        if classe is None and "classe" in r["alors"]:
            classe, rc = r["alors"]["classe"], r["id"]
        if action is None and "action" in r["alors"]:
            action, ra = r["alors"]["action"], r["id"]
        if classe and action:
            break
    return Decision(classe or "Non-classe", rc, action or "a_trier", ra)

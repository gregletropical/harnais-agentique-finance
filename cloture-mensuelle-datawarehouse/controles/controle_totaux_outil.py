"""Contrôle `cutoff contre totaux de l'outil` et son registre d'exceptions.

Le cutoff de chaque projet est reconstitué depuis l'outil de gestion de projets (CA produit, coût
produit). L'outil publie aussi ses propres totaux par entité et période. Le contrôle compare les deux,
par entité, à 1 EUR près (l'outil arrondit ses totaux à l'euro).

Certains écarts sont connus et ne se codent pas en règle (l'outil ne compte pas toujours certaines lignes
que la formule reconstitue, par exemple une revalorisation de change sur un projet en devise). Ils ne se
forcent pas non plus : sur décision humaine, ils reçoivent DEUX lignes — un ajustement du cutoff qui les
neutralise, et une exception motivée au registre `regles/exceptions_totaux_outil.csv`.

Règle de jugement (pure) :
- sans exception : OK si |écart| <= tolérance, sinon KO ;
- avec exceptions pour ce mois et cette entité (marge seulement) : le résiduel = écart - somme des
  exceptions doit tenir dans la tolérance (statut EXPLIQUE), sinon KO — y compris quand l'écart brut est
  nul : une exception que l'outil compte désormais est périmée, le registre mentirait.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from controles import commun as C

COLONNES_EXCEPTIONS = ["periode", "entite", "id_projet", "ecart_mb", "cause", "date"]


def valider_exceptions(lignes: list[dict], entites: set[str] | None = None) -> list[dict]:
    """Refuse un registre mal formé : on ne juge pas avec un registre douteux."""
    vues = set()
    for i, r in enumerate(lignes, start=2):
        if not re.fullmatch(r"\d{4}-\d{2}", r.get("periode", "")):
            raise ValueError(f"exceptions ligne {i} : période invalide {r.get('periode')!r}")
        if entites is not None and r.get("entite") not in entites:
            raise ValueError(f"exceptions ligne {i} : entité inconnue {r.get('entite')!r}")
        if not (r.get("ecart_mb") or "").strip():
            raise ValueError(f"exceptions ligne {i} : montant obligatoire")
        if not (r.get("cause") or "").strip():
            raise ValueError(f"exceptions ligne {i} : cause vide")
        cle = (r["periode"], r["entite"], r["id_projet"])
        if cle in vues:
            raise ValueError(f"exceptions ligne {i} : doublon {cle}")
        vues.add(cle)
    return lignes


def juger(lignes: list[dict], exceptions: list[dict], tolerance: float = 1.0) -> list[dict]:
    """`lignes` : {periode, entite, mesure ('CA produit' | 'MB produite'), ecart}. Renvoie les lignes jugées."""
    exc, projets = {}, {}
    for e in exceptions:
        k = (e["periode"], e["entite"])
        exc[k] = round(exc.get(k, 0.0) + float(e["ecart_mb"]), 2)
        projets.setdefault(k, []).append(e["id_projet"])
    out = []
    for l in lignes:
        k = (l["periode"], l["entite"])
        x = exc.get(k, 0.0) if l["mesure"] == "MB produite" else 0.0
        residuel = round(l["ecart"] - x, 2)
        statut = "KO" if abs(residuel) > tolerance else ("EXPLIQUE" if x else "OK")
        out.append({**l, "exceptions": x, "residuel": residuel, "statut": statut,
                    "projets_exceptions": ",".join(projets.get(k, [])) if x else ""})
    return out


def controle_totaux_outil(conn: sqlite3.Connection, periode: str, regles: Path = C.REGLES) -> C.Resultat:
    tol = C.parametres(regles)["tolerance_cutoff_entite_periode_eur"]
    lignes = []
    for entite, ca, mb, ca_outil, mb_outil in conn.execute(
            """SELECT t.entite, COALESCE(SUM(c.ca), 0), COALESCE(SUM(c.ca - c.cout), 0), t.ca_produit, t.mb_produite
               FROM raw_totaux_outil t LEFT JOIN raw_cutoff c ON c.periode = t.periode AND c.entite = t.entite
               WHERE t.periode = ? GROUP BY t.entite, t.ca_produit, t.mb_produite ORDER BY t.entite""", (periode,)):
        lignes.append({"periode": periode, "entite": entite, "mesure": "CA produit", "ecart": round(ca - ca_outil, 2)})
        lignes.append({"periode": periode, "entite": entite, "mesure": "MB produite", "ecart": round(mb - mb_outil, 2)})
    if not lignes:
        return C.Resultat("cutoff contre totaux de l'outil", False, f"aucun total de l'outil pour {periode}")
    entites = {r[0] for r in conn.execute("SELECT DISTINCT entite FROM raw_projets")}
    exc = [e for e in valider_exceptions(C.regle("exceptions_totaux_outil.csv", regles), entites) if e["periode"] == periode]
    jugees = juger(lignes, exc, tol)
    ko = [j for j in jugees if j["statut"] == "KO"]
    details = [f"{j['entite']} {j['mesure']} : écart {C.eur(j['ecart'], signe=True)}, exceptions {C.eur(j['exceptions'], signe=True)}, "
               f"résiduel {C.eur(j['residuel'], signe=True)} -> {j['statut']}" for j in jugees]
    expl = sum(j["statut"] == "EXPLIQUE" for j in jugees)
    msg = (f"{len(ko)} écart(s) hors tolérance après exceptions" if ko
           else f"conforme ({expl} écart(s) expliqué(s) au registre)")
    return C.Resultat("cutoff contre totaux de l'outil", not ko, msg, details=details)

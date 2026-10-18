"""Cadrage en valeur du livre de paie contre le journal de paie de la comptabilité, et son registre.

Le contrôle ne rapporte pas « 0 écart au-dessus du seuil » mais « 0 écart NON EXPLIQUÉ ». Il n'y a pas
de seuil de matérialité sur un écart de réconciliation : un écart d'un centime toléré aujourd'hui devient
un écart dont plus personne ne connaît l'origine. Un écart connu porte sa cause, sa référence et sa
résolution attendue dans `regles/registre_exceptions_cadrage.csv` ; il reste affiché, jamais masqué.

Obsolescence : une ligne `ouvert` dont le compte n'est plus en anomalie est annoncée en information ; le
registre n'est jamais réécrit automatiquement (repasser à `resolu` reste un geste humain).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from controles import commun as C
from controles.pipeline import executer_sql

COLONNES = ["compte", "motif", "reference", "statut", "date_detection", "date_resolution"]
STATUTS_VALIDES = {"ouvert", "resolu"}
STATUTS_ANOMALIE = {"ecart", "absent_livre", "absent_pa"}


@dataclass
class Verdict:
    expliques: list[tuple]          # (compte, livre, pa, ecart, statut, motif, reference)
    non_expliques: list[tuple]      # (compte, livre, pa, ecart, statut)
    a_repasser_resolu: list[str]    # comptes du registre dont l'écart a disparu


def valider_registre(lignes: list[dict]) -> list[dict]:
    for i, r in enumerate(lignes, start=2):
        manquantes = [c for c in COLONNES if c not in r]
        if manquantes:
            raise ValueError(f"registre d'exceptions : colonne(s) manquante(s) {manquantes}")
        if r["statut"] not in STATUTS_VALIDES:
            raise ValueError(f"registre d'exceptions ligne {i} : statut invalide {r['statut']!r}")
    return lignes


def evaluer(lignes: list[tuple], registre: list[dict]) -> Verdict:
    """`lignes` : (compte, livre_solde, pa_solde, ecart, statut) de ctrl_cadrage_paie. Pur."""
    ouvert = {r["compte"].strip(): (r["motif"], r["reference"]) for r in registre if r["statut"] == "ouvert"}
    expliques, non_expliques, en_anomalie = [], [], set()
    for compte, livre, pa, ecart, statut in lignes:
        if statut not in STATUTS_ANOMALIE:
            continue
        c = str(compte).strip()
        en_anomalie.add(c)
        if c in ouvert:
            expliques.append((compte, livre, pa, ecart, statut, *ouvert[c]))
        else:
            non_expliques.append((compte, livre, pa, ecart, statut))
    return Verdict(expliques, non_expliques, [c for c in ouvert if c not in en_anomalie])


def executer(conn: sqlite3.Connection, mois: str, prm: dict, regles: Path = C.REGLES) -> list[C.Resultat]:
    executer_sql(conn, "ctrl_cadrage_paie.sql", {"journal": prm["comptes"]["journal_paie"], "seuil": prm["tolerance_paie_eur"]})
    lignes = conn.execute("SELECT compte, livre_solde, pa_solde, ecart, statut FROM ctrl_cadrage_paie ORDER BY compte").fetchall()
    v = evaluer(lignes, valider_registre(C.regle("registre_exceptions_cadrage.csv", regles)))
    det = [f"expliqué {c} | écart {C.eur(e, signe=True)} | {s} | réf {ref} | {motif}" for c, l, p, e, s, motif, ref in v.expliques]
    det += [f"NON EXPLIQUÉ {c} | livre {C.eur(l)} | journal {C.eur(p)} | écart {C.eur(e, signe=True)} | {s}" for c, l, p, e, s in v.non_expliques]
    det += [f"[INFO] compte {c} n'est plus en écart : ligne à repasser `resolu` dans le registre" for c in v.a_repasser_resolu]
    msg = (f"{len(v.non_expliques)} écart(s) NON expliqué(s) - tolérance zéro" if v.non_expliques
           else f"0 écart non expliqué ({len(v.expliques)} expliqué(s) au registre)")
    return [C.Resultat("cadrage paie livre x journal", not v.non_expliques, msg, details=det)]

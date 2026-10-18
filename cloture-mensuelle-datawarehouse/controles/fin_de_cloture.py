"""Contrôles du mois, puis contrôle de fin de clôture : la porte avant toute diffusion.

Après le pipeline de P. Lecture seule, aucun appel extérieur. La fin de clôture ÉCHOUE si :

1. la date de clôture du modèle n'est pas le dernier jour de P (un extrait lancé sur le mauvais mois fait
   avancer la date de clôture et tout le prévisionnel sans autre erreur) ;
2. le mart de paie ne couvre pas P ;
3. le cadrage en valeur livre de paie x journal de paie porte un écart non expliqué par le registre ;
4. un projet non interne avec production sur P n'a pas de groupe client, ou un arbitrage MDM est en
   attente ou décidé mais non appliqué ;
5. les contrôles du mois n'ont pas été calculés sur P (« mois non calculé » n'est pas un zéro), ou l'un
   de leurs contrôles bloquants est en échec (résidu d'un tableau de passage, vraisemblance) ;
6. l'oracle M-1 trouve un écart non qualifié sur un mois passé, ou l'instantané de P-1 manque.

Les constats (pièces à instruire, deals disparus, corrections périmées) ne bloquent pas : ils se
présentent à l'humain, qui franchit lui-même le jalon « données publiables ». Un échec se rapporte et
se présente ; il ne se contourne pas.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from controles import cadrage_achats, cadrage_paie, cadrage_ventes, commun as C, crm, mdm, recette, vraisemblance

COLS_SYNTHESE = [("periode", "TEXT"), ("controle", "TEXT"), ("ok", "INTEGER"), ("bloquant", "INTEGER"), ("message", "TEXT")]


# ---------------------------------------------------------------------------
# Contrôles du mois
# ---------------------------------------------------------------------------

def controles_mois(conn: sqlite3.Connection, periode: str, exemple: Path, regles: Path = C.REGLES) -> list[C.Resultat]:
    prm = C.parametres(regles)
    res = []
    res += cadrage_ventes.executer(conn, periode, prm)
    res += cadrage_achats.executer(conn, periode, prm, regles)
    res += cadrage_paie.executer(conn, periode, prm, regles)
    res += vraisemblance.executer(conn, periode, prm, regles)
    res.append(crm.controle_disparus(C.lire_source(exemple, "crm/deals_precedent.csv"), C.lire_source(exemple, "crm/deals.csv")))
    C.publier(conn, "ctrl_synthese", COLS_SYNTHESE,
              [{"periode": periode, "controle": r.nom, "ok": int(r.ok), "bloquant": int(r.bloquant), "message": r.message} for r in res])
    return res


# ---------------------------------------------------------------------------
# Contrôles de fin de clôture (chacun pur ou presque, renvoie un Resultat)
# ---------------------------------------------------------------------------

def controle_date_cloture(date_cloture: str | None, periode: str) -> C.Resultat:
    attendu = C.fin_de_mois(periode).isoformat()
    return C.Resultat("date de clôture", date_cloture == attendu, f"modèle au {date_cloture}, attendu {attendu}")


def controle_paie(max_mois: str | None, periode: str) -> C.Resultat:
    ok = max_mois is not None and max_mois >= periode
    return C.Resultat("couverture paie du modèle", ok, f"mart de paie jusqu'à {max_mois or '—'}, attendu >= {periode}")


def controle_mdm(constats: list[str]) -> C.Resultat:
    return C.Resultat("arbitrages MDM", not constats,
                      "aucun arbitrage en attente" if not constats else f"{len(constats)} arbitrage(s) en attente ou non appliqué(s)",
                      details=constats)


def controle_mois_calcule(synthese: list[tuple]) -> C.Resultat:
    """`synthese` : lignes (controle, ok, bloquant, message) de ctrl_synthese pour P."""
    if not synthese:
        return C.Resultat("contrôles du mois", False, "MOIS NON CALCULÉ : le pipeline n'a pas tourné sur P (ce n'est pas un zéro)")
    ko = [f"{c} : {m}" for c, ok, b, m in synthese if b and not ok]
    constats = sum(1 for c, ok, b, m in synthese if not b and not ok)
    return C.Resultat("contrôles du mois", not ko,
                      f"{len(ko)} contrôle(s) bloquant(s) en échec" if ko
                      else f"calculés, aucun bloquant en échec, {constats} constat(s) à présenter", details=ko)


def executer(conn: sqlite3.Connection, periode: str, exemple: Path, regles: Path = C.REGLES) -> list[C.Resultat]:
    res = [controle_date_cloture(conn.execute("SELECT date_cloture FROM stg_date_cloture").fetchone()[0], periode),
           controle_paie(conn.execute("SELECT MAX(mois) FROM mart_fct_paie_mensuel").fetchone()[0], periode)]
    lignes = conn.execute("SELECT compte, livre_solde, pa_solde, ecart, statut FROM ctrl_cadrage_paie").fetchall()
    v = cadrage_paie.evaluer(lignes, C.regle("registre_exceptions_cadrage.csv", regles))
    res.append(C.Resultat("cadrage paie en valeur", not v.non_expliques,
                          f"{len(v.non_expliques)} écart(s) non expliqué(s)" if v.non_expliques
                          else f"0 écart non expliqué, {len(v.expliques)} expliqué(s) au registre",
                          details=[f"{c} écart {C.eur(e, signe=True)} ({s})" for c, _, _, e, s in v.non_expliques]))
    res.append(mdm.controle_production_sans_groupe(conn, periode))
    res.append(controle_mdm(mdm.constats_garde(C.lire_source(exemple, "mdm/arbitrages.csv"))))
    synth = conn.execute("SELECT controle, ok, bloquant, message FROM ctrl_synthese WHERE periode = ?", (periode,)).fetchall() \
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'ctrl_synthese'").fetchone() else []
    res.append(controle_mois_calcule(synth))
    res.append(recette.comparer(conn, periode, exemple, regles))
    return res

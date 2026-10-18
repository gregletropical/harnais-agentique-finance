"""Vraisemblance de la production du mois contre l'historique.

Leçon d'une clôture réelle : un export du cutoff amputé de l'essentiel de son chiffre d'affaires a
traversé le pré-vol d'ouverture, la validation structurelle, tout le pipeline et tous les contrôles de qualité sans
déclencher un seul avertissement, parce que l'export de l'outil et ses propres totaux étaient faux
ENSEMBLE. Ce qui l'a arrêté, c'est un humain regardant un total à côté de l'historique. Le pipeline
validait la forme d'un fichier, jamais sa vraisemblance : ce contrôle fait le geste de l'humain.

Règle : pour chaque mesure (CA, marge brute), le mois P doit tenir entre `ratio_min` et `ratio_max` fois
la médiane des `mois_historique` mois précédents. Hors bornes : bloquant. Un vrai mois exceptionnel
existe (un gros contrat, un mois de congés) : il se constate et se confirme par l'humain, qui l'écrit
dans le rapport de clôture, il ne se laisse pas passer en silence.
"""
from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

from controles import commun as C


def juger(valeur: float, historique: list[float], ratio_min: float, ratio_max: float) -> tuple[bool, float | None]:
    """(ok, ratio) — pur. Sans historique, rien à juger : ok, ratio None."""
    hist = [h for h in historique if h is not None]
    if not hist:
        return True, None
    med = statistics.median(hist)
    if med == 0:
        return valeur == 0, None
    r = valeur / med
    return ratio_min <= r <= ratio_max, round(r, 3)


def executer(conn: sqlite3.Connection, mois: str, prm: dict, regles: Path = C.REGLES) -> list[C.Resultat]:
    v = prm["vraisemblance"]
    debut = C.decaler(mois, -v["mois_historique"])
    serie = {m: (ca, mb) for m, ca, mb in conn.execute(
        "SELECT mois, SUM(ca), SUM(mb) FROM mart_fct_ca_mensuel WHERE mois BETWEEN ? AND ? GROUP BY mois", (debut, mois))}
    cur = serie.get(mois, (0.0, 0.0))
    det, ok_global = [], True
    for i, mesure in enumerate(("ca", "mb")):
        if mesure not in v["mesures"]:
            continue
        hist = [serie[m][i] for m in serie if m != mois]
        ok, r = juger(cur[i], hist, v["ratio_min"], v["ratio_max"])
        ok_global &= ok
        med = statistics.median(hist) if hist else 0
        det.append(f"{mesure.upper()} {mois} = {C.eur(cur[i])} ; médiane des {len(hist)} mois précédents = {C.eur(med)} ; "
                   f"ratio {r} -> {'OK' if ok else 'HORS BORNES [' + str(v['ratio_min']) + ' ; ' + str(v['ratio_max']) + ']'}")
    return [C.Resultat("vraisemblance de la production", ok_global,
                       "dans les bornes de l'historique" if ok_global else "hors bornes : export incomplet ou mois exceptionnel à confirmer",
                       details=det)]

"""Récapitulatif métier du mois clôturé : ce que l'humain relit avant de monter la synthèse client.

Il s'imprime toujours, mais porte en tête son statut de diffusion : tant que la fin de clôture n'est pas
conforme, les chiffres sont marqués NON DIFFUSABLES. C'est le récapitulatif qui a fait voir, dans une
clôture réelle, un mois amputé de l'essentiel de son chiffre d'affaires que tous les contrôles de forme
avaient laissé passer : il met toujours le mois à côté de l'historique.
"""
from __future__ import annotations

import sqlite3
import statistics
from pathlib import Path

from controles import commun as C


def lignes(conn: sqlite3.Connection, periode: str, exemple: Path, diffusable: bool) -> list[str]:
    out = [f"RÉCAPITULATIF MÉTIER {periode} — " + ("DIFFUSABLE après GO humain" if diffusable
                                                  else "NON DIFFUSABLE (fin de clôture en échec)")]
    ca, mb = conn.execute("SELECT COALESCE(SUM(ca), 0), COALESCE(SUM(mb), 0) FROM mart_fct_ca_mensuel WHERE mois = ?",
                          (periode,)).fetchone()
    hist = [r[0] for r in conn.execute(
        "SELECT SUM(ca) FROM mart_fct_ca_mensuel WHERE mois BETWEEN ? AND ? GROUP BY mois", (C.decaler(periode, -12), C.decaler(periode, -1)))]
    med = statistics.median(hist) if hist else 0
    out.append(f"  CA produit  {C.eur(ca):>14}   (médiane des 12 mois précédents {C.eur(med)})")
    taux = f"{(mb / ca * 100) if ca else 0:.1f}".replace(".", ",")
    out.append(f"  MB produite {C.eur(mb):>14}   ({taux} %)")
    out.append("  Top groupes clients du mois :")
    for g, c, m in conn.execute("""SELECT COALESCE(f.id_groupe, '(sans groupe)'), f.ca, f.mb FROM mart_fct_ca_mensuel f
                                   WHERE f.mois = ? ORDER BY f.ca DESC LIMIT 5""", (periode,)):
        out.append(f"    {g:<16} CA {C.eur(c):>12}   MB {C.eur(m):>12}")
    snap = C.resoudre(exemple, f"snapshot/fct_ca_mensuel_{C.decaler(periode, -1)}.csv")
    connus = {r["id_groupe"] for r in C.lire_csv(snap)}
    nouveaux = [r[0] for r in conn.execute(
        "SELECT DISTINCT id_groupe FROM mart_fct_ca_mensuel WHERE mois = ? AND id_groupe IS NOT NULL ORDER BY 1", (periode,))
        if r[0] not in connus]
    out.append(f"  Nouveaux groupes clients : {', '.join(nouveaux) or 'aucun'}")
    for poste, montant in conn.execute("SELECT poste_pnl, SUM(montant) FROM mart_pnl_mensuel WHERE mois = ? GROUP BY 1 ORDER BY 1",
                                       (periode,)):
        out.append(f"  P&L comptable {poste:<28} {C.eur(montant):>12}")
    paie = conn.execute("SELECT cout_total, effectif FROM mart_fct_paie_mensuel WHERE mois = ?", (periode,)).fetchone()
    if paie:
        out.append(f"  Coût de paie {C.eur(paie[0]):>15}   (effectif {paie[1]})")
    for annee, total in conn.execute("SELECT substr(mois, 1, 4), SUM(montant) FROM mart_forecast_mensuel GROUP BY 1 ORDER BY 1"):
        out.append(f"  Prévisionnel CRM pondéré {annee} {C.eur(total):>10}")
    return out

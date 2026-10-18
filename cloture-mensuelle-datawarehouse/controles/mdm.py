"""Référentiel analytique (MDM) : garde des arbitrages et contrôle « production sans groupe client ».

Les rattachements d'un projet, d'une organisation ou d'un deal à un groupe client sont arbitrés par un
humain à chaque clôture. L'agent prépare (suggestions avec un candidat et ses voisins), l'humain décide,
un script applique la décision au référentiel versionné : l'agent ne remplit jamais la colonne
`decision` et n'écrit jamais dans le référentiel à la main.

- **Garde** (en tête du pipeline) : bloque si une ligne PRIORITAIRE (projet avec production sur le mois,
  organisation qui porte un deal ouvert) n'a pas de décision, ou si une décision est remplie mais pas
  encore appliquée — sinon le pipeline tournerait sur un référentiel qui ignore l'arbitrage. Les
  centaines de lignes « bruit » (prospects sans deal ouvert) laissées vides ne bloquent pas.
- **Production sans groupe** (en fin de clôture) : un projet non interne avec du CA ou du coût sur le
  mois et sans groupe sortirait du P&L par client sans erreur.
"""
from __future__ import annotations

import sqlite3

from controles import commun as C


class GardeMDM(RuntimeError):
    """Un arbitrage MDM est en attente ou non appliqué : le pipeline ne doit pas tourner."""


def constats_garde(arbitrages: list[dict]) -> list[str]:
    out = []
    for r in arbitrages:
        d = (r.get("decision") or "").strip()
        if r.get("prioritaire") == "1" and not d:
            out.append(f"{r['nature']} {r['cle']} ({r['libelle']}) : prioritaire sans décision")
        elif d and r.get("applique") != "1":
            out.append(f"{r['nature']} {r['cle']} : décision {d!r} prise mais non appliquée au référentiel")
    return out


def garde(arbitrages: list[dict]) -> None:
    c = constats_garde(arbitrages)
    if c:
        raise GardeMDM(f"{len(c)} arbitrage(s) MDM en attente : " + " ; ".join(c))


def controle_production_sans_groupe(conn: sqlite3.Connection, periode: str) -> C.Resultat:
    ko = conn.execute(
        """SELECT id_projet, libelle, client, ca, cout FROM stg_cutoff
           WHERE periode = ? AND interne = 0 AND id_groupe IS NULL AND (ca <> 0 OR cout <> 0) ORDER BY id_projet""",
        (periode,)).fetchall()
    det = [f"{p} {l} (client {c or '—'}) : CA {C.eur(ca)}, coût {C.eur(k)} sans groupe client" for p, l, c, ca, k in ko]
    return C.Resultat("production sans groupe client", not ko,
                      f"{len(ko)} projet(s) à arbitrer au référentiel" if ko
                      else "tout projet non interne avec production sur P a un groupe", details=det)

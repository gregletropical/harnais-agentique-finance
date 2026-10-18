"""Reconstruction de `stg_*` et `mart_*` depuis `raw_*`, dans l'ordre imposé par les dépendances.

Version réduite du pipeline réel (une vingtaine de modules en domaines : référentiels, projets et cutoff,
CRM, paie, grand livre, marts, contrôles). Les principes sont conservés :

- **un module par table produite**, idempotent (DROP puis CREATE) : rejouer le pipeline ne change rien ;
- **jamais une étape isolée** : on rejoue toujours la chaîne complète, sinon les rattachements au
  référentiel décrochent en silence (un identifiant de groupe réattribué en amont et pas en aval) ;
- **les contrôles de module sont bloquants** (compte orphelin, rubrique sans compte, dates inversées) :
  une erreur se rapporte, elle ne se contourne pas ;
- **les référentiels versionnés sont relus à chaque passage** : une décision écrite dans `regles/` est
  appliquée au pipeline suivant, sans autre étape de chargement.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from controles import commun as C
from controles import crm, mdm

SQL = Path(__file__).resolve().parent / "sql"


class ErreurModule(RuntimeError):
    """Contrôle de module en échec : le pipeline s'arrête."""


def executer_sql(conn: sqlite3.Connection, nom: str, params: dict | None = None) -> None:
    table = nom.removesuffix(".sql")
    texte = (SQL / nom).read_text(encoding="utf-8")
    with conn:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(texte, params or {})


def etape_projets(conn, periode, exemple):
    for nom in ("stg_projet.sql", "stg_cutoff.sql", "stg_date_cloture.sql"):
        executer_sql(conn, nom)


def etape_paie(conn, periode, exemple):
    executer_sql(conn, "stg_paie_livre_compte.sql")
    orph = [r[0] for r in conn.execute("SELECT DISTINCT rubrique FROM stg_paie_livre_compte WHERE compte IS NULL")]
    if orph:
        raise ErreurModule(f"rubrique(s) de paie sans compte (regles/passage_rubrique_compte.csv) : {', '.join(orph)}")


def etape_grand_livre(conn, periode, exemple):
    executer_sql(conn, "stg_gl_pnl.sql")
    orph = [r[0] for r in conn.execute("SELECT DISTINCT compte FROM stg_gl_pnl WHERE poste_pnl IS NULL ORDER BY 1")]
    if orph:
        raise ErreurModule(f"compte(s) orphelin(s) sans poste P&L (regles/taxonomie_pnl.csv) : {', '.join(orph)}")


def etape_crm(conn, periode, exemple):
    crm.controler_dates(conn)
    lignes, constats = crm.forecast(conn, periode)
    C.publier(conn, "mart_forecast_mensuel", [("mois", "TEXT"), ("id_deal", "TEXT"), ("montant", "REAL")],
              [{"mois": m, "id_deal": d, "montant": v} for m, d, v in lignes])
    return constats


def etape_marts(conn, periode, exemple):
    for nom in ("mart_fct_ca_mensuel.sql", "mart_pnl_mensuel.sql", "mart_fct_paie_mensuel.sql"):
        executer_sql(conn, nom)


def etape_garde(conn, periode, exemple):
    mdm.garde(C.lire_source(exemple, "mdm/arbitrages.csv"))


ETAPES = [
    ("garde MDM", etape_garde),
    ("projets et cutoff", etape_projets),
    ("paie", etape_paie),
    ("grand livre", etape_grand_livre),
    ("CRM et prévisionnel", etape_crm),
    ("marts", etape_marts),
]


def executer(conn: sqlite3.Connection, periode: str, exemple: Path, verbeux: bool = True) -> list[str]:
    """Joue toutes les étapes ; renvoie les constats non bloquants. Lève à la première erreur bloquante."""
    constats = []
    for nom, fn in ETAPES:
        t = time.monotonic()
        res = fn(conn, periode, exemple)
        constats += res or []
        if verbeux:
            print(f"  === {nom} : {time.monotonic() - t:.2f} s")
    return constats

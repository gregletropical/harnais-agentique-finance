"""CRM : registre d'anomalies piloté par la donnée, garde-fou du prévisionnel au grain mois, deals disparus."""
import sqlite3

import pytest

from controles import commun as C, crm
from controles.chargement import COLS_DEALS

D = {"id_deal": "D1", "titre": "t", "organisation": "o", "statut": "open", "valeur": "1000", "marge": "400",
     "probabilite": "0.5", "debut": "2026-09-01", "fin": "2026-03-31"}
R = {"id_deal": "D1", "champ": "fin", "valeur_source": "2026-03-31", "valeur_corrigee": "2027-03-31", "statut": "ouvert"}


def test_registre_applique_si_la_source_n_a_pas_bouge():
    deals, constats = crm.appliquer_registre([D], [R])
    assert deals[0]["fin"] == "2027-03-31" and not constats


def test_registre_signale_une_source_corrigee():
    deals, constats = crm.appliquer_registre([{**D, "fin": "2027-06-30"}], [R])
    assert deals[0]["fin"] == "2027-06-30" and "repasser `resolu`" in constats[0]


def test_registre_ignore_les_lignes_resolues():
    deals, constats = crm.appliquer_registre([D], [{**R, "statut": "resolu"}])
    assert deals[0]["fin"] == "2026-03-31" and not constats


def _base(deals):
    conn = sqlite3.connect(":memory:")
    C.publier(conn, "raw_deals", COLS_DEALS, deals)
    return conn


def test_dates_inversees_bloquent():
    with pytest.raises(crm.DatesInversees, match="D1"):
        crm.controler_dates(_base([D]))


def test_forecast_jamais_sur_un_mois_clos():
    conn = _base([{**D, "debut": "2026-03-15", "fin": "2026-06-30"}])
    lignes, constats = crm.forecast(conn, "2026-03")
    assert [m for m, _, _ in lignes] == ["2026-04", "2026-05", "2026-06"]
    assert round(sum(v for _, _, v in lignes), 0) == 500 and "décalé" in constats[0]


def test_deal_perdu_n_est_pas_une_disparition():
    ancien = [D, {**D, "id_deal": "D2"}]
    nouveau = [{**D, "statut": "lost"}]
    assert [d["id_deal"] for d in crm.deals_disparus(ancien, nouveau)] == ["D2"]
    assert not crm.controle_disparus(ancien, nouveau).bloquant

"""Pré-vol d'ouverture et fin de clôture : fonctions pures, hors base."""
import datetime as dt

from controles import fin_de_cloture as fc
from controles import preflight as pf


def test_mois_attendu():
    assert pf.mois_attendu(dt.date(2026, 4, 1)) == "2026-03"
    assert pf.mois_attendu(dt.date(2027, 1, 3)) == "2026-12"


def test_paie_ne_couvre_pas_le_mois():
    b = pf.Bilan()
    pf.bilan_paie([{"mois": "2026-01"}, {"mois": "2026-02"}], "2026-03", b)
    assert b.manquants and "2026-02" in b.manquants[0]


def test_paie_historique_appauvri():
    b = pf.Bilan()
    pf.bilan_paie([{"mois": "2026-03"}], "2026-03", b, mois_depot_precedent=14)
    assert not b.manquants and "effacé" in b.incoherences[0]


def test_modes_et_mois_deja_charge():
    b = pf.Bilan()
    pf.bilan_chaine("outil_projets", {"nom": "2026-04-01_0900", "periode": "2026-03"},
                    {"extrait": "2026-04-01_0900", "periode": "2026-03"}, "2026-03", b)
    pf.bilan_chaine("compta", None, None, "2026-03", b)
    pf.bilan_chaine("crm", {"nom": "x"}, None, "2026-03", b)
    assert b.modes["outil_projets"].startswith("delta") and b.modes["compta"].startswith("complet")
    assert b.modes["crm"] == "toujours complet"
    assert "déjà chargé" in b.incoherences[0]


def test_texte_verdict():
    assert pf.texte(pf.Bilan(manquants=["m"]), "2026-03", "2026-03")[-1].startswith("VERDICT : MANQUANTS")
    assert "attendre son GO" in pf.texte(pf.Bilan(), "2026-03", "2026-03")[-1]


def test_controles_de_fin_de_cloture():
    assert fc.controle_date_cloture("2026-03-31", "2026-03").ok
    assert not fc.controle_date_cloture("2026-04-30", "2026-03").ok
    assert fc.controle_paie("2026-03", "2026-03").ok
    assert not fc.controle_paie("2026-02", "2026-03").ok and not fc.controle_paie(None, "2026-03").ok
    assert fc.controle_mdm([]).ok and not fc.controle_mdm(["projet P9 : prioritaire sans décision"]).ok


def test_mois_non_calcule_n_est_pas_un_zero():
    r = fc.controle_mois_calcule([])
    assert not r.ok and "NON CALCULÉ" in r.message
    assert fc.controle_mois_calcule([("x", 0, 0, "constat")]).ok          # un constat ne bloque pas
    assert not fc.controle_mois_calcule([("x", 0, 1, "résidu")]).ok      # un bloquant si

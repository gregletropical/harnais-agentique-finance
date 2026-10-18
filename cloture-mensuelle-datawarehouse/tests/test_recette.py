"""Recette : ARRONDI, QUALIFIE (montant obligatoire), NON_QUALIFIE ; oracle M-1 et figement."""
import pytest

from controles import recette
from tests.conftest import EXEMPLES

REG = [{"mesure": "ca", "cle": "2026-02|G_*", "ecart": "-1500.00", "cause": "ajustement décidé"}]


def test_qualification():
    jug, orph = recette.qualifier([{"mesure": "ca", "cle": "2026-02|G_BETA", "ecart": -1500.01},
                                   {"mesure": "ca", "cle": "2026-01|G_BETA", "ecart": 0.01},
                                   {"mesure": "mb", "cle": "2026-02|G_BETA", "ecart": -1500.0}], REG)
    assert [j["statut"] for j in jug] == ["QUALIFIE", "ARRONDI", "NON_QUALIFIE"]
    assert orph == []


def test_le_montant_doit_correspondre():
    jug, orph = recette.qualifier([{"mesure": "ca", "cle": "2026-02|G_BETA", "ecart": -900.0}], REG)
    assert jug[0]["statut"] == "NON_QUALIFIE" and len(orph) == 1   # la ligne n'a servi à rien : signalée


def test_ligne_sans_montant_refusee():
    with pytest.raises(ValueError, match="montant obligatoire"):
        recette.valider_registre([{**REG[0], "ecart": ""}])


def test_oracle_conforme_puis_regression(base_conforme):
    assert recette.comparer(base_conforme, "2026-03", EXEMPLES / "mois_conforme").ok
    with base_conforme:   # une régression sur un mois passé, que personne n'a décidée
        base_conforme.execute("UPDATE mart_fct_ca_mensuel SET ca = ca + 10 WHERE mois = '2025-11' AND id_groupe = 'G_ALPHA'")
    r = recette.comparer(base_conforme, "2026-03", EXEMPLES / "mois_conforme")
    assert not r.ok and any("2025-11|G_ALPHA" in d and "NON_QUALIFIE" in d for d in r.details)


def test_oracle_sans_instantane_echoue(base_conforme):
    assert not recette.comparer(base_conforme, "2026-04", EXEMPLES / "mois_conforme").ok


def test_figer_refuse_un_autre_mois_et_l_ecrasement(base_conforme, tmp_path):
    with pytest.raises(RuntimeError, match="autre mois"):
        recette.figer(base_conforme, "2026-02", tmp_path)
    cible = recette.figer(base_conforme, "2026-03", tmp_path)
    assert cible.read_text(encoding="utf-8").startswith("mois,id_groupe,ca,mb")
    with pytest.raises(FileExistsError):
        recette.figer(base_conforme, "2026-03", tmp_path)

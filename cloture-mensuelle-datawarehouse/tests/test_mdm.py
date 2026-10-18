"""Garde MDM : seules les lignes prioritaires bloquent, et une décision non appliquée bloque aussi."""
import pytest

from controles import mdm


def _a(prioritaire="1", decision="", applique="0"):
    return {"nature": "projet", "cle": "P9", "libelle": "x", "prioritaire": prioritaire, "decision": decision, "applique": applique}


def test_prioritaire_sans_decision_bloque():
    with pytest.raises(mdm.GardeMDM, match="prioritaire sans décision"):
        mdm.garde([_a()])


def test_bruit_sans_decision_ne_bloque_pas():
    mdm.garde([_a(prioritaire="0")])


def test_decision_non_appliquee_bloque():
    assert "non appliquée" in mdm.constats_garde([_a(decision="creer:G9")])[0]


def test_decision_appliquee_passe():
    assert mdm.constats_garde([_a(decision="creer:G9", applique="1")]) == []


def test_production_sans_groupe(base_conforme, base_ecart):
    assert mdm.controle_production_sans_groupe(base_conforme, "2026-03").ok
    r = mdm.controle_production_sans_groupe(base_ecart, "2026-03")
    assert not r.ok and "P106" in r.details[0]

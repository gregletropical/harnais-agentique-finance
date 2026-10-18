"""Cadrage en valeur livre de paie x journal de paie : « 0 écart non expliqué », jamais « 0 écart au-dessus du seuil »."""
import pytest

from controles import cadrage_paie as CP

REG = [{"compte": "645200", "motif": "m", "reference": "r", "statut": "ouvert", "date_detection": "", "date_resolution": ""},
       {"compte": "641300", "motif": "m", "reference": "r", "statut": "resolu", "date_detection": "", "date_resolution": "x"}]


def test_ecart_explique_reste_affiche():
    v = CP.evaluer([("645200", 100.0, 60.0, 40.0, "ecart")], REG)
    assert len(v.expliques) == 1 and not v.non_expliques


def test_ecart_non_explique_meme_d_un_centime():
    v = CP.evaluer([("645100", 100.01, 100.0, 0.01, "ecart")], REG)
    assert len(v.non_expliques) == 1


def test_ligne_resolue_n_explique_plus_rien():
    assert len(CP.evaluer([("641300", 1.0, 0.0, 1.0, "absent_pa")], REG).non_expliques) == 1


def test_obsolescence_annoncee_jamais_reecrite():
    v = CP.evaluer([("645200", 1.0, 1.0, 0.0, "ok")], REG)
    assert v.a_repasser_resolu == ["645200"]


def test_classe_4_hors_perimetre_ignoree():
    assert not CP.evaluer([("421000", 0.0, -900.0, 900.0, "hors_perimetre_bilan")], REG).non_expliques


def test_registre_invalide_refuse():
    with pytest.raises(ValueError, match="statut invalide"):
        CP.valider_registre([{**REG[0], "statut": "clos"}])


def test_scenarios(base_conforme, base_ecart):
    statuts = dict(base_conforme.execute("SELECT compte, statut FROM ctrl_cadrage_paie"))
    assert statuts["645200"] == "ecart" and statuts["645210"] == "absent_livre" and statuts["421000"] == "hors_perimetre_bilan"
    ok = base_conforme.execute("SELECT ok FROM ctrl_synthese WHERE controle = 'cadrage paie livre x journal'").fetchone()[0]
    ko = base_ecart.execute("SELECT ok FROM ctrl_synthese WHERE controle = 'cadrage paie livre x journal'").fetchone()[0]
    assert (ok, ko) == (1, 0)

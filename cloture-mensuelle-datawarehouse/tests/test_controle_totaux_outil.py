"""Contrôle cutoff contre totaux de l'outil et son registre d'exceptions : une exception explique, elle ne force pas."""
import sqlite3

import pytest

from controles import chargement
from controles import controle_totaux_outil as CTO
from tests.conftest import EXEMPLES, P


def _l(ecart_mb, ecart_ca=0.0, periode="2026-03", entite="E1"):
    return [{"periode": periode, "entite": entite, "mesure": "CA produit", "ecart": ecart_ca},
            {"periode": periode, "entite": entite, "mesure": "MB produite", "ecart": ecart_mb}]


EXC = [{"periode": "2026-03", "entite": "E1", "id_projet": "P104", "ecart_mb": "12.40", "cause": "change", "date": "2026-04-01"}]


def statuts(lignes, exc):
    return [j["statut"] for j in CTO.juger(lignes, exc, 1.0)]


def test_sans_exception_ok_et_ko():
    assert statuts(_l(0.4), []) == ["OK", "OK"]
    assert statuts(_l(7.01), []) == ["OK", "KO"]


def test_exception_explique_un_ecart():
    j = CTO.juger(_l(12.42), EXC, 1.0)
    assert [x["statut"] for x in j] == ["OK", "EXPLIQUE"]
    assert j[1]["residuel"] == 0.02 and j[1]["projets_exceptions"] == "P104"


def test_exception_insuffisante_bloque():
    assert statuts(_l(20.0), EXC) == ["OK", "KO"]


def test_exception_perimee_bloque():
    """L'outil compte désormais la ligne : l'écart brut est nul, le registre mentirait."""
    assert statuts(_l(0.0), EXC) == ["OK", "KO"]


def test_exception_ne_vaut_que_pour_son_mois_son_entite_et_la_marge():
    assert statuts(_l(12.40, periode="2026-04"), EXC) == ["OK", "KO"]
    assert statuts(_l(12.40, entite="E2"), EXC) == ["OK", "KO"]
    assert statuts(_l(0.0, ecart_ca=12.40), EXC) == ["KO", "KO"]


@pytest.mark.parametrize("champ, valeur, message", [
    ("periode", "2026-3", "période"), ("entite", "INCONNUE", "entité"),
    ("ecart_mb", "", "montant obligatoire"), ("cause", " ", "cause vide")])
def test_registre_invalide_refuse(champ, valeur, message):
    with pytest.raises(ValueError, match=message):
        CTO.valider_exceptions([{**EXC[0], champ: valeur}], {"E1"})


def test_registre_doublon_refuse():
    with pytest.raises(ValueError, match="doublon"):
        CTO.valider_exceptions(EXC * 2, {"E1"})


def test_chargement_bloque_sans_l_exception(regles_copie):
    """Retirer l'exception du registre fait échouer le chargement : rien d'autre n'est chargé."""
    (regles_copie / "exceptions_totaux_outil.csv").write_text(",".join(CTO.COLONNES_EXCEPTIONS) + "\n", encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    with pytest.raises(chargement.ChargementBloque, match="hors tolérance"):
        chargement.charger(conn, EXEMPLES / "mois_conforme", P, regles_copie)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "raw_cutoff" in tables and "raw_grand_livre" not in tables

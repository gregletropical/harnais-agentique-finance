"""Bout en bout sur les exemples synthétiques : rapport du matin, puis plan d'écriture."""

import datetime as dt
import json
from pathlib import Path

import pytest

from controles import etat as etat_mod
from controles import plan_ecriture
from controles.etat import construire_etat, rapport_markdown
from controles.plan_ecriture import construire_plan
from controles.source_fichier import SourceFichier
from regles.classement import classer

EXEMPLES = Path(__file__).resolve().parents[1] / "exemples"
MAINTENANT = dt.datetime(2026, 10, 16, 7, 0, 0)

# Le classement attendu de chaque ligne du relevé fictif : c'est la spécification
# démonstrative. Toute évolution d'une règle qui le change doit être délibérée.
ATTENDU = {
    1: "A", 2: "A", 3: "A", 4: "A'1", 5: "A'2", 6: "B", 7: "N", 8: "R", 9: "I", 10: "I", 11: "I", 12: "I",
    13: "I", 14: "I", 15: "I", 16: "C", 17: "D", 18: "D", 19: "D", 20: "D", 21: "D", 22: "D", 23: "D",
    24: "D", 25: "D", 26: "E", 27: "P", 28: "D", 29: "D", 30: "I", 31: "D", 32: "D", 33: "A'1",
}


@pytest.fixture
def src():
    return SourceFichier.depuis_dossier(EXEMPLES)


@pytest.fixture
def etat(src):
    return construire_etat(src, MAINTENANT)


def test_chaque_ligne_tombe_dans_sa_classe(etat):
    obtenu = {x["id"]: x["classement"]["classe"] for x in etat["lignes"]}
    assert obtenu == ATTENDU


def test_familles(etat):
    fam = [x["classement"]["famille"] for x in etat["lignes"]]
    assert (fam.count("executable"), fam.count("a_arbitrer"), fam.count("exception")) == (16, 3, 14)


def test_la_continuite_des_soldes_sort_le_doublon_des_executables(src, etat):
    # Sans le contrôle de continuité, la ligne réimportée serait imputée par une catégorie actée.
    l29 = next(l for l in src.lignes() if l.id == 29)
    assert classer(l29, src).classe == "I"
    k = next(x for x in etat["lignes"] if x["id"] == 29)["classement"]
    assert k["classe"] == "D" and "doublon probable" in k["motif"]


def test_alertes_du_rapport(etat):
    md = rapport_markdown(etat)
    assert "ALERTE : pas de synchronisation" in md and "BANQUE 3" in md
    assert "ALERTE BANQUE 2" in md
    assert "2 anomalie(s)" in md
    for section in ("## 1. Exécutable", "## 2. À arbitrer", "## 3. Exceptions", "## GO attendu"):
        assert section in md


def test_commande_unique(tmp_path, capsys):
    assert etat_mod.main(["--maintenant", "2026-10-16 07:00:00", "--sortie", str(tmp_path)]) == 0
    assert "Rapport de lettrage du matin" in capsys.readouterr().out
    assert (tmp_path / "2026-10-16_0700_etat.json").exists()


def test_plan_complet_dans_l_ordre(src, etat):
    res = construire_plan(etat, src)
    assert res["arret"] is None and len(res["plan"]) == 16
    classes = [r["classe"] for r in res["plan"]]
    assert classes == sorted(classes, key=["A", "A'1", "B", "N", "R", "I"].index)
    assert all(r["id"] not in (5, 16, 26, 29) for r in res["plan"])   # ni arbitrage ni exception


def test_plan_arret_a_la_premiere_anomalie(src, etat):
    # Entre l'état et le plan, quelqu'un a encaissé partiellement la facture de la ligne 2.
    p = next(p for p in src.ref["pieces"] if p["nom"] == "FV-2026-00131")
    p["residu"] = 2000.0
    res = construire_plan(etat, src)
    assert "garde-fou de somme" in res["arret"]
    assert [r["id"] for r in res["plan"]] == [1]   # rien n'est planifié après la ligne fautive


def test_plan_ligne_deja_rapprochee(src, etat):
    src.ligne_releve(1)["rapprochee"] = True
    assert "déjà rapprochée" in construire_plan(etat, src)["arret"]


def _ecrire_etat(tmp_path, etat):
    f = tmp_path / "etat.json"
    f.write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
    return f


def test_go_consigne_mot_pour_mot(tmp_path, etat, capsys):
    f = _ecrire_etat(tmp_path, etat)
    code = plan_ecriture.main(["--etat", str(f), "--maintenant", "2026-10-16 07:10:00", "--go", "GO pour la section 1"])
    out = capsys.readouterr().out
    assert code == 0 and "« GO pour la section 1 »" in out and "PLAN VALIDÉ PAR GO" in out


def test_go_refuse_sur_etat_perime_ou_go_vide(tmp_path, etat):
    f = _ecrire_etat(tmp_path, etat)
    with pytest.raises(SystemExit):
        plan_ecriture.main(["--etat", str(f), "--maintenant", "2026-10-16 10:00:00", "--go", "GO"])
    with pytest.raises(SystemExit):
        plan_ecriture.main(["--etat", str(f), "--go", "  "])

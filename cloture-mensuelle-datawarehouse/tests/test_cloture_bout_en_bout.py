"""Le déroulé complet : la variante conforme passe, la variante en écart est bloquée avant diffusion."""
import datetime as dt

from controles import fin_de_cloture
from controles.cloturer import cloturer
from tests.conftest import EXEMPLES, P

J0 = dt.date(2026, 4, 1)


def test_sans_go_humain_rien_ne_tourne(capsys):
    assert cloturer(EXEMPLES / "mois_conforme", P, J0, go=False) == 2
    assert "Chargement" not in capsys.readouterr().out


def test_mois_conforme_diffusable(capsys, tmp_path):
    assert cloturer(EXEMPLES / "mois_conforme", P, J0, go=True, figer=tmp_path) == 0
    out = capsys.readouterr().out
    assert "FIN DE CLÔTURE : CONFORME" in out and "DIFFUSABLE après GO humain" in out
    assert (tmp_path / f"fct_ca_mensuel_{P}.csv").exists()


def test_mois_en_ecart_bloque_la_diffusion(capsys):
    assert cloturer(EXEMPLES / "mois_en_ecart", P, J0, go=True) == 1
    out = capsys.readouterr().out
    assert "FIN DE CLÔTURE : ÉCHEC" in out and "NON DIFFUSABLE" in out
    for attendu in ("645100", "P106", "vraisemblance de la production", "F-2026-036", "A-305", "D-501"):
        assert attendu in out


def test_echecs_attendus_de_la_variante(base_ecart):
    fin = fin_de_cloture.executer(base_ecart, P, EXEMPLES / "mois_en_ecart")
    assert sorted(r.nom for r in fin if not r.ok) == ["cadrage paie en valeur", "contrôles du mois", "production sans groupe client"]


def test_mois_inattendu_signale_sans_refus(capsys):
    assert cloturer(EXEMPLES / "mois_conforme", P, dt.date(2026, 5, 4), go=False) == 2
    assert "clôture en retard ou en avance" in capsys.readouterr().out

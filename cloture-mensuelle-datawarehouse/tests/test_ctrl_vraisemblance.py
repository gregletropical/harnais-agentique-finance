"""Vraisemblance : le contrôle qui fait le geste de l'humain regardant un total à côté de l'historique."""
from controles import vraisemblance as VR

HIST = [40000, 45000, 50000, 42000, 48000, 44000]


def test_mois_normal():
    assert VR.juger(46000, HIST, 0.5, 2.0)[0]


def test_export_ampute_bloque():
    ok, r = VR.juger(9000, HIST, 0.5, 2.0)
    assert not ok and r < 0.5


def test_mois_double_bloque_aussi():
    assert not VR.juger(100000, HIST, 0.5, 2.0)[0]


def test_sans_historique_rien_a_juger():
    assert VR.juger(1000, [], 0.5, 2.0) == (True, None)


def test_scenarios(base_conforme, base_ecart):
    q = "SELECT ok FROM ctrl_synthese WHERE controle = 'vraisemblance de la production'"
    assert base_conforme.execute(q).fetchone()[0] == 1
    assert base_ecart.execute(q).fetchone()[0] == 0

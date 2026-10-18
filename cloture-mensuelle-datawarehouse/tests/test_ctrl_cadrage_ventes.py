"""Cadrage des ventes : qualification pièce à pièce et tableau de passage à résidu nul."""
from controles import cadrage_ventes as V
from controles import commun as C


def _f(ht=1000.0, devise="EUR", date="2026-03-31", md=None):
    return {"date": date, "devise": devise, "montant_devise": md or ht, "ht_eur": ht}


def _p(ht=1000.0, date="2026-03-31", autre=0.0):
    return {"date": date, "ht": ht, "tva": ht * 0.2, "ttc": ht * 1.2, "autre": autre}


def test_qualification():
    assert V.qualifier(_f(), _p(), "2026-03", 0.05) == (["identique"], "OK")
    assert V.qualifier(_f(), None, "2026-03", 0.05)[1] == "INSTRUIRE"
    assert V.qualifier(None, _p(), "2026-03", 0.05)[1] == "INSTRUIRE"
    assert V.qualifier(_f(920.0, "USD", md=1000.0), _p(925.5), "2026-03", 0.05)[1] == "METHODE"
    assert V.qualifier(_f(920.0, "USD", md=1000.0), _p(990.0), "2026-03", 0.05)[1] == "INSTRUIRE"
    assert V.qualifier(_f(), _p(1000.6), "2026-03", 0.05)[1] == "METHODE"          # arrondi
    assert V.qualifier(_f(), _p(1030.0), "2026-03", 0.05)[1] == "INSTRUIRE"
    assert V.qualifier(_f(), _p(date="2026-04-02"), "2026-03", 0.05)[1] == "INSTRUIRE"   # écart de période
    assert V.qualifier(_f(), _p(autre=50.0), "2026-03", 0.05)[1] == "INSTRUIRE"          # HT hors classe 70


def test_conforme_residu_nul_et_change_en_methode(base_conforme):
    res = V.executer(base_conforme, "2026-03", C.parametres())
    assert all(r.ok for r in res)
    niv = dict(base_conforme.execute("SELECT numero, niveau FROM ctrl_cadrage_ventes_pieces"))
    assert niv["F-2026-034"] == "METHODE" and list(niv.values()).count("OK") == 4


def test_facture_absente_est_un_constat(base_ecart):
    residu, instr = V.executer(base_ecart, "2026-03", C.parametres())
    assert residu.ok and not instr.ok and not instr.bloquant
    assert any("F-2026-036" in d and "outil_seul" in d for d in instr.details)


def test_piece_non_rapprochable_fait_apparaitre_un_residu(base_conforme):
    """Une pièce de ventes sans numéro reconnaissable échappe au rapprochement : le résidu la révèle et bloque."""
    with base_conforme:
        base_conforme.execute("INSERT INTO raw_grand_livre VALUES ('PRINCIPALE','VT','2026-03-31','AV-1','706100','X','avoir manuel',300,0)")
    residu = V.executer(base_conforme, "2026-03", C.parametres())[0]
    assert not residu.ok and residu.bloquant and "-300,00" in residu.message

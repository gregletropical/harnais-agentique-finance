"""Cadrage des achats : appariement par niveaux de preuve décroissants, qualification, périmètre, résidu."""
from controles import cadrage_achats as A
from controles import commun as C

PRM = C.parametres()


def _f(fid, numero="", bc="", ht=1000.0, fournisseur="FOURNISSEUR X", entite="E1", date="2026-03-10"):
    return {"id_ecriture": fid, "date": date, "entite": entite, "id_projet": "P1", "fournisseur": fournisseur,
            "numero_facture": numero, "bon_commande": bc, "ht_eur": ht}


def _p(piece, txt, ht=1000.0, tiers="FOURNISSEUR X", entite="E1", date="2026-03-15"):
    return {"entite": entite, "piece": piece, "date": date, "tiers": tiers, "txt": txt, "txt_n": A.nb(txt),
            "comptes": {"604100"}, "ht": ht, "ht_604": ht, "mois": date[:7], "hors_perimetre": False}


def test_niveaux_de_preuve():
    F = [_f("a", "FX-10001", "BC-1"), _f("b", "FX-20002"), _f("c", "", "BC-3", ht=1030.0),
         _f("d", ""), _f("e", "FX-50005", entite="E1")]
    P = [_p("p1", "FX-10001 BC-1"), _p("p2", "fact FX-20002"), _p("p3", "commande BC-3"),
         _p("p4", "FOURNISSEUR X prestation"), _p("p5", "FX-50005", entite="E2")]
    m = A.apparier(F, P, PRM)
    assert m == {"a": ("p1", "N1_bc_facture"), "b": ("p2", "N3_facture"), "c": ("p3", "N2_bc"),
                 "d": ("p4", "N4_tiers_montant"), "e": ("p5", "N5_facture_autre_entite")}


def test_une_piece_ne_sert_qu_une_fois_et_la_preuve_forte_passe_d_abord():
    F = [_f("faible", ""), _f("fort", "FX-10001")]
    P = [_p("p1", "FOURNISSEUR X FX-10001")]
    assert A.apparier(F, P, PRM) == {"fort": ("p1", "N3_facture")}


def test_tiers_montant_refuse_hors_tolerance_ou_hors_delai_ou_numero_contradictoire():
    assert A.apparier([_f("d", "", ht=1000.0)], [_p("p", "FOURNISSEUR X", ht=1050.0)], PRM) == {}
    assert A.apparier([_f("d", "", date="2026-01-02")], [_p("p", "FOURNISSEUR X", date="2026-03-15")], PRM) == {}
    # la pièce porte le numéro d'une AUTRE écriture de l'outil : le tiers et le montant ne suffisent pas
    m = A.apparier([_f("d", ""), _f("autre", "FX-99999", entite="E2")], [_p("p", "FOURNISSEUR X FX-99999")], PRM)
    assert "d" not in m and m["autre"] == ("p", "N5_facture_autre_entite")


def test_normalisation_bornee():
    assert A.nb("F-2026-01") not in A.nb("F-2026-011")


def test_conforme(base_conforme):
    res = A.executer(base_conforme, "2026-03", PRM)
    assert all(r.ok for r in res)
    nat = dict(base_conforme.execute("SELECT id_ecriture, nature FROM ctrl_cadrage_achats_outil"))
    assert nat == {"A-301": "ok", "A-302": "ok", "A-303": "ok", "A-304": "hors_perimetre"}
    hors = base_conforme.execute("SELECT piece FROM ctrl_cadrage_achats_compta WHERE nature = 'hors_perimetre'").fetchall()
    assert hors == [("HA-1105",)]


def test_paye_non_comptabilise(base_ecart):
    residu, instr = A.executer(base_ecart, "2026-03", PRM)
    assert residu.ok and not instr.ok and not instr.bloquant
    cat = base_ecart.execute("SELECT categories FROM ctrl_cadrage_achats_outil WHERE id_ecriture = 'A-305'").fetchone()[0]
    assert cat.startswith("O_seul:paye_non_comptabilise")

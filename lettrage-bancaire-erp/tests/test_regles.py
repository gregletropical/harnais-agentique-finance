"""Tests hors réseau du classement : chaque règle, chaque garde-fou, sur des jeux minimaux.

Chaque test reproduit, avec des tiers et des montants fictifs, un cas réel qui a fait
évoluer la règle (coïncidence arithmétique, homonyme, ligne réimportée…).
"""

from regles.categories import SOCIETE_B, SOCIETE_A
from regles.classement import (
    Ligne, PointSolde, anomalie_rapprochement_auto, categorie_i, choisir_tiers, classement_reimport, classer,
    combinaisons_exactes, controle_continuite, correspond, dates_factures_citees, echeancier, emetteur,
    factures_citees, id_emetteur, nom_contrepartie, numeros_cites, suspects_reimport, tiers_par_precedent,
)
from controles.source_fichier import SourceFichier

J1, J_B = 1, 3
_aml = [9000]


def P(nom, tiers_id, residu, societe=SOCIETE_A, date="2026-09-01", ref="", echeances=None):
    _aml[0] += 1
    p = {"id": _aml[0], "nom": nom, "tiers_id": tiers_id, "societe_id": societe, "residu": residu,
         "date": date, "ref": ref, "aml_ids": [_aml[0] + 100000]}
    if echeances:
        p["echeances"] = [{"id": _aml[0] * 10 + i, "residu": r, "echeance": e} for i, (r, e) in enumerate(echeances)]
    return p


def source(tiers=(), pieces=(), **extra):
    ref = {"societes": [{"id": SOCIETE_A, "nom": "A", "verrou": "2025-12-31"},
                        {"id": SOCIETE_B, "nom": "B", "verrou": "2025-12-31"}],
           "journaux": [{"id": J1, "nom": "B1", "societe_id": SOCIETE_A, "derniere_synchro_utc": ""},
                        {"id": J_B, "nom": "B3", "societe_id": SOCIETE_B, "derniere_synchro_utc": ""}],
           "tiers": [{"id": i, "nom": n, **({"archive_sans_piece": True} if i >= 800 and i < 900 else {})}
                     for i, n in tiers] + [{"id": 901, "nom": "HEBERGEUR CLOUD EXEMPLE"},
                                           {"id": 902, "nom": "FOURNISSEUR ENERGIE EXEMPLE"}],
           "pieces": list(pieces), **extra}
    return SourceFichier(ref, {"lignes": []})


def L(montant, libelle, journal=J1, societe=SOCIETE_A, date="2026-10-15", **kw):
    return Ligne(id=1, date=date, montant=montant, libelle=libelle, journal_id=journal, journal="",
                 societe_id=societe, societe="", verrou="2025-12-31", **kw)


# --------------------------------------------------------------------------- #
# Extraction depuis le libellé
# --------------------------------------------------------------------------- #

def test_numeros_cites_exclut_dates_et_identifiants():
    assert numeros_cites("VIR SEPA RECU /FRM ALPHA /RNF FV 00129") == ["00129"]
    assert numeros_cites("VIR SEPA RECU /FRM ALPHA /RNF FV00129") == ["00129"]
    assert numeros_cites("PRLV SEPA X ECH/151026 ID EMETTEUR/FR00ZZZ999001") == []


def test_nom_contrepartie():
    assert nom_contrepartie("VIR SEPA RECU /FRM ALPHA LOGICIELS /EID 1") == "ALPHA LOGICIELS"
    assert nom_contrepartie("VIR SEPA EMIS /PID XI SOFTWARE - REF/FACTURE 90000123") == "XI SOFTWARE"
    assert nom_contrepartie("PRLV SEPA NU FOURNITURES ECH/151026") == "NU FOURNITURES"


def test_emetteur_et_creancier_sepa():
    assert emetteur("VIR SEPA RECU /FRM SAS  GAMMA   INDUSTRIE /RNF X") == "SAS GAMMA INDUSTRIE"
    assert id_emetteur("PRLV SEPA X ECH/1 ID EMETTEUR/FR00ZZZ999001 REF/2") == "FR00ZZZ999001"


def test_factures_citees_et_echeancier():
    assert factures_citees("VIR SEPA EMIS /PID XI - REF/FACTURE 90000123") == ["90000123"]
    assert echeancier("VIR /RNF ECHEANCIER 2/4 FACTURES 15/07+08") == (2, 4)
    assert dates_factures_citees("ECHEANCIER 2/4 FACTURES 15/07+08", "2026-10-15") == ["2026-07-15", "2026-08-15"]
    # Mois cité postérieur au mois de la ligne : année précédente.
    assert dates_factures_citees("FACTURES 15/11", "2026-02-10") == ["2025-11-15"]


# --------------------------------------------------------------------------- #
# Identification du tiers : jamais de devinette
# --------------------------------------------------------------------------- #

def test_deux_premiers_mots_exiges():
    assert not correspond("M JEAN DUPONT", "12 rue Jean Jaures")
    assert correspond("ALPHA L.B.", "ALPHA LB")
    assert correspond("SIGMA", "SIGMA CONSEIL")       # un mot de 4 caractères et plus suffit
    assert not correspond("GE", "GE TRANSPORTS")       # mot court : nom exact exigé
    assert correspond("GE", "GE")


def test_nom_exact_departage_et_coquille_ecartee():
    cands = [(1, "SIGMA CONSEIL"), (2, "SIGMA CONSEIL, M. DURAND")]
    assert choisir_tiers("SIGMA CONSEIL", cands) == (1, "SIGMA CONSEIL")
    assert choisir_tiers("SIGMA", [(1, "SIGMA CONSEIL"), (2, "SIGMA ETUDES")]) is None
    # Fiche archivée sans pièce (doublon d'import) : écartée quand plusieurs sont plausibles.
    assert choisir_tiers("SIGMA", [(1, "SIGMA CONSEIL"), (3, "SIGMA CONSEIL")], coquilles={3}) == (1, "SIGMA CONSEIL")
    assert choisir_tiers("SAS ALPHA LOGICIELS", [(1, "ALPHA LOGICIELS"), (2, "ALPHA LOGICIELS EUROPE")]) == \
        (1, "ALPHA LOGICIELS")


def test_precedent_bancaire_unanime_seulement():
    assert tiers_par_precedent([(5, "X"), (5, "X")]) == (5, "X")
    assert tiers_par_precedent([(5, "X")]) is None                       # un seul précédent
    assert tiers_par_precedent([(5, "X"), (6, "Y"), (5, "X")]) is None   # un discordant
    assert tiers_par_precedent([(5, "X"), (None, None)]) is None         # une ligne sans tiers


# --------------------------------------------------------------------------- #
# Combinaisons exactes
# --------------------------------------------------------------------------- #

def test_combinaisons():
    assert combinaisons_exactes([72000, 144000, 99000], 216000)[0] == 1
    assert combinaisons_exactes([50000, 100000, 70000, 80000], 150000)[0] == 2
    assert combinaisons_exactes([100, 200, 300, 400], 600, taille=3)[0] == 1
    assert combinaisons_exactes(list(range(1, 50)), 10)[0] is None    # trop de pièces : pas d'énumération


# --------------------------------------------------------------------------- #
# Classes exécutables
# --------------------------------------------------------------------------- #

def test_A_reference_citee_montant_exact():
    src = source([(1, "ALPHA LOGICIELS")], [P("FV-2026-00129", 1, 3600.0)])
    k = classer(L(3600.0, "VIR SEPA RECU /FRM ALPHA LOGICIELS /RNF FV 00129"), src)
    assert k.classe == "A" and k.executable and k.geste["type"] == "lettrer"


def test_A_par_echeance_la_plus_ancienne():
    src = source([(1, "GAMMA")], [P("FV-2026-00128", 1, 3750.0,
                                    echeances=[(1250.0, "2026-10-05"), (1250.0, "2026-11-05"), (1250.0, "2026-12-05")])])
    k = classer(L(2500.0, "VIR SEPA RECU /FRM GAMMA /RNF FV 00128"), src)
    assert k.classe == "A" and len(k.geste["aml_ids"]) == 2


def test_A1_combinaison_triviale_avec_validation_comptable():
    src = source([(1, "DELTA SERVICES")], [P("FV-2026-1", 1, 720.0), P("FV-2026-2", 1, 1440.0), P("FV-2026-3", 1, 990.0)])
    k = classer(L(2160.0, "VIR SEPA RECU /FRM DELTA SERVICES"), src)
    assert k.classe == "A'1" and k.validation_comptable and k.pieces_ouvertes == 3 and k.combinaisons == 1


def test_A2_unique_mais_au_dela_des_seuils_non_executable():
    # Cas fondateur : une combinaison unique sur 4 pièces parmi 10 ouvertes reste une coïncidence
    # possible. Un client réel avait lettré une composition différente de celle calculée.
    vals = [1234.56, 2345.67, 3456.78, 987.65, 1876.54, 765.43, 2109.87, 1543.21, 2468.13, 1357.92]
    src = source([(1, "EPSILON")], [P(f"FV-2026-{i}", 1, v) for i, v in enumerate(vals)])
    k = classer(L(round(1234.56 + 987.65 + 765.43 + 2468.13, 2), "VIR SEPA RECU /FRM EPSILON"), src)
    assert k.classe == "A'2" and not k.executable


def test_B_lot_unique_et_D_deux_lots():
    lot = {"id": 1, "nom": "LOT/1", "montant": -500.0, "journal_id": J1, "etat": "envoye"}
    assert classer(L(-500.0, "VIR SEPA EMIS /PID LOT X"), source(lots=[lot])).classe == "B"
    deux = [lot, {**lot, "id": 2, "nom": "LOT/2"}]
    assert classer(L(-500.0, "VIR SEPA EMIS /PID LOT X"), source(lots=deux)).classe == "D"


def test_N_virement_groupe_taille_imposee():
    pay = [{"id": i, "residu": r, "libelle": f"NDF/{i}", "date": "2026-10-13", "journal_id": J1}
           for i, r in enumerate([-210.40, -312.50, -120.00, -95.30], 1)]
    k = classer(L(-642.90, "VIR SEPA EMIS /PID NOTES DE FRAIS /NBT 3"), source(paiements_en_cours=pay))
    assert k.classe == "N"
    # Paiements hors de la fenêtre de 5 jours : non candidats.
    vieux = [{**x, "date": "2026-09-01"} for x in pay]
    assert classer(L(-642.90, "VIR SEPA EMIS /PID NDF /NBT 3"), source(paiements_en_cours=vieux)).classe == "D"


def test_R_remboursement_et_ambiguite():
    lig = {"id": 1, "piece": "AV-1", "residu": -480.0, "tiers_id": 1, "societe_id": SOCIETE_A}
    lib = "VIR SEPA EMIS /PID ZETA HOLDING REMBOURSEMENT TROP PERCU"
    assert classer(L(-480.0, lib), source([(1, "ZETA HOLDING")], lignes_ouvertes_tiers=[lig])).classe == "R"
    deux = [lig, {**lig, "id": 2, "piece": "AV-2"}]
    assert classer(L(-480.0, lib), source([(1, "ZETA HOLDING")], lignes_ouvertes_tiers=deux)).classe == "D"


# --------------------------------------------------------------------------- #
# Catégories d'imputation (classe I) et leurs garde-fous
# --------------------------------------------------------------------------- #

def test_I_frais_bancaires_compte_par_societe():
    k = classer(L(-38.40, "COMMISSIONS FACTURE NUMERO 1"), source())
    assert k.classe == "I" and k.geste["compte"] == "627000"
    cat, _ = categorie_i("COMMISSIONS FACTURE NUMERO 1", -38.40, SOCIETE_B)
    assert cat.compte_de(SOCIETE_B) == "627800"


def test_I_categorie_ecartee_si_tiers_pose():
    k = classer(L(-15.0, "FRAIS DE TENUE DE COMPTE", partenaire_id=901, partenaire="X"), source())
    assert k.classe == "D" and "tiers posé" in k.motif


def test_I_sens_du_montant_respecte():
    # Un libellé de frais bancaires en crédit n'est pas un frais bancaire.
    assert categorie_i("COMMISSIONS FACTURE NUMERO 1", +38.40, SOCIETE_A) == (None, None)


def test_I_plafond():
    k = classer(L(-62500.0, "ECHEANCE PRET MOYEN TERME T4", journal=J_B, societe=SOCIETE_B), source())
    assert k.classe == "D" and "50 000" in k.motif
    k = classer(L(-4200.0, "ECHEANCE PRET MOYEN TERME T3", journal=J_B, societe=SOCIETE_B), source())
    assert k.classe == "I"


def test_I_hors_societe_actee_signalee():
    lib = "VIR SEPA RECU /FRM ASSUREUR PREVOYANCE EXEMPLE /RNF PREVOYANCE 092026"
    k = classer(L(2340.0, lib, journal=J_B, societe=SOCIETE_B), source())
    assert k.classe == "D" and "extension à arbitrer" in k.motif
    k = classer(L(2340.0, lib), source())
    assert k.classe == "I"


def test_I_ca3_controle_unicite_od():
    od = {"id": 1, "piece": "OD/9", "residu": -18245.0, "compte": "445510", "societe_id": SOCIETE_A}
    lib = "PRLV SEPA DGFIP LIB/TVA-092026-3310CA3"
    k = classer(L(-18245.0, lib), source(lignes_ouvertes_compte=[od]))
    assert k.classe == "I" and k.geste["lettrer_avec"] == [1]
    k = classer(L(-18245.0, lib), source(lignes_ouvertes_compte=[od, {**od, "id": 2, "piece": "OD/8"}]))
    assert k.classe == "D" and "unicité" in k.motif


def test_I_a_arbitrer_jamais_execute():
    k = classer(L(820.0, "VIR SEPA RECU /FRM ASSUREUR DOMMAGES EXEMPLE /RNF SINISTRE"), source())
    assert k.classe == "D" and "à arbitrer" in k.motif


def test_I_apres_factures_cede_devant_une_facture_ouverte():
    lib = "PRLV SEPA FOURNISSEUR ENERGIE EXEMPLE ECH/141026"
    assert classer(L(-265.10, lib), source()).classe == "I"
    src = source(pieces=[P("FA-EN-1", 902, -265.10)])
    k = classer(L(-265.10, lib), src)
    assert k.classe == "A'1"


# --------------------------------------------------------------------------- #
# Exceptions et cas à arbitrer
# --------------------------------------------------------------------------- #

def test_exercice_clos_jamais_execute():
    src = source([(1, "ALPHA")], [P("FV-2025-00101", 1, 700.0)])
    k = classer(L(700.0, "VIR SEPA RECU /FRM ALPHA /RNF FV 00101", date="2025-12-30"), src)
    assert k.classe == "D" and "exercice clos" in k.motif


def test_P_ligne_partiellement_traitee():
    k = classer(L(-1040.0, "PRLV SEPA PI LOCATIONS", contreparties_posees=["613200"]), source())
    assert k.classe == "P"


def test_C_partiel_et_D_hors_tolerance():
    src = source([(1, "ETA")], [P("FV-2026-00124", 1, 2400.0)])
    assert classer(L(1000.0, "VIR SEPA RECU /FRM ETA /RNF FV 00124"), src).classe == "C"
    k = classer(L(2400.01, "VIR SEPA RECU /FRM ETA /RNF FV 00124"), src)
    assert k.classe == "D" and "tolérance nulle" in k.motif   # un centime de trop suffit


def test_D_combinaisons_multiples():
    src = source([(1, "MU TECHNOLOGIES")], [P(f"FV-2026-{v}", 1, v) for v in (500.0, 1000.0, 700.0, 800.0)])
    k = classer(L(1500.0, "VIR SEPA RECU /FRM MU TECHNOLOGIES"), src)
    assert k.classe == "D" and k.combinaisons == 2


def test_D_tiers_incertain_et_tiers_inconnu():
    src = source([(1, "OMEGA MEDIA")], [P("FV-2026-00125", 1, 640.0)])
    assert "tiers incertain" in classer(L(640.0, "VIR SEPA RECU /FRM LAMBDA CONSULTING"), src).motif
    assert "aucune correspondance" in classer(L(950.0, "VIR SEPA RECU /FRM KAPPA"), src).motif


def test_D_double_paiement_probable():
    payee = {"nom": "FA-NU-1", "tiers_id": 1, "societe_id": SOCIETE_A, "montant": -356.40, "date": "2026-10-01"}
    k = classer(L(-356.40, "PRLV SEPA NU FOURNITURES ECH/151026"), source([(1, "NU FOURNITURES")], factures_payees=[payee]))
    assert k.classe == "D" and "double paiement" in k.motif


def test_D_facture_citee_absente_de_la_combinaison():
    src = source([(1, "XI SOFTWARE")], [P("FA-XI-1", 1, -587.4, ref="INV-90000045")])
    k = classer(L(-587.4, "VIR SEPA EMIS /PID XI SOFTWARE - REF/FACTURE 90000123"), src)
    assert k.classe == "D" and "appariement refusé" in k.motif
    # La même ligne citant la bonne référence passe.
    src = source([(1, "XI SOFTWARE")], [P("FA-XI-1", 1, -587.4, ref="INV-90000123")])
    assert classer(L(-587.4, "VIR SEPA EMIS /PID XI SOFTWARE - REF/FACTURE INV-90000123"), src).classe in ("A", "A'1")


def test_E_echeancier_proposition_derniere_partielle():
    src = source([(1, "OMICRON SANTE")], [P("FV-2026-00113", 1, 500.0, date="2026-07-15"),
                                          P("FV-2026-00114", 1, 2000.0, date="2026-08-15")])
    k = classer(L(1500.0, "VIR SEPA RECU /FRM OMICRON SANTE /RNF ECHEANCIER 2/4 FACTURES 15/07+08"), src)
    assert k.classe == "E" and k.geste["reste_partielle"] == 1000.0 and not k.executable
    k = classer(L(1500.0, "VIR SEPA RECU /FRM OMICRON SANTE /RNF ECHEANCIER 2/4"), src)
    assert k.classe == "D" and "périmètre indéterminé" in k.motif


def test_tiers_par_precedent_bancaire():
    prec = [{"ligne_id": i, "libelle": f"VIR SEPA RECU /FRM UPSILON GESTION /RNF P{i}", "journal_id": J1,
             "tiers_id": 1} for i in range(3)]
    src = source([(1, "HOLDING U.G. PARTICIPATIONS")], [P("FV-2026-00120", 1, 4800.0)], precedents_bancaires=prec)
    k = classer(L(4800.0, "VIR SEPA RECU /FRM UPSILON GESTION /RNF OCTOBRE"), src)
    assert k.classe == "A'1" and "précédent bancaire" in k.motif


# --------------------------------------------------------------------------- #
# Contrôles transverses
# --------------------------------------------------------------------------- #

def test_continuite_detecte_la_ligne_reimportee():
    pts = [PointSolde(d, [100.0 + e], 100.0) for d, e in
           (("2026-10-08", 0), ("2026-10-09", 0), ("2026-10-12", 0), ("2026-10-14", 150), ("2026-10-15", 150))]
    diag = controle_continuite(pts)
    assert diag["fiable"] and diag["alerte"] and diag["apparition"] == ("2026-10-12", "2026-10-14")
    lignes = [L(-150.0, "SOUSCRIPTION TITRES BANQUE", date="2026-10-14"), L(-150.0, "AUTRE", date="2026-10-09")]
    lignes[1].id = 2
    assert suspects_reimport(lignes, J1, diag) == [1]
    assert classement_reimport(diag).classe == "D"


def test_continuite_journal_non_controlable_jamais_en_alerte():
    pts = [PointSolde(f"2026-10-{d:02d}", [100.0 + d], 100.0) for d in range(8, 14)]
    diag = controle_continuite(pts)
    assert not diag["fiable"] and not diag["alerte"]


def test_rapprochements_automatiques():
    assert anomalie_rapprochement_auto("445740", "445740", False) is None   # paire de TVA générée par l'ERP
    assert anomalie_rapprochement_auto("512300", "411000", False) is None
    assert "416000" in anomalie_rapprochement_auto("416000", "411000", False)
    assert "partiellement" in anomalie_rapprochement_auto("401000", "512300", True)

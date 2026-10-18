"""Gestes interdits, niveaux de droits et GO humain — à passer AVANT toute écriture.

Ce que ces tests prouvent, sans aucun appel réseau (le transport est une boîte de fichiers) :
1. aucune méthode d'envoi, de suppression, de corbeille ou de transfert n'est atteignable par le
   client du pipeline, même sur le profil d'écriture ;
2. le profil lecture ne peut rien écrire, et le niveau plein n'est jamais chargé par le pipeline ;
3. un `modify` ne peut pas poser TRASH ni SPAM (suppression ou déclassement déguisés) ;
4. la lecture des messages est forcée en métadonnées ;
5. les profils de connexion ne demandent aucun scope hors niveau ni aucun scope « jamais » ;
6. le contrôle statique attrape un connecteur fautif ;
7. l'exécution des décisions humaines refuse tout ce qui sort du vocabulaire fermé.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import CONF, MAILS, MANIFESTE, RACINE, REGLES, message
from controles import client_messagerie as cm, controle_gestes, controle_scopes, dedoublonnage, execution
from controles import regles_tri, signaux as sg

EXEMPLES = RACINE / "exemples"


@pytest.fixture
def transport():
    return cm.TransportFichiers(MAILS)


def _refuse(client, methode, corps=None) -> bool:
    try:
        client.appel(methode, {"id": "01_sain_facture_fournisseur"}, corps)
    except cm.MethodeInterdite:
        return True
    return False


@pytest.mark.parametrize("methode", [
    ("messages", "send"), ("messages", "delete"), ("messages", "trash"), ("messages", "batchDelete"),
    ("drafts", "send"), ("drafts", "create"), ("threads", "trash"), ("labels", "delete"),
    ("settings", "forwardingAddresses", "create"), ("messages", "forward"), ("messages", "reply"),
])
def test_envoi_suppression_transfert_refuses_meme_en_ecriture(transport, methode):
    rw = cm.ClientMessagerie(cm.Profil("boite-maintenance", "maintenance"), transport, ecriture=True)
    assert _refuse(rw, methode)
    assert transport.journal == []


def test_liste_blanche_sans_verbe_interdit():
    verbes = set(cm.REGLES["verbes_interdits"])
    for methode in cm.METHODES_AUTORISEES:
        assert methode[-1] not in verbes and "drafts" not in methode


def test_lecture_ne_peut_pas_ecrire(transport):
    ro = cm.ClientMessagerie(cm.Profil("boite-lecture", "lecture"), transport)
    assert _refuse(ro, ("messages", "modify"), {"addLabelIds": ["IA/x"]})
    assert _refuse(ro, ("labels", "create"), {"name": "IA/x"})
    with pytest.raises(cm.MethodeInterdite):
        cm.ClientMessagerie(cm.Profil("boite-lecture", "lecture"), transport, ecriture=True)
    with pytest.raises(cm.MethodeInterdite):
        cm.ClientMessagerie(cm.Profil("boite-maintenance", "maintenance"), transport, ecriture=False)


def test_niveau_plein_interdit_au_pipeline(transport):
    for ecriture in (True, False):
        with pytest.raises(cm.MethodeInterdite):
            cm.ClientMessagerie(cm.Profil("boite-plein", "plein"), transport, ecriture=ecriture)


def test_modify_ne_pose_ni_corbeille_ni_spam(transport):
    rw = cm.ClientMessagerie(cm.Profil("boite-maintenance", "maintenance"), transport, ecriture=True)
    assert _refuse(rw, ("messages", "modify"), {"addLabelIds": ["TRASH"]})
    assert _refuse(rw, ("messages", "modify"), {"addLabelIds": ["IA/À traiter", "SPAM"]})
    assert not _refuse(rw, ("messages", "modify"), {"addLabelIds": ["IA/À traiter"], "removeLabelIds": ["INBOX"]})


def test_lecture_forcee_en_metadonnees(transport):
    vus = []
    origine = transport.executer
    transport.executer = lambda m, p, c: (vus.append(p), origine(m, p, c))[1]
    ro = cm.ClientMessagerie(cm.Profil("boite-lecture", "lecture"), transport)
    rep = ro.appel(("messages", "get"), {"id": "05_injection_html_cachee", "format": "full"})
    assert vus[-1]["format"] == "metadata"
    assert set(rep) == {"id", "labelIds", "headers"} and "SYSTEM" not in json.dumps(rep)


def test_archiver_est_reversible(transport):
    rw = cm.ClientMessagerie(cm.Profil("boite-maintenance", "maintenance"), transport, ecriture=True)
    rw.archiver("02_sain_interne_reunion")
    assert transport.journal == [("messages.modify", "02_sain_interne_reunion", (), ("INBOX", "UNREAD"))]


# --- niveaux de droits -----------------------------------------------------------------
@pytest.mark.parametrize("profil", sorted((EXEMPLES / "profils").glob("*.json")), ids=lambda p: p.stem)
def test_profils_conformes(profil):
    assert controle_scopes.controler_profil(json.loads(profil.read_text(encoding="utf-8"))) == []


@pytest.mark.parametrize("profil,regles_attendues", [
    ("profil-trop-large.json", {"S2", "S3"}),
    ("plein-sur-serveur-m365.json", {"S3", "S4"}),
    ("lecture-avec-outils-d-envoi.json", {"S2", "S5"}),
])
def test_profils_fautifs_detectes(profil, regles_attendues):
    ecarts = controle_scopes.controler_profil(
        json.loads((EXEMPLES / "profils_fautifs" / profil).read_text(encoding="utf-8")))
    assert {e.split()[0] for e in ecarts} == regles_attendues


# --- contrôle statique -----------------------------------------------------------------
def test_code_du_pipeline_sans_geste_interdit():
    assert controle_gestes.analyser_dossier(RACINE / "controles") == []


def test_connecteur_fautif_detecte():
    codes = {v[2] for v in controle_gestes.analyser_dossier(EXEMPLES / "code_fautif")}
    assert codes == {"G1", "G2", "G3"}


# --- tri sur métadonnées, dédoublonnage, GO humain -------------------------------------
def test_fichier_de_regles_valide():
    regles_tri.charger()


@pytest.mark.parametrize("fichier,action,regle", [
    ("03_sain_lettre_information.eml", "archivable", "R10-liste-diffusion"),
    ("11_lien_reinitialisation.eml", "suspect", "R01-dmarc-echec-cible-usurpation"),
    ("01_sain_facture_fournisseur.eml", "a_traiter", "R02-correspondant-connu"),
])
def test_regles_tri_sur_metadonnees(fichier, action, regle):
    m = message(fichier)
    d = regles_tri.decider(REGLES, regles_tri.faits(m, sg.calculer(m, CONF)))
    assert (d.action, d.regle_action) == (action, regle)


def test_dedoublonnage_inter_boites():
    r = dedoublonnage.controler(MAILS)
    assert r["total"] == len(MANIFESTE) and r["uniques"] == len(MANIFESTE) - 1
    assert r["groupes"] == {"boite-principale+boite-service": 1}


def _mid(transport, ident):
    return transport.messages[ident].message_id


def test_execution_go_humain(transport):
    rw = cm.ClientMessagerie(cm.Profil("boite-maintenance", "maintenance"), transport, ecriture=True)
    decisions = [
        {"cle": "K01", "ident": "02_sain_interne_reunion", "message_id": _mid(transport, "02_sain_interne_reunion"),
         "decision": "archiver"},
        {"cle": "K02", "ident": "01_sain_facture_fournisseur", "message_id": _mid(transport, "01_sain_facture_fournisseur"),
         "decision": "a_faire", "resume": "Contrôler et régler la facture F-2026-118"},
        {"cle": "K03", "ident": "04_injection_directe", "message_id": _mid(transport, "04_injection_directe"),
         "decision": "supprimer"},
        {"cle": "K04", "ident": "03_sain_lettre_information", "message_id": "<autre@exemples.test>",
         "decision": "archiver"},
        {"cle": "K05", "ident": "09_virement_urgent_dirigeant", "message_id": _mid(transport, "09_virement_urgent_dirigeant"),
         "decision": "archiver", "commentaire": "Attendre le contre-appel avant d'archiver"},
        {"cle": "K06", "ident": "10_changement_rib_sosie_fournisseur",
         "message_id": _mid(transport, "10_changement_rib_sosie_fournisseur"), "decision": "transférer au comptable"},
    ]
    simulation = execution.executer(decisions, rw, appliquer=False)
    assert transport.journal == [] and simulation.archives == ["K01"]
    bilan = execution.executer(decisions, rw, appliquer=True)
    assert bilan.archives == ["K01"] and len(bilan.taches) == 1
    assert dict(bilan.anomalies) == {"K03": "decision_hors_vocabulaire", "K04": "identite_non_confirmee",
                                     "K05": "commentaire_a_traiter_d_abord", "K06": "decision_hors_vocabulaire"}
    assert transport.journal == [("messages.modify", "02_sain_interne_reunion", (), ("INBOX", "UNREAD"))]

"""Mutations volontaires du code, pour contrôler la recette elle-même.

Un PASS ne vaut que si le test sait échouer. Chaque mutation ci-dessous casse une
défense précise ; `test_mutations.py` relance la recette avec chacune d'elles et
exige qu'au moins un test échoue. Une mutation qui passerait inaperçue serait un
test mort, c'est-à-dire un faux sentiment de sécurité.

La mutation est choisie par la variable d'environnement RECETTE_MUTATION et
appliquée par `conftest.py` avant tout test.
"""
from __future__ import annotations

import json
import re

from controles import client_messagerie, lecteur, lecteur_revue, orchestrateur, signaux


def _validateur_permissif():
    def permissif(brut):
        try:
            obj = json.loads(re.search(r"\{.*\}", str(brut), re.S).group(0))
        except Exception:
            obj = {}
        cat = obj.get("categorie") if obj.get("categorie") in lecteur.CATEGORIES else "Indetermine"
        att = obj.get("attente_utilisateur") if obj.get("attente_utilisateur") in lecteur.ATTENTES else "aucune"
        urg = obj.get("urgence") if obj.get("urgence") in lecteur.URGENCES else "basse"
        return lecteur.Verdict(True, cat, att, urg)
    lecteur.valider_sortie = permissif


def _balises_non_neutralisees():
    lecteur.neutraliser = lambda texte, limite: (str(texte) if texte else "")[:limite]


def _orchestrateur_laxiste():
    def laxiste(verdict, signaux_, boite_partagee, anomalies=()):
        if getattr(verdict, "valide", False):
            return orchestrateur.Proposition("libelle_automatique", verdict.categorie)
        return orchestrateur.Proposition("rien", None)
    orchestrateur.decider = laxiste


def _exception_propagee():
    def lire(sujet, domaine, corps, noms_pj, appeler, extraits_pj=None):
        consigne, contenu = lecteur.preparer(sujet, domaine, corps, noms_pj, extraits_pj)
        return lecteur.valider_sortie(appeler(consigne, contenu))
    lecteur.lire = lire


def _sujet_dans_consigne():
    origine = lecteur.preparer

    def preparer(sujet, domaine, corps, noms_pj=None, extraits_pj=None, nonce=None):
        consigne, contenu = origine(sujet, domaine, corps, noms_pj, extraits_pj, nonce)
        return consigne + f"\nSujet du message : {sujet}", contenu
    lecteur.preparer = preparer


def _dmarc_absent_neutre():
    origine = signaux.verdict_authentification

    def verdict(entetes, serveur):
        res, forge = origine(entetes, serveur)
        if res["dmarc"] in ("absent", "none"):
            res["dmarc"] = "pass"
        return res, forge
    signaux.verdict_authentification = verdict


def _entete_forge_acceptee():
    signaux._authserv = lambda valeur: "mx.messagerie-exemple.test"


def _assainissement_desactive():
    lecteur_revue.assainir = lambda obj, rejets, chemin="": obj


def _faits_sans_controle():
    orchestrateur.faits_candidats = lambda s, lecture, anomalies: [
        {**f, "statut": "quarantaine"} for f in (lecture or {}).get("contexte", [])]


def _liste_blanche_ouverte():
    client_messagerie.METHODES_AUTORISEES = client_messagerie.METHODES_AUTORISEES | {
        ("messages", "send"), ("messages", "delete"), ("messages", "trash")}
    client_messagerie.LIBELLES_INTERDITS = frozenset()


MUTATIONS = {
    "validateur_permissif": _validateur_permissif,
    "balises_non_neutralisees": _balises_non_neutralisees,
    "orchestrateur_laxiste": _orchestrateur_laxiste,
    "exception_propagee": _exception_propagee,
    "sujet_dans_consigne": _sujet_dans_consigne,
    "dmarc_absent_neutre": _dmarc_absent_neutre,
    "entete_forge_acceptee": _entete_forge_acceptee,
    "assainissement_desactive": _assainissement_desactive,
    "faits_sans_controle": _faits_sans_controle,
    "liste_blanche_ouverte": _liste_blanche_ouverte,
}


def appliquer(nom: str | None) -> None:
    if nom:
        MUTATIONS[nom]()

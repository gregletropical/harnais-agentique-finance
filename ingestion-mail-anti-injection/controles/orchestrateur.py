"""Orchestrateur : barrière 6 (séparation lecteur / orchestrateur) et barrière 8 (politique de confiance).

L'orchestrateur est la partie qui, dans le système réel, a des outils (poser un
libellé, archiver, préparer un brouillon). Il ne voit JAMAIS le contenu brut d'un
message. Ses seules entrées sont :
- un `Verdict` (tri) ou une lecture validée et assainie (revue), produits par le lecteur ;
- des `Signaux` calculés hors ligne sur les en-têtes ;
- des codes d'anomalie anti-fraude (liste fermée).

La frontière est un TYPE, pas une consigne : passer une chaîne à `decider` lève
TypeError. L'analyse AST de la recette vérifie qu'il n'importe ni l'ingestion, ni
l'extracteur HTML, ni les fonctions de préparation du lecteur.

Il n'exécute rien : il rend une PROPOSITION, choisie dans une liste fermée. Les
trois interdits de la doctrine sont structurels — aucune proposition « envoyer »,
« supprimer » ou « ouvrir un lien » n'existe dans son vocabulaire.

Risque résiduel assumé, et c'est la raison d'être de cette couche : un modèle
détourné peut mentir À L'INTÉRIEUR du schéma (classer un message d'attaque en
`Clients`, urgence `haute`). Le schéma borne ce qu'il peut dire, pas la vérité
de ce qu'il dit. D'où la règle : **un verdict de modèle peut abaisser la
confiance, jamais l'élever.** Seuls DMARC `pass` ET un émetteur en relation
ouvrent l'unique automatisme admis (un libellé, additif et réversible), et jamais
sur une boîte partagée.
"""
from __future__ import annotations

from dataclasses import dataclass

from .lecteur import Verdict
from .signaux import Signaux

# --- tri du flux ------------------------------------------------------------
PROPOSITIONS = (
    "rien",                    # verdict rejeté ou indéterminé : on ne fait rien
    "libelle_automatique",     # geste additif et réversible, seul automatisme admis
    "a_valider",               # tout le reste : une proposition, jamais un geste
)

# --- revue du stock ---------------------------------------------------------
DECISIONS_REVUE = (
    "revue_humaine",   # suspect, non authentifié, anomalie, lecture rejetée
    "a_faire",         # une action est attendue de l'utilisateur
    "garder",          # sujet protégé : jamais proposé à l'archivage
    "archiver",        # proposition d'archivage, exécutée seulement après GO humain
)
MOTIFS_REVUE = ("traitement_degrade", "anomalie_fraude", "lecture_rejetee", "lecture_suspecte",
                "risque_eleve", "action_attendue", "sujet_protege", "information")


@dataclass(frozen=True)
class Proposition:
    geste: str
    categorie: str | None

    def __post_init__(self):
        if self.geste not in PROPOSITIONS:
            raise ValueError("geste hors liste fermée")


@dataclass(frozen=True)
class PropositionRevue:
    decision: str
    motif: str
    resume_action: str | None = None   # champ texte borné et assaini par le lecteur de revue

    def __post_init__(self):
        if self.decision not in DECISIONS_REVUE or self.motif not in MOTIFS_REVUE:
            raise ValueError("décision ou motif hors liste fermée")


def _verifier_signaux(signaux) -> None:
    if not isinstance(signaux, Signaux):
        raise TypeError("l'orchestrateur n'accepte que des Signaux calculés, jamais des en-têtes bruts")


def decider(verdict: Verdict, signaux: Signaux, boite_partagee: bool, anomalies: tuple = ()) -> Proposition:
    """Tri du flux : quelle proposition pour ce message ?"""
    if not isinstance(verdict, Verdict):
        raise TypeError("l'orchestrateur n'accepte qu'un Verdict, jamais un contenu brut")
    _verifier_signaux(signaux)
    if type(boite_partagee) is not bool:
        raise TypeError("boite_partagee doit être un booléen")
    if not verdict.valide or verdict.categorie == "Indetermine":
        return Proposition("rien", None)
    if boite_partagee or anomalies:
        return Proposition("a_valider", verdict.categorie)   # boîte partagée ou anomalie : jamais d'automatisme
    if signaux.confiance and signaux.dmarc == "pass" and signaux.connu and signaux.mode == "normal":
        return Proposition("libelle_automatique", verdict.categorie)
    return Proposition("a_valider", verdict.categorie)


def proposer_revue(signaux: Signaux, lecture: dict | None, anomalies: tuple, protege: bool) -> PropositionRevue:
    """Revue du stock : décision PROPOSÉE à l'humain, jamais exécutée ici."""
    _verifier_signaux(signaux)
    if isinstance(lecture, str):
        raise TypeError("l'orchestrateur n'accepte qu'une lecture validée, jamais un contenu brut")
    if signaux.mode == "degrade" or not signaux.authentifie:
        return PropositionRevue("revue_humaine", "traitement_degrade")
    if anomalies:
        return PropositionRevue("revue_humaine", "anomalie_fraude")
    if not lecture or lecture.get("rejete"):
        return PropositionRevue("revue_humaine", "lecture_rejetee")
    if lecture["famille"] == "suspect" or lecture.get("_rejets"):
        return PropositionRevue("revue_humaine", "lecture_suspecte")
    if lecture["risque"]["niveau"] == "eleve":
        return PropositionRevue("revue_humaine", "risque_eleve")
    act = lecture["action"]
    if lecture["famille"] == "action_attendue" and act["requise"] and act["pour_utilisateur"]:
        return PropositionRevue("a_faire", "action_attendue", act["resume"])
    if protege:
        return PropositionRevue("garder", "sujet_protege")
    return PropositionRevue("archiver", "information")


def faits_candidats(signaux: Signaux, lecture: dict | None, anomalies: tuple) -> list[dict]:
    """Défense contre la persistance (règle 1 du §5 bis).

    Jamais de fait issu d'un message non authentifié, en mode dégradé, porteur
    d'une anomalie, d'une lecture rejetée, suspecte, à risque, ou dont la sortie
    a subi un assainissement. Les faits retenus restent en QUARANTAINE : un fait
    extrait est une affirmation de l'émetteur, datée et sourcée, pas une
    connaissance — il n'entre en mémoire qu'après validation humaine.
    """
    _verifier_signaux(signaux)
    if (not signaux.confiance or signaux.mode == "degrade" or anomalies or not lecture
            or lecture.get("rejete") or lecture.get("_rejets") or lecture["famille"] == "suspect"
            or lecture["risque"]["niveau"] != "aucun"):
        return []
    return [{"theme": f["theme"], "fait": f["fait"], "statut": "quarantaine", "source_domaine": signaux.domaine}
            for f in lecture.get("contexte", []) if f["fait"] != "[rejeté]"]

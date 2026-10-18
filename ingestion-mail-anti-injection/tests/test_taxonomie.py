"""La taxonomie publiée (`regles/taxonomie_sorties.json`) est exactement celle que le code applique.

Un référentiel publié qui diverge du code est pire que pas de référentiel : il fait croire à une
fermeture qui n'existe pas. Ce test échoue dès qu'une valeur est ajoutée d'un côté sans l'autre.
"""
from __future__ import annotations

import json

from conftest import RACINE
from controles import anti_fraude, execution, lecteur, lecteur_revue, orchestrateur, pieces_jointes, regles_tri, signaux

T = json.loads((RACINE / "regles" / "taxonomie_sorties.json").read_text(encoding="utf-8"))


def test_lecteur_tri():
    assert T["lecteur_tri"]["champs"] == {k: list(v) for k, v in lecteur.SCHEMA.items()}
    assert T["lecteur_tri"]["motifs_rejet"] == list(lecteur.MOTIFS_REJET)


def test_lecteur_revue():
    r = T["lecteur_revue"]
    assert r["familles"] == list(lecteur_revue.FAMILLES)
    assert r["themes_contexte"] == list(lecteur_revue.THEMES)
    assert r["niveaux_risque"] == list(lecteur_revue.NIVEAUX_RISQUE)
    assert r["indices_risque"] == list(lecteur_revue.INDICES_RISQUE)
    assert r["motifs_rejet"] == list(lecteur_revue.MOTIFS_REJET_REVUE)
    assert r["motifs_refuses_dans_les_textes"] == [n for n, _ in lecteur_revue.INTERDITS]
    s = lecteur_revue.SCHEMA["properties"]
    assert r["champs_texte_bornes"] == {
        "action.resume": s["action"]["properties"]["resume"]["maxLength"],
        "contexte[].fait": s["contexte"]["items"]["properties"]["fait"]["maxLength"],
        "implication_future.motif": s["implication_future"]["properties"]["motif"]["maxLength"]}


def test_signaux_fraude_pieces():
    assert T["signaux"]["verdicts_dmarc"] == list(signaux.VERDICTS_DMARC)
    assert T["signaux"]["drapeaux_non_confiance"] == list(signaux.DRAPEAUX)
    assert T["anti_fraude"]["anomalies"] == list(anti_fraude.ANOMALIES)
    assert T["pieces_jointes"]["formats_attendus"] == list(pieces_jointes.FORMATS_ATTENDUS)
    assert T["pieces_jointes"]["motifs_non_extraction"] == list(pieces_jointes.MOTIFS)


def test_orchestrateur_regles_execution():
    assert T["orchestrateur"]["propositions_tri"] == list(orchestrateur.PROPOSITIONS)
    assert T["orchestrateur"]["decisions_revue"] == list(orchestrateur.DECISIONS_REVUE)
    assert T["orchestrateur"]["motifs_revue"] == list(orchestrateur.MOTIFS_REVUE)
    assert T["regles_tri"] == {"classes": list(regles_tri.CLASSES), "actions": list(regles_tri.ACTIONS),
                               "niveaux": list(regles_tri.NIVEAUX), "conditions": list(regles_tri.CONDITIONS)}
    assert T["execution"]["decisions_executables"] == list(execution.DECISIONS_EXECUTABLES)

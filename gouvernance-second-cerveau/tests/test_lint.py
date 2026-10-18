"""Le lint se déclenche là où les exemples sont fautifs, et se tait sur le vault propre."""
from pathlib import Path

import pytest

import lint_vault as lv

EXEMPLES = Path(__file__).resolve().parent.parent / "exemples"
SUJETS = {"compta", "data", "process", "outillage"}


def regles(constats, note=None):
    return {c.regle for c in constats if note is None or c.note == note}


def lancer(nom):
    vault = EXEMPLES / nom
    return lv.parcourir(vault, lv.charger_vocabulaire_sujet(vault), avec_git=False)


def test_vault_propre_ni_error_ni_warn():
    constats, scannees = lancer("vault-propre")
    assert scannees > 10
    assert [c for c in constats if c.severite in ("ERROR", "WARN")] == []
    # Seul signal attendu : un jalon dont toutes les dépendances sont faites.
    assert regles(constats) == {"jalon-franchissable"}


def test_vault_exemple_declenche_les_regles_demonstratives():
    constats, _ = lancer("vault-exemple")
    attendues = {
        "type-supprime", "status-invalide", "sujet-yaml-imbrique", "sujet-hors-vocabulaire",
        "sujet-sur-note-sujet", "source-absent", "frontmatter-absent", "note-orpheline",
        "id-en-double", "dependance-morte", "cycle-dependances", "focus-hors-plafond",
        "focus-hors-hub", "focus-invalide", "recurrence-invalide", "projet-cible-non-projet",
        "ref-externe-invalide", "ref-externe-hors-perimetre", "diese-dans-frontmatter",
        "summary-trop-long", "created-format", "importance-hors-bornes", "tags-en-frontmatter",
        "quote-sans-reponse", "reponses-en-attente", "tag-inline-hors-whitelist",
        "emoji-reserve-hors-tache", "tache-dans-journal", "retour-chariot-en-phrase",
        "tache-doublon-probable", "jalon-avec-energie", "jalon-sans-prefixe",
        "dossier-non-frontiere", "jalon-franchissable",
    }
    manquantes = attendues - regles(constats)
    assert not manquantes, manquantes


def test_plafond_focus_pose_le_constat_sur_chaque_hub():
    constats, _ = lancer("vault-exemple")
    notes = {c.note for c in constats if c.regle == "focus-hors-plafond"}
    assert len(notes) == 4


@pytest.mark.parametrize("vault,code", [("vault-propre", 0), ("vault-exemple", 1)])
def test_mode_strict(vault, code, capsys):
    assert lv.main(["--vault", str(EXEMPLES / vault), "--strict", "--summary"]) == code


# -- règles unitaires ------------------------------------------------------

def note(fm: str, corps: str = "[[Client A]]\n") -> str:
    return f"---\n{fm.strip()}\n---\n{corps}"


BASE = """
type: documentation
status: active
source: ai
summary: "Une note de test correctement renseignée pour le lint."
created: 2026-10-01
"""


def test_note_bien_formee_ne_produit_rien():
    texte = note(BASE + 'sujet:\n  - "[[compta]]"\n')
    assert lv.controler("clients/client_a/x.md", texte, SUJETS, {}) == []


def test_wikilink_non_quote_en_yaml_est_une_erreur():
    texte = note(BASE + "sujet:\n  - [[compta]]\n")
    assert "sujet-yaml-imbrique" in regles(lv.controler("interne/x.md", texte, SUJETS))


def test_sujet_doit_etre_dans_le_dossier_et_pas_seulement_exister():
    texte = note(BASE + 'sujet:\n  - "[[Client A]]"\n')
    assert "sujet-hors-vocabulaire" in regles(lv.controler("interne/x.md", texte, SUJETS))


def test_summary_de_plus_de_50_mots():
    long = " ".join(["mot"] * 51)
    texte = note(BASE.replace("Une note de test correctement renseignée pour le lint.", long)
                 + 'sujet:\n  - "[[compta]]"\n')
    assert "summary-trop-long" in regles(lv.controler("interne/x.md", texte, SUJETS))


def test_projet_doit_viser_un_hub():
    texte = note(BASE + 'sujet:\n  - "[[compta]]"\nprojet: "[[Client A]]"\n')
    index = {"Client A": "moc"}
    assert "projet-cible-non-projet" in regles(lv.controler("interne/x.md", texte, SUJETS, index))


def test_retour_chariot_ignore_sur_une_note_humaine():
    corps = "[[Client A]]\n\nUne phrase coupée\nau milieu par un retour.\n"
    ia = note(BASE + 'sujet:\n  - "[[compta]]"\n', corps)
    humain = ia.replace("source: ai", "source: human")
    assert "retour-chariot-en-phrase" in regles(lv.controler("interne/x.md", ia, SUJETS))
    assert "retour-chariot-en-phrase" not in regles(lv.controler("interne/x.md", humain, SUJETS))


def test_quote_insensible_a_la_casse():
    corps = "[[Client A]]\n\n> [!Quote] Responsable\n> Un commentaire.\n"
    texte = note(BASE + 'sujet:\n  - "[[compta]]"\n', corps)
    assert "quote-sans-reponse" in regles(lv.controler("interne/x.md", texte, SUJETS))
    repondu = corps + "> > [!check] Réponse agent\n> > Traité.\n"
    texte = note(BASE + 'sujet:\n  - "[[compta]]"\n', repondu)
    assert "quote-sans-reponse" not in regles(lv.controler("interne/x.md", texte, SUJETS))


def test_note_endormie_passe_en_dette_froide():
    texte = note(BASE.replace("status: active", "status: archive"))  # sujet absent
    constats = lv.controler("interne/x.md", texte, SUJETS)
    assert constats and all(c.froid for c in constats)


def test_graphe_cycle_et_dependance_morte():
    taches = [
        {"note": "a.md", "ligne": 1, "statut": " ", "ids": ["t1"], "deps": ["t2"], "jalon": False},
        {"note": "a.md", "ligne": 2, "statut": " ", "ids": ["t2"], "deps": ["t1"], "jalon": False},
        {"note": "b.md", "ligne": 1, "statut": " ", "ids": ["t3"], "deps": ["inconnu"], "jalon": False},
    ]
    assert {"cycle-dependances", "dependance-morte"} <= regles(lv.controler_graphe(taches))

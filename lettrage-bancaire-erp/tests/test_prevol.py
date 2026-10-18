"""Tests du pré-vol : fonctions pures des contrôles bloquants et pré-rapport sur les exemples."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from controles.prevol import (
    AdaptateurFichier, EtatAvant, LigneEcriture, construire_rapport, charger_spec, correspond_doublon, equilibre,
    executer_prevol, exercice_ouvert, lettrage_solde_zero,
)

EX = Path(__file__).resolve().parents[1] / "exemples" / "prevol"
FIGE = datetime(2026, 10, 16, 9, 0, tzinfo=timezone.utc)


def test_equilibre():
    assert equilibre([LigneEcriture("411000", "x", debit=12.0), LigneEcriture("758000", "x", credit=12.0)])[0]
    assert not equilibre([LigneEcriture("606400", "x", debit=450.0), LigneEcriture("401000", "x", credit=445.5)])[0]


def test_exercice_en_cours_par_dessus_les_verrous():
    assert exercice_ouvert("2026-10-16", "2025-12-31", None, 2026)[0]
    ok, detail = exercice_ouvert("2025-11-30", None, None, 2026)     # aucun verrou : refus quand même
    assert not ok and "exercice en cours" in detail
    assert not exercice_ouvert("2026-01-15", "2026-01-31", None, 2026)[0]


def test_lettrage_doit_solder_a_zero():
    assert lettrage_solde_zero([-1812.0, 1800.0, 12.0])[0]
    assert not lettrage_solde_zero([-1812.0, 1800.0])[0]


def test_anti_doublon():
    piece = {"ref": "FA-2025-1187", "tiers_id": 140, "montant": 450.0}
    assert correspond_doublon(piece, "FA-2025-1187", None, None)
    assert correspond_doublon(piece, None, 140, 450.0)
    assert not correspond_doublon(piece, "AUTRE", 140, 451.0)


def _prevol(nom):
    return executer_prevol(charger_spec(EX / nom), AdaptateurFichier.depuis_fichier(EX / "grand_livre.json", "2026-10-16 11:00"),
                           genere_le=FIGE)


def test_demande_legitime_passe_tous_les_controles():
    rapport, controles = _prevol("demande_ecart_reglement.json")
    assert not [c for c in controles if c.statut == "fail"]
    assert "auteur d'origine du process" in rapport
    assert "Horodatage pré-vol : 2026-10-16T" in rapport


def test_demande_fautive_bloquee_sur_quatre_controles():
    rapport, controles = _prevol("demande_correction_anterieure.json")
    echecs = {c.nom for c in controles if c.statut == "fail"}
    assert echecs == {"exercice ouvert (et exercice EN COURS)", "anti-doublon", "équilibre débit = crédit",
                      "garde-fou lettrage (groupe = 0)"}
    assert "NE DOIT PAS être proposée" in rapport


def test_aucun_precedent_est_un_signal_d_alerte():
    from controles.prevol import OperationSpec
    spec = OperationSpec("S", 1, "geste", ["999999"], "2026-10-16")
    rapport = construire_rapport(spec, [], EtatAvant(), [], FIGE)
    assert "AUCUN PRÉCÉDENT TROUVÉ" in rapport and "signal d'alerte" in rapport


def test_simuler_est_volontairement_absent():
    with pytest.raises(NotImplementedError):
        AdaptateurFichier({}).simuler(None)

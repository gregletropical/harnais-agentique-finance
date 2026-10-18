"""Mise à jour incrémentale : fenêtre glissante M-2, remplacement par fenêtre et par clé, contrôle après chargement."""
import sqlite3

import pytest

from controles import increment as inc

T = "raw_test_increment"
COLS = [("id", "INTEGER"), ("d", "TEXT"), ("v", "REAL")]
F = {"colonne": "d", "depuis": "2026-07-01", "cle": ["id"]}


def test_debut_fenetre():
    assert str(inc.debut_fenetre("2026-09")) == "2026-07-01"
    assert str(inc.debut_fenetre("2026-01")) == "2025-11-01"


def test_complet_puis_delta():
    conn = sqlite3.connect(":memory:")
    with conn:
        inc.remplacer(conn, T, COLS, [(1, "2026-01-05", 10), (2, "2026-07-03", 20), (3, "2026-08-01", 30)])
    # delta : 2 supprimée de la source (dans la fenêtre), 3 corrigée, 4 nouvelle, 1 corrigée hors fenêtre (par sa clé)
    delta = [(1, "2026-01-05", 11), (3, "2026-08-01", 31), (4, "2026-09-02", 40)]
    with conn:
        r = inc.remplacer(conn, T, COLS, delta, F)
        inc.controler(conn, T, F, sum(1 for l in delta if l[1] >= F["depuis"]))
    assert r == {"supprimees": 3, "inserees": 3}
    assert conn.execute(f"SELECT id, v FROM {T} ORDER BY id").fetchall() == [(1, 11.0), (3, 31.0), (4, 40.0)]


def test_delta_sur_table_absente():
    with pytest.raises(RuntimeError, match="absente"):
        inc.remplacer(sqlite3.connect(":memory:"), "raw_absente", COLS, [], F)


def test_controle_apres_chargement():
    conn = sqlite3.connect(":memory:")
    inc.remplacer(conn, T, COLS, [(1, "2026-08-01", 1)])
    with pytest.raises(RuntimeError, match="attendues"):
        inc.controler(conn, T, F, 2)

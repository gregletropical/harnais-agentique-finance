"""Fixtures : une base SQLite en mémoire chargée et reconstruite depuis un dossier d'exemple."""
import shutil
import sqlite3
from pathlib import Path

import pytest

from controles import chargement, fin_de_cloture, pipeline

RACINE = Path(__file__).resolve().parent.parent
EXEMPLES = RACINE / "exemples"
REGLES = RACINE / "regles"
P = "2026-03"


def construire(exemple: Path, regles: Path = REGLES, controles: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    chargement.charger(conn, exemple, P, regles)
    pipeline.executer(conn, P, exemple, verbeux=False)
    if controles:
        fin_de_cloture.controles_mois(conn, P, exemple, regles)
    return conn


@pytest.fixture
def base_conforme():
    conn = construire(EXEMPLES / "mois_conforme")
    yield conn
    conn.close()


@pytest.fixture
def base_ecart():
    conn = construire(EXEMPLES / "mois_en_ecart")
    yield conn
    conn.close()


@pytest.fixture
def regles_copie(tmp_path):
    """Copie modifiable des référentiels, pour simuler une décision ou un registre périmé."""
    cible = tmp_path / "regles"
    shutil.copytree(REGLES, cible)
    return cible

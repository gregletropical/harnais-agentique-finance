"""Outillage commun de la recette : sentinelles réseau et disque, exemples chargés, mutation éventuelle."""
from __future__ import annotations

import builtins
import json
import os
import socket
import sys
from pathlib import Path

import pytest

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent
sys.path.insert(0, str(ICI))

import mutations  # noqa: E402

mutations.appliquer(os.environ.get("RECETTE_MUTATION"))

from controles import regles_tri  # noqa: E402
from controles.ingestion import analyser  # noqa: E402

EXEMPLES = RACINE / "exemples"
MAILS = EXEMPLES / "mails"
MANIFESTE = json.loads((MAILS / "manifeste.json").read_text(encoding="utf-8"))["cas"]
BRUTS = {c["fichier"]: (MAILS / c["fichier"]).read_bytes() for c in MANIFESTE}
CONF = json.loads((EXEMPLES / "boite_exemple.json").read_text(encoding="utf-8"))
REGLES = regles_tri.charger()


def message(fichier: str):
    return analyser(BRUTS[fichier], fichier)


class Sentinelles:
    """Toute connexion réseau et tout `open()` pendant le bloc sont interceptés et comptés.

    Les compteurs sont la mesure ; `test_b0_sentinelles_crient` prouve qu'ils ne
    sont pas morts en les déclenchant volontairement.
    """
    def __init__(self):
        self.reseau = 0
        self.disque = 0
        self._socket, self._open = socket.socket, builtins.open

    def __enter__(self):
        sentinelle = self

        class SocketInterdit(socket.socket):
            def connect(self, adresse):
                sentinelle.reseau += 1
                raise PermissionError(f"réseau interdit vers {adresse}")

            def connect_ex(self, adresse):
                sentinelle.reseau += 1
                raise PermissionError(f"réseau interdit vers {adresse}")

        def open_interdit(*a, **k):
            sentinelle.disque += 1
            raise PermissionError("accès disque interdit pendant la lecture")

        socket.socket = SocketInterdit
        builtins.open = open_interdit
        return self

    def __exit__(self, *exc):
        socket.socket, builtins.open = self._socket, self._open
        return False


@pytest.fixture
def sentinelles():
    return Sentinelles()


@pytest.fixture(scope="session")
def conf():
    return CONF

"""Contrôle de la recette elle-même : chaque mutation volontaire du code doit faire échouer au moins un test.

Un PASS de la recette n'est donc pas un silence. La recette est relancée dans un sous-processus,
avec la mutation choisie par la variable RECETTE_MUTATION (cf. `mutations.py`).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

from conftest import RACINE
from mutations import MUTATIONS


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_mutation_detectee(mutation):
    env = {**os.environ, "RECETTE_MUTATION": mutation}
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header",
                        "tests/test_recette_adverse.py", "tests/test_gestes_interdits.py"],
                       cwd=RACINE, env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 1, f"mutation {mutation} non détectée :\n{r.stdout[-1500:]}"
    echecs = re.search(r"(\d+) failed", r.stdout)
    assert echecs and int(echecs.group(1)) >= 1, r.stdout[-1500:]

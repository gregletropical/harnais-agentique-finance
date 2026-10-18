#!/usr/bin/env python3
"""
vault_commit.py — Point d'entrée de commit propre au second cerveau.

Ce fichier n'est qu'une ENVELOPPE : tout le moteur vit dans `commit_guard.py`
(même dossier), générique, appelable depuis n'importe quel dépôt. Ici ne reste
que la configuration propre au vault — c'est le patron à reproduire pour
chaque dépôt d'une organisation (un dépôt par frontière de partage, cf.
README § Vers le multi-utilisateurs).

Usage (depuis la racine du vault) :
    python controles/vault_commit.py --register --label "claude-poste"
    python controles/vault_commit.py --commit --push --id <sid> -m "msg" -- <fichiers>
    python controles/vault_commit.py --release --id <sid>
"""

from __future__ import annotations

import sys
from pathlib import Path

# Pas de `__pycache__/` laissé par l'import du moteur : dans un dépôt sans
# .gitignore, il apparaîtrait au résidu.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import commit_guard as cg  # noqa: E402

# Tout ce qui est propre au vault tient ici.
CONFIG = cg.Config(
    commande="python controles/vault_commit.py",
    commande_courte="vault_commit.py",
    designation="ce vault",
    variable_session="AGENT_SESSION_ID",
    # Le vault a toujours un amont : son absence est une anomalie (code 1).
    sans_amont_code=1,
    sans_amont_message="Branche sans amont : rien à synchroniser, push impossible.",
    prefixe_tmp="vault-rebase-",
    afficher_depot=False,
    option_repo=False,
)


def main() -> int:
    return cg.main(CONFIG)


if __name__ == "__main__":
    sys.exit(main())

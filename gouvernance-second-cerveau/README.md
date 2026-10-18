# Gouvernance d'un second cerveau écrit par plusieurs agents IA

## 1. Le cas d'usage en conditions réelles

En DAF externalisé, je tiens un second cerveau Obsidian d'environ 1 000 notes Markdown, versionné sous Git (un *second cerveau*, ou *vault* dans le vocabulaire d'Obsidian, est une base de notes personnelle reliées entre elles) : procédures, comptes rendus, hubs de chantier par client (un *hub* est la note centrale d'un chantier, vers laquelle pointent toutes les notes qui en relèvent), tâches et décisions. Ce référentiel est aussi le **contexte de travail de mes agents IA** : ce qu'ils y lisent conditionne ce qu'ils produisent, et ce qu'ils y écrivent devient le contexte de la session suivante.

Plusieurs écrivains y travaillent en même temps : deux ou trois sessions d'agents en parallèle sur mon poste (Claude Code, OpenCode), plus un agent autonome sur un serveur, qui écrit sans supervision et synchronise régulièrement son travail. Un seul humain, déjà trois écrivains.

Deux risques en découlent. Le premier est la **dégradation silencieuse du classement** : une note mal renseignée n'est pas cassée, elle est invisible, et personne ne s'en aperçoit. Le second est la **collision d'écriture** : trois fois en un mois, une fin de session a enregistré dans Git le travail d'une autre session sous un message qui ne le décrivait pas. Rien n'a été perdu, mais un historique qui ment ne se répare pas.

J'y réponds par deux principes. **« Le dossier ne classe pas, il cloisonne »** : un dossier n'existe que s'il matérialise une frontière de partage (un client lira un jour son dossier) ; tout le classement est dans les properties du frontmatter (l'en-tête de métadonnées de chaque note), à vocabulaire fermé. Et **des contrôles mécaniques plutôt que des consignes** : l'interdiction de `git add -A` était écrite dans les instructions de l'agent, il l'a violée trois fois en un mois ; elle n'a plus été violée depuis qu'un hook (un script que Claude Code exécute avant chaque commande) refuse la commande avant exécution.

## 2. Ce que ce dossier montre — et ce qu'il ne montre pas

Je ne présente pas de maquette de production : le référentiel réel contient des données clients et des éléments personnels, je ne peux partager ni lui, ni l'accès aux environnements où il tourne.

Ce que je publie :

- les **fichiers réels**, adaptés et anonymisés : le lint du référentiel (`controles/lint_vault.py` ; un *lint* est un contrôle automatique qui relit les notes et signale celles qui enfreignent une règle), le garde-fou de commit (`controles/commit_guard.py`), les deux hooks Claude Code, un exemple de configuration ;
- un **extrait réécrit** du fichier d'instructions de l'agent et la **doctrine** d'écriture concurrente tirée de l'expérience ;
- un **référentiel de règles** séparé du moteur (`regles/referentiel.yaml`) ;
- deux **mini-vaults 100 % synthétiques** (un client fictif, des sujets génériques) pour voir les règles se déclencher, et des tests qui le prouvent.

Ce que j'ai retiré : les noms de clients, de personnes et de dossiers réels, les règles propres à un client (généralisées), le programme de synchronisation de l'agent du serveur (il dépend d'un hébergement précis), et tout ce qui touche à la vie privée.

## 3. Le déroulé du workflow

| Étape | Qui | Ce qui se passe | Contrôle |
|---|---|---|---|
| 1. Démarrage de session | agent | s'enregistre au registre de sessions (`vault_commit.py --register`), reçoit un briefing calculé : questions en attente, tâches qui lui sont assignées, ce que l'agent du serveur a produit | registre dans `.git/agent-sessions/`, expiration sur 12 h d'**inactivité** |
| 2. Travail | agent | écrit des notes selon le schéma de properties, des tâches à leur source (le hub, jamais un journal), des dépendances `🆔`/`⛔` (marqueurs du plugin Tasks d'Obsidian) | le harnais refuse d'éditer un fichier modifié depuis sa lecture |
| 3. Édition d'un hub | hook `bail_note.py` | pose un bail (une réservation temporaire et non bloquante de la note) ; si une autre session tient déjà ce hub, avertit l'agent et l'humain **sans bloquer** | information, jamais de verrou |
| 4. Toute commande shell | hook `block_git_add_all.py` | refuse `git add -A`, `git add .`, `git commit -a` avant exécution | refus dur |
| 5. Avant de rendre la main | agent + lint | lance `lint_vault.py --changed` ; corrige les ERROR | ERROR = la note ment, WARN = incomplète, INFO = signal |
| 6. Commit | `commit_guard.py` | stage par chemins explicites, refuse si l'index contient déjà le travail d'un autre, refuse `--all` dès deux sessions, affiche le résidu, ajoute le trailer `Session:` (une ligne de métadonnée en pied du message de commit) | code 2 = refus délibéré |
| 7. Push | `commit_guard.py` | `fetch`, puis refus si l'amont a touché un fichier du lot ; push différé si l'amont touche le travail pas encore enregistré dans Git d'une autre session ; sinon rebase dans un worktree temporaire et push | jamais d'`--autostash`, jamais de `--force` |
| 8. Arbitrages | **humain** | pose les `focus` (3 au maximum), donne le GO (validation explicite) sur les jalons, répond aux encarts `[!todo] Réponse`, tranche les codes 2 | le lint signale, l'humain décide |

**En cas d'exception.** Un code 2 n'est pas une panne : le commit local est fait, rien n'est perdu, et le message dit quoi lire (`git log -p base..amont -- <fichier>`) avant de relancer avec `--accepter-amont` ou d'arbitrer. Un ERROR du lint bloque en mode `--strict` (hook pre-commit possible avec `--staged`). L'agent du serveur ne peut écrire que dans le journal du jour et la boîte de réception : son programme de synchronisation refuse d'enregistrer dans Git tout autre chemin, et sa production est marquée pour être rangée en session.

## 4. La compétence démontrée

Faire écrire plusieurs agents IA dans un même référentiel sans qu'ils l'abîment : chaque règle est binaire et vérifiée par une machine, donc applicable par un modèle léger sans jugement. Traiter le référentiel comme le contexte du modèle (*context engineering*) : un vocabulaire fermé, un fait écrit une seule fois à son étage, une vue calculée plutôt qu'une mémoire tenue à la main. Tracer qui a écrit quoi et par quelle session, et réserver à l'humain les arbitrages : priorités, validations, conflits. C'est la gouvernance qu'il faut à un second cerveau d'entreprise avant d'y brancher des agents.

## 5. Contenu du dossier

| Fichier | Rôle |
|---|---|
| `instructions/AGENTS.extrait.md` | extrait réécrit des instructions de l'agent : dossier-frontière, properties à vocabulaire fermé, tâches et dépendances, règle de commit, périmètre de l'agent autonome |
| `instructions/doctrine-ecriture-concurrente.md` | les neuf principes de l'écriture concurrente, les options écartées, les limites |
| `regles/referentiel.yaml` | vocabulaires fermés et paramètres de tous les contrôles (le moteur n'en contient aucun) |
| `regles/catalogue-regles.md` | les 61 règles du lint (26 ERROR, 27 WARN, 8 INFO) et ce que chacune attrape |
| `regles/claude-settings.exemple.json` | branchement des deux hooks dans Claude Code |
| `regles/gitattributes.exemple` | `merge=union` limité aux journaux append-only |
| `controles/lint_vault.py` | le lint, en lecture seule : frontmatter, vocabulaires, graphe de tâches, plafonds, structure |
| `controles/commit_guard.py` | garde-fou de commit multi-sessions (registre, index, synchro avant push, provenance) |
| `controles/vault_commit.py` | configuration du garde-fou pour le vault : le patron d'un dépôt par frontière |
| `controles/hooks/block_git_add_all.py` | hook `PreToolUse` qui refuse le staging aveugle |
| `controles/hooks/bail_note.py` | hook `PreToolUse` qui informe qu'une autre session tient un hub |
| `exemples/vault-propre/` | mini-vault synthétique conforme : 0 ERROR, 0 WARN |
| `exemples/vault-exemple/` | le même, plus des notes volontairement fautives |
| `tests/` | 45 tests : règles du lint, hook, bail, garde-fou de commit sur de vrais dépôts git jetables |

## 6. Essayer

Depuis ce dossier, avec Python 3.11+ et [uv](https://docs.astral.sh/uv/) :

```bash
uv run python controles/lint_vault.py --vault exemples/vault-propre --summary
uv run python controles/lint_vault.py --vault exemples/vault-exemple --strict
uv run pytest
```

Sans uv : `pip install pyyaml pytest`, puis les mêmes commandes avec `python`.

Résultat attendu sur le vault propre :

```
lint : 13 notes scannées, 0 avec au moins un constat au seuil WARN
  ERROR    0   WARN    0
  (1 constat(s) sous le seuil masqué(s))
```

Sur le vault fautif, code de sortie 1 et, entre autres :

```
lint : 20 notes scannées, 9 avec au moins un constat au seuil WARN
  ERROR   21   WARN   15
  · focus-hors-plafond              4
  · id-en-double                    2
  · tache-doublon-probable          2
  ...

clients/client_a/Relance fournisseurs.md
  [ERROR] type-supprime — `note` a été supprimé du référentiel → `draft-prompt / documentation selon le geste`
  [ERROR] sujet-yaml-imbrique — `- [[x]]` non quoté parse en liste imbriquée — écrire `- "[[x]]"`
  [ERROR] sujet-hors-vocabulaire — `finance` n'est pas une note de `ressources/sujets/`
  [ERROR] status-invalide — `en-cours` (attendu : active | archive | avorte | done | incubation | slowburn | standby)
  [WARN ] source-absent

clients/client_a/Rapprochement bancaire mensuel.md
  [ERROR] recurrence-invalide — `quotidienne` (attendu : annuelle | hebdomadaire | mensuelle | trimestrielle)
  [ERROR] dependance-morte — ligne 19 : `⛔ zz9999` ne correspond à aucun `🆔` du vault
  [ERROR] cycle-dependances — cycle : rbm003 → rbm004 → rbm003
  ...

journal/2026-10-16.md
  [WARN ] tache-dans-journal — 1 tâche(s) ouverte(s) dans un journal — une tâche vit dans son hub ; ...
  [WARN ] retour-chariot-en-phrase — 1 ligne(s) coupée(s) en cours de phrase — ...
```

`--seuil INFO --limite 0` affiche aussi les signaux (jalon à valider, encart de réponse vide, sous-dossier hors frontière). Pour voir le hook refuser une commande :

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"cd depot && git add -A"}}' | python controles/hooks/block_git_add_all.py
```

Les tests du garde-fou montent un dépôt nu (le serveur) et deux clones (le poste, un autre écrivain) dans un dossier temporaire, et vérifient les cinq comportements clés : `--all` refusé à deux sessions, index déjà chargé refusé, commit par chemins avec trailer et résidu intact, refus de pousser si l'amont a touché le lot, rebase à part puis push si l'amont a touché autre chose.

## Vers le multi-utilisateurs : un cadrage, pas un pilote

Mon référentiel a un seul écrivain humain. J'ai **cadré** le passage à une équipe (benchmark, options, décisions), **pas éprouvé** : aucun pilote multi-utilisateurs n'a tourné.

Le fait qui commande tout : **git n'a pas de droit de lecture plus fin que le dépôt**. Quiconque clone lit tout l'historique, dossiers « interdits » compris. J'ai comparé trois architectures :

| Option | Verdict |
|---|---|
| Un dépôt unique exposé par dossier en lecture seule | tient pour des lecteurs, pas pour des écrivains : qui écrit doit cloner, donc tout lire |
| Un vault par utilisateur | rien n'est commun : un réseau de seconds cerveaux personnels, pas un second cerveau d'entreprise |
| **Vault fédéré : un dépôt par frontière** | retenu comme cible : le vault d'une personne est l'assemblage des dépôts qu'elle a le droit de lire |

« Le dossier cloisonne » devient « le dossier-frontière est un dépôt » : la frontière cesse d'être une convention pour devenir un droit d'accès appliqué par le serveur, c'est-à-dire un contrôle et non une consigne. Properties, vues et lint fonctionnent à l'identique sur l'assemblage.

Ce que cela impose, sur le papier — c'est un cadrage, pas un pilote réalisé :

- une instance d'agent par utilisateur, lancée sur son seul assemblage (filtrer avant de lire, jamais après) ;
- des équipes sur le serveur de dépôts pour filtrer les lectures, et `CODEOWNERS` avec protection de branche : tout le monde lit la doctrine commune, seuls ses propriétaires la modifient ;
- un contrôle qui interdit à une note d'une frontière large de pointer vers une frontière plus étroite (un lien fuit par son titre) ;
- un garde-fou de commit capable d'écrire dans plusieurs dépôts, d'où sa séparation en moteur générique (`commit_guard.py`) et configuration par dépôt (`vault_commit.py`) ;
- si la concurrence sur les tâches devient le point de douleur, les tâches en base de données, le savoir restant en fichiers.

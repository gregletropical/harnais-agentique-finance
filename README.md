# Harnais agentique pour la finance d'entreprise

Ce dépôt montre comment je structure des workflows d'agents IA pour des missions de direction financière : ce que l'agent lit, les règles qu'il applique, les contrôles qui l'empêchent de se tromper en silence, et les points où un humain valide.

Je suis DAF externalisé, après 18 ans de contrôle de gestion et de finance en entreprise. Depuis février 2025, je construis mes propres outils avec des agents (Claude Code, OpenCode, un agent autonome sur serveur), et je les utilise chaque jour en mission : comptabilité, clôtures mensuelles, pilotage, revue de boîtes mail.

## Ce que ce dépôt est, et ce qu'il n'est pas

**Ce n'est pas une maquette de production.** Je ne peux partager ni données client, ni accès à un environnement client, et je ne le ferai pas. Aucun dossier ne se connecte à un système réel.

**C'est un partage d'approche.** Chaque dossier part d'un cas d'usage réel et publie les fichiers qui font le workflow : les instructions que lit l'agent, les définitions de règles, les scripts de lint et de contrôle, les garde-fous. Les références réelles sont anonymisées. Des exemples entièrement synthétiques permettent de lancer les contrôles et de voir une règle se déclencher.

## Le principe commun : des contrôles, pas des consignes

Un agent qui écrit dans un référentiel, une comptabilité ou une boîte mail finit par se tromper. Une consigne dans un prompt ne l'en empêche pas ; un contrôle mécanique, si. Chaque dossier applique la même boucle :

1. **Des règles explicites**, écrites dans des fichiers que l'agent et l'humain lisent de la même façon.
2. **Des contrôles automatiques** avant toute action qui engage : lint, pré-vol, cadrage, recette.
3. **Les exceptions remontées à l'humain**, avec ce qu'il faut pour trancher, plutôt qu'une décision prise par défaut.
4. **Un GO humain explicite et tracé** avant toute écriture en production.
5. **Une trace rejouable** : ce qui a été décidé, par qui, sur quelle base.

## Les quatre cas

| Dossier | Cas d'usage réel | Ce qu'il démontre |
|---|---|---|
| [`gouvernance-second-cerveau/`](gouvernance-second-cerveau/) | Un second cerveau d'environ 1 000 notes Markdown, versionné sous Git, dans lequel plusieurs agents écrivent en parallèle | Faire écrire plusieurs agents dans un même référentiel sans qu'ils l'abîment : vocabulaires fermés, lint de 61 règles, garde-fou de commit pour sessions concurrentes |
| [`lettrage-bancaire-erp/`](lettrage-bancaire-erp/) | La routine comptable du matin dans l'ERP d'un éditeur de logiciels : rapprochement bancaire et imputations | Un agent qui écrit en comptabilité de production sans perte de contrôle : règles testées, contrôle de l'existant, pré-vol, exceptions arbitrées, GO tracé |
| [`cloture-mensuelle-datawarehouse/`](cloture-mensuelle-datawarehouse/) | L'entrepôt de données finance d'une agence de services numériques, alimenté par API depuis quatre sources | Un P&L mensuel fiable sans outil BI propriétaire : pipeline par étapes, contrôles de cadrage, pré-vol de fin de clôture, recette métier |
| [`ingestion-mail-anti-injection/`](ingestion-mail-anti-injection/) | Des agents qui lisent des boîtes mail professionnelles pour en extraire du contexte | Traiter un contenu non fiable comme une surface d'attaque : lecteur isolé, sorties à taxonomie fermée, gestes interdits, recette adverse |

Chaque dossier a son README : le cas d'usage, ce que le dossier montre et ne montre pas, le déroulé du workflow, la compétence démontrée, et la commande pour lancer les contrôles sur les exemples.

## Indépendance du modèle

Les instructions sont des fichiers Markdown et les contrôles sont du Python : rien ne dépend d'un fournisseur de modèle. Le même fichier d'instructions est lu par deux harnais différents (Claude Code et OpenCode, ce dernier multi-modèles via OpenRouter). Mon agent autonome tourne sur mon serveur avec un modèle à poids ouverts, aujourd'hui appelé via OpenRouter et remplaçable par un modèle auto-hébergé sans toucher au harnais. C'est la condition pour qu'une entreprise garde la maîtrise de son contexte, quel que soit le modèle qu'elle utilise demain.

## Par où commencer

Une commande par dossier suffit pour voir une règle se déclencher : le lint sur le vault volontairement fautif (`gouvernance-second-cerveau`), le rapport du matin sur un relevé fictif (`lettrage-bancaire-erp`), la clôture d'un mois en écart, bloquée avant diffusion (`cloture-mensuelle-datawarehouse`), la passe complète sur des mails piégés (`ingestion-mail-anti-injection`). Chaque README donne la commande exacte et la sortie attendue. L'ensemble compte 395 tests, tous verts.

## Essayer

Chaque dossier est autonome. Python 3.11 ou plus ; les dépendances éventuelles sont déclarées dans le `pyproject.toml` du dossier.

```bash
cd <dossier>
uv run pytest        # ou : python -m pytest
```

## Auteur

Grégory Mazerat, DAF externalisé, FP&A, data et context engineering. [LinkedIn](https://www.linkedin.com/in/gregorymazerat/)

Licence MIT.

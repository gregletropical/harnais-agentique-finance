# Lettrage bancaire piloté par un agent, sous contrôle humain

## 1. Le cas d'usage en conditions réelles

Chez un client éditeur de logiciels, je tiens en DAF externalisé une routine comptable quotidienne pilotée par un agent IA dans l'ERP (Odoo).

Chaque matin ouvré, après la synchronisation bancaire, l'agent collecte les lignes bancaires non rapprochées de chaque compte bancaire, les confronte aux règles d'imputation et de lettrage, contrôle l'existant (factures ouvertes, historique des opérations similaires, paiements par lot, doublons, soldes bancaires), puis classe chaque ligne : exécutable, à arbitrer, ou exception.

Il me soumet un rapport. Rien ne s'écrit sans mon GO explicite, que l'agent recopie mot pour mot dans le compte rendu. Il exécute ensuite les seules lignes exécutables, en recalculant chaque garde-fou juste avant chaque geste, relit l'ERP après chacun, et s'arrête à la première anomalie.

Toute écriture qui sort de ce périmètre passe par un protocole de pré-vol : recherche d'un précédent chez le client, état des comptes, contrôles bloquants, pré-rapport validé.

C'est un lint de comptabilisation : les règles sont explicites, versionnées et testées, et ce que la machine ne peut pas trancher remonte à un humain avec les faits et les options.

## 2. Ce que ce dossier montre — et ce qu'il ne montre pas

Ce dossier n'est pas une maquette de production. Je ne peux partager ni données client, ni accès à un environnement client.

Il montre la structure du workflow à travers des fichiers réels, adaptés et anonymisés :

- les instructions que lit l'agent (commande, procédure, protocole, règles de conduite) ;
- les règles de classement et le paramétrage des catégories d'imputation, avec leur nombre, leur nature et leurs garde-fous d'origine ;
- les contrôles : rapport du matin, plan d'écriture, pré-vol, hook de garde-fou.

Les tiers, libellés, montants, comptes auxiliaires et décisions sont fictifs ; les comptes sont ceux du plan comptable général.

Il ne contient aucun connecteur vers un système réel. Là où le code d'origine lit l'ERP, `controles/source_fichier.py` lit un fichier d'exemples synthétiques en respectant exactement le même contrat (`regles.classement.Source`). Là où il écrit dans l'ERP, `controles/plan_ecriture.py` produit un plan d'écriture et s'arrête : en production, l'exécution passe par l'API de l'ERP, après GO, par un adaptateur non publié.

Le suivi des activités et mentions de l'équipe du client (étape 2 de la routine) est décrit dans les instructions, mais son script n'est pas publié : il ne fait que lire le fil de discussion des pièces dans l'ERP.

## 3. Le déroulé du workflow

| # | Étape | Qui | Point de contrôle |
|---|---|---|---|
| 1 | Collecte des lignes non rapprochées, des pièces ouvertes, des lots, des précédents, des soldes | Script, lecture seule | Fraîcheur de la synchronisation de chaque banque |
| 2 | Continuité des soldes : une ligne qui compense exactement un écart apparu entre solde banque et solde ERP sort des exécutables | Script | Exception « doublon probable », avant tout classement |
| 3 | Classement de chaque ligne en 11 classes, regroupées en 3 familles | Script (`regles/`) | Tolérance nulle, refus sur ambiguïté, seuils de coïncidence |
| 4 | Contrôle des rapprochements faits la nuit par le robot de l'ERP, compteurs de dérive | Script | Alertes dans le rapport |
| 5 | Analyse des cas nouveaux à arbitrer et des exceptions, checklist fermée en 7 points, en parallèle | Agent, lecture seule | Conclusion argumentée, niveau de certitude |
| 6 | Rapport unique : évident, arbitrages, sollicitations, suivi, dérive | Agent | **GO de l'utilisateur, en conversation** |
| 7 | Plan d'écriture : sélection des exécutables, ordre A, A′₁, B, N, R, I, garde-fous recalculés | Script | GO cité mot pour mot ; état de moins de 2 heures |
| 8 | Exécution par l'API, relecture après chaque geste | Adaptateur ERP (non publié) | Arrêt à la première anomalie, aucune relance |
| 9 | Arbitrages hors script : script dédié, simulation d'abord | Agent | **Pré-vol** : 8 portes, pré-rapport, GO consigné |
| 10 | Traçabilité : compte rendu, notes à la première personne de l'utilisateur, activité de validation au comptable pour tout lettrage par déduction | Agent | Hook `PreToolUse` qui refuse une écriture ERP sans pré-rapport valide |

En cas d'exception, rien ne s'écrit : la ligne remonte dans le rapport avec son motif et ses candidats. Une catégorie nouvelle se propose à l'utilisateur, elle n'entre dans le code qu'après arbitrage et avec ses tests. Un membre de l'équipe du client n'est sollicité que si un élément extérieur manque.

Les trois familles :

- **Exécutable** : A (référence citée, montant = reste dû), A′₁ (combinaison unique et triviale chez un tiers identifié), B (lot de paiements), N (virement groupé), R (remboursement d'un trop-perçu), I (catégorie d'imputation actée).
- **À arbitrer** : A′₂ (combinaison unique mais coïncidence possible), C (règlement partiel), E (échéancier).
- **Exception** : P (ligne déjà partiellement traitée), D (tiers inconnu, incertain ou ambigu, montant hors tolérance, combinaisons multiples, double paiement, doublon, exercice clos, catégorie hors plafond ou hors périmètre).

## 4. La compétence démontrée

Faire écrire un agent en production comptable sans perdre le contrôle.

Les règles sont dans le code, binaires et testées, pas dans une consigne qu'un modèle interprète ; chaque règle porte l'incident qui l'a fait naître.

Les décisions humaines sont isolées, préparées avec les faits et les options, et tracées par la citation exacte du GO.

La routine est rejouable à l'identique, indépendante du modèle qui la pilote, et portable d'un ERP à l'autre par un adaptateur à cinq primitives.

## 5. Contenu du dossier

| Fichier | Rôle |
|---|---|
| `instructions/commande-routine-matin.md` | Commande que lance l'agent chaque matin (format commande Claude Code) |
| `instructions/routine-matinale.md` | Procédure autoportante en 6 étapes, du premier passage à la formalisation |
| `instructions/specification-classement.md` | Classes, seuils, identification du tiers, garde-fous, ce que le script ne fait pas |
| `instructions/protocole-prevol.md` | Protocole des 8 portes avant toute écriture en production, et son incident fondateur |
| `instructions/regles-de-conduite-erp.md` | Première personne de l'utilisateur, sollicitation d'un tiers seulement si bloqué, GO consigné, discipline d'exécution |
| `regles/categories.py` | Paramétrage : seuils, comptes techniques, 19 catégories d'imputation avec leurs garde-fous |
| `regles/classement.py` | Classement pur, sans réseau : extraction du libellé, identification du tiers, combinaisons exactes, échéanciers, continuité des soldes |
| `controles/source_fichier.py` | Source de données lue dans les exemples, à la place du connecteur ERP |
| `controles/etat.py` | Commande unique : produit le rapport Markdown soumis pour GO, et l'état JSON |
| `controles/plan_ecriture.py` | Plan d'écriture (simulation) : garde-fous recalculés, arrêt à la première anomalie, GO consigné |
| `controles/prevol.py` | Pré-vol : précédents, état avant, contrôles bloquants, pré-rapport ; `simuler` volontairement absente |
| `controles/garde_fou_prevol.py` | Hook `PreToolUse` : refuse une écriture ERP sans pré-rapport récent portant un GO cité ; angles morts documentés |
| `exemples/releve.json` | 33 lignes bancaires fictives, construites pour faire jouer chaque règle |
| `exemples/referentiel.json` | Référentiel fictif : journaux, tiers, pièces ouvertes, lots, précédents, soldes |
| `exemples/rapport_du_matin.md` | Rapport produit sur ces exemples, tel que l'agent le soumettrait |
| `exemples/prevol/` | Grand livre fictif, une demande légitime et une demande fautive |
| `tests/` | 59 tests pytest : chaque règle, chaque garde-fou, le bout en bout |

## 6. Essayer

Depuis ce dossier, avec Python 3.11 ou plus (aucune dépendance hors bibliothèque standard pour les contrôles) :

```bash
python controles/etat.py --maintenant "2026-10-16 07:00:00"
```

Résultat attendu : le rapport de `exemples/rapport_du_matin.md` — 33 lignes, dont 16 exécutables, 3 à arbitrer et 14 exceptions ; une alerte de synchronisation sur l'une des banques ; une alerte de continuité qui sort une ligne réimportée des exécutables (sans ce contrôle, une catégorie actée l'aurait imputée) ; 2 anomalies sur les rapprochements de la nuit.

Plan d'écriture après GO, sur l'état produit :

```bash
python controles/etat.py --maintenant "2026-10-16 07:00:00" --sortie sortie/
python controles/plan_ecriture.py --etat sortie/2026-10-16_0700_etat.json --maintenant "2026-10-16 07:10:00" --go "GO pour la section 1"
```

Résultat attendu : 16 gestes planifiés dans l'ordre, chacun avec ses garde-fous recalculés et ce qu'il faudra relire, et le GO cité.

Pré-vol :

```bash
python controles/prevol.py exemples/prevol/demande_ecart_reglement.json        # code 0 : contrôles passés
python controles/prevol.py exemples/prevol/demande_correction_anterieure.json  # code 1 : 4 contrôles bloquants en échec
```

Tests (pytest, déclaré dans `pyproject.toml`) :

```bash
uv run pytest        # ou : python -m pytest, avec pytest installé
```

Résultat attendu : `59 passed`.

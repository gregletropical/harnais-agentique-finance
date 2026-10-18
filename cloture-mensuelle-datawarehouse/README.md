# Clôture mensuelle d'un entrepôt de données finance

## 1. Le cas d'usage en conditions réelles

Pour une agence de services numériques cliente, j'ai conçu un entrepôt de données finance alimenté chaque mois par API depuis quatre sources : l'outil de gestion de projets et des temps, le CRM, le logiciel comptable et la paie.

L'entrepôt produit le P&L mensuel, le prévisionnel des ventes issu du CRM et les analyses de marge par client, sans outil de BI propriétaire : une base PostgreSQL en couches (brut, préparation, restitution, contrôles), des scripts Python et des référentiels versionnés dans Git.

La clôture mensuelle est un process récurrent piloté par une commande d'agent (Claude Code) : checklist guidée, pré-vol d'ouverture (bilan des sources avant toute extraction), chargements, arbitrages humains, pipeline, contrôles de cadrage (ventes, achats, paie contre comptabilité), contrôle de fin de clôture (le second pré-vol, avant diffusion), récapitulatif métier.

Le résultat le plus parlant n'est pas technique : la clôture a d'abord glissé de plusieurs semaines faute de déclencheur ; elle sort désormais le jour même (J+0), sans avoir changé la technique, grâce à un déclencheur daté et à un process instancié chaque mois.

## 2. Ce que ce dossier montre — et ce qu'il ne montre pas

Ce dossier n'est pas une maquette de production. Je ne peux partager ni les données du client, ni l'accès à ses environnements.

Il montre mon approche de la structuration d'un workflow agentique, à partir de fichiers réels adaptés et anonymisés :

- les **instructions de l'agent** (la commande de clôture, la chaîne canonique des étapes, la doctrine hub récurrent / itération enregistrée) ;
- les **référentiels et registres** qui portent les décisions humaines (taxonomie P&L, passage rubrique de paie vers compte, registres d'exceptions, ajustements du cutoff, c'est-à-dire de l'arrêté mensuel, projet par projet, du chiffre d'affaires et du coût produits, référentiel clients) ;
- les **contrôles**, réécrits en Python standard sur un schéma générique, avec la logique réelle : appariement par niveaux de preuve, tableaux de passage à résidu nul, registres qui expliquent sans forcer, oracle M-1 (l'instantané figé des tables de restitution du mois précédent, référence de non-régression des mois passés) ;
- des **exemples 100 % synthétiques** (un mois fictif, montants inventés) pour voir chaque contrôle passer, et échouer.

Aucun connecteur n'est publié. Là où le système réel appelle une API en lecture seule puis fige l'extrait sur disque, la fonction `lire_source()` lit un fichier d'exemple : l'extrait figé est le dossier d'exemple. Le système réel tourne sur PostgreSQL avec un schéma par couche ; la démonstration utilise SQLite, où la couche devient un préfixe de table (`raw_`, `stg_`, `mart_`, `ctrl_`).

## 3. Le déroulé du workflow

| Étape | Qui | Ce qui se passe | En cas d'exception |
|---|---|---|---|
| 0. Pré-vol d'ouverture | script, puis humain | Bilan des sources : mois attendu, dépôt de paie couvrant le mois, extraits contre registre des chargements, mode complet ou delta par source | Manquant : arrêt. Incohérence (mois inattendu, mois déjà chargé) : présentée à l'humain. **GO humain sur le mois obligatoire** pour continuer |
| 1. Chargement | agent | Le cutoff des projets d'abord, avec son contrôle bloquant (total reconstitué contre total de l'outil, par entité et période), puis les autres sources ; corrections CRM appliquées depuis un registre versionné | Contrôle en échec : rien d'autre n'est chargé. Un écart que l'outil ne compte pas reçoit, sur décision humaine, un ajustement et une exception motivée ; une exception périmée bloque aussi |
| 2. Arbitrages | agent prépare, humain décide | Rattachement des nouveaux clients et projets au référentiel ; une garde bloque le pipeline si un arbitrage prioritaire manque ou n'est pas appliqué | L'agent ne remplit jamais la colonne `decision` et n'écrit jamais dans le référentiel à la main |
| 3. Pipeline | agent | Chaîne complète brut → préparation → restitution, jamais une étape isolée ; référentiels relus à chaque passage | Compte sans poste P&L, rubrique de paie sans compte, deal à dates inversées : arrêt, rapport, décision humaine |
| 4. Contrôles du mois | agent | Cadrage ventes, cadrage achats, cadrage paie, vraisemblance contre les douze mois précédents, deals disparus du CRM | Pièces à instruire et disparitions : constats présentés. Résidu de passage non nul, écart de paie non expliqué, mois hors bornes : bloquants |
| 5. Fin de clôture | script | Contrôle de fin de clôture, le pré-vol avant diffusion : date de clôture, couverture paie, cadrage paie, production sans groupe client, arbitrages en attente, contrôles calculés, oracle M-1 sur les mois passés | Verdict ÉCHEC : diffusion bloquée, l'échec se présente à l'humain, il ne se contourne pas |
| 6. Récapitulatif | agent, puis humain | Chiffres du mois à côté de l'historique, marqués NON DIFFUSABLES tant que 5 n'est pas conforme ; l'humain franchit le jalon « données publiables » | — |
| 7. Clôture de la clôture | agent | Instantané des marts (oracle de la clôture suivante), enregistrement dans Git des seuls référentiels modifiés, ligne datée au journal du hub récurrent | Instantané refusé si la date de clôture n'est pas la fin du mois ou s'il existe déjà |

Le principe qui traverse tout : **l'agent prépare, l'humain décide**. Tout ce qui est déterministe revient à l'agent ; tout jugement métier (ajustement, rattachement, qualification d'un écart) revient à l'humain, et s'écrit dans un registre versionné avec sa cause, jamais en base.

## 4. La compétence démontrée

- Un pipeline de données financières dont un agent déroule les étapes, avec des **contrôles bloquants avant toute diffusion** et des tests qui font échouer chaque contrôle volontairement.
- Une doctrine de **tolérance zéro** : le contrôle rapporte « 0 écart non expliqué », chaque écart connu porte sa cause dans un registre, et un registre périmé bloque autant qu'un écart.
- Des **arbitrages sécurisés et tracés** : l'agent ne tranche rien, chaque décision humaine laisse une ligne versionnée, et l'itération mensuelle est un enregistrement qui ne se réécrit pas.
- Un process tenu à J+0 par un **déclencheur et une chaîne datée**, plutôt que par la technique.

## 5. Contenu du dossier

| Fichier | Rôle |
|---|---|
| `instructions/commande-cloture-mensuelle.md` | La commande d'agent : étapes, blocages attendus et quoi faire, table des décisions humaines, interdits |
| `instructions/chaine-canonique.md` | Le process : jour de référence, quatre phases, étapes avec qui / énergie / durée / dépendance / jour cible, jalons, règles dures, reprise hors cycle, pièges |
| `instructions/hub-recurrent-et-iteration.md` | La doctrine hub récurrent / note d'itération enregistrée, le modèle d'itération (les pictogrammes des lignes de tâches sont les marqueurs du plugin Tasks d'Obsidian), les enseignements anonymisés de deux itérations réelles |
| `regles/parametres.json` | Tolérances (arrondi technique, jamais matérialité), bornes de vraisemblance, seuils d'appariement, comptes et journaux |
| `regles/catalogue_controles.csv` | Les vingt contrôles : étape, nature (bloquant, constat, incohérence), module, ce qui bloque |
| `regles/taxonomie_pnl.csv`, `passage_rubrique_compte.csv` | Classement des comptes en postes P&L ; ventilation des rubriques de paie en comptes |
| `regles/groupes_clients.csv`, `xref_client_groupe.csv` | Référentiel analytique (MDM, gestion des données de référence : les clients et leurs rattachements), maintenu par la seule routine d'arbitrage |
| `regles/ajustements_cutoff.csv` | Ajustements du cutoff décidés par l'humain (annulation, neutralisation) |
| `regles/exceptions_totaux_outil.csv` | Registre des écarts que l'outil ne compte pas dans ses totaux |
| `regles/registre_exceptions_cadrage.csv` | Registre des écarts de paie expliqués (ouvert, résolu) |
| `regles/registre_anomalies_crm.csv` | Corrections CRM qui ne peuvent pas être faites à la source |
| `regles/ecarts_snap_qualifies.csv` | Écarts qualifiés de l'oracle M-1 (montant et cause obligatoires) |
| `regles/perimetre_cadrage_achats.csv` | Périmètre déclaré du cadrage des achats (comptes, tiers, projets internes exclus) |
| `controles/cloturer.py` | Le déroulé de bout en bout (étapes 0 à 6), avec la porte du GO humain |
| `controles/preflight.py` | Pré-vol d'ouverture : bilan des sources avant toute extraction |
| `controles/chargement.py` | Chargement des extraits dans `raw_*` (interface qui remplace les connecteurs) |
| `controles/controle_totaux_outil.py` | Contrôle bloquant du chargement et son registre d'exceptions |
| `controles/pipeline.py`, `controles/sql/*.sql` | Pipeline réduit, un fichier SQL par table produite, contrôles de module |
| `controles/crm.py` | Registre d'anomalies piloté par la donnée, prévisionnel au grain mois (fonction `forecast`, table `mart_forecast_mensuel`), deals disparus |
| `controles/mdm.py` | Garde des arbitrages, production sans groupe client |
| `controles/cadrage_ventes.py` | Rapprochement pièce à pièce, qualification OK / METHODE / INSTRUIRE, tableau de passage |
| `controles/cadrage_achats.py` | Appariement par niveaux de preuve décroissants, qualification des non-appariés, périmètre, passage |
| `controles/cadrage_paie.py` | Livre de paie contre journal de paie, « 0 écart non expliqué » |
| `controles/vraisemblance.py` | Production du mois contre la médiane des douze mois précédents |
| `controles/recette.py` | Qualification des écarts (arrondi, qualifié, non qualifié), oracle M-1, figement |
| `controles/increment.py` | Chargement delta à fenêtre glissante et son contrôle |
| `controles/fin_de_cloture.py`, `controles/recap.py` | Contrôles du mois, contrôle de fin de clôture, récapitulatif métier |
| `exemples/mois_conforme/` | Un mois fictif complet qui passe, avec des écarts expliqués par les registres |
| `exemples/mois_en_ecart/` | Variante qui n'embarque que les fichiers modifiés (`variante.json` liste les écarts volontaires) |
| `tests/` | 66 tests pytest : chaque contrôle passe sur le conforme et échoue là où on le casse |

## 6. Essayer

Depuis ce dossier, avec Python 3.11 ou plus récent (aucune dépendance hors bibliothèque standard ; pytest, déclaré dans le groupe `dev` que `uv` installe par défaut, pour les tests) :

```bash
uv run pytest -q
```

Résultat attendu : `66 passed`.

Le déroulé complet sur le mois conforme :

```bash
python -m controles.cloturer --exemple exemples/mois_conforme --periode 2026-03 --aujourdhui 2026-04-01 --go
```

Résultat attendu : `FIN DE CLÔTURE : CONFORME`, récapitulatif « DIFFUSABLE après GO humain », code retour 0. Au passage, trois écarts expliqués par les registres (revalorisation de change au chargement, mutuelle mal ventilée en paie, ajustement décidé sur le mois précédent), un écart de change classé en méthode, un prévisionnel décalé hors du mois clos et une correction CRM signalée périmée.

Le même déroulé sur la variante en écart :

```bash
python -m controles.cloturer --exemple exemples/mois_en_ecart --periode 2026-03 --aujourdhui 2026-04-01 --go
```

Résultat attendu : `FIN DE CLÔTURE : ÉCHEC (cadrage paie en valeur, production sans groupe client, contrôles du mois)`, récapitulatif « NON DIFFUSABLE », code retour 1. Les trois bloquants : un écart de charges sociales absent du registre, un nouveau projet client jamais rattaché au référentiel, et une production du mois hors bornes de vraisemblance alors que l'export et les totaux de l'outil étaient cohérents entre eux. Trois constats sont aussi présentés : une facture absente du journal des ventes, un achat payé mais jamais comptabilisé, un deal disparu du CRM.

Sans `--go`, le script s'arrête après le pré-vol d'ouverture (code retour 2) : le GO sur le mois est humain. `--detail` affiche les tableaux de passage et le détail de chaque contrôle ; `--base fichier.sqlite` conserve la base pour l'inspecter.

---
description: "Clôture mensuelle de l'entrepôt de données finance : pré-vol d'ouverture et GO humain, extractions, chargements, arbitrages, pipeline, contrôles, fin de clôture, récapitulatif, instantané"
allowed-tools: ["Read", "Write", "Edit", "Glob", "Grep", "Bash"]
---

# /cloture-mensuelle

Commande d'agent qui conduit la clôture mensuelle de l'entrepôt de données finance d'un client. Elle porte la **charge mentale** du process : ce qu'il faut vérifier, dans quel ordre, ce qui bloque et quoi faire quand ça bloque. Elle ne porte **aucune décision métier** : l'agent prépare, l'humain décide.

> Version publique et anonymisée d'une commande réelle. Les chemins, noms de base, d'outils et de personnes ont été retirés ; les commandes renvoient aux scripts de démonstration de ce dossier (`controles/`), qui jouent une version réduite du pipeline sur des données synthétiques.

`P` désigne le mois clôturé (`AAAA-MM`). La procédure est **autoportante** : un agent qui ne connaît rien du chantier doit pouvoir la dérouler avec ce seul document. Si une étape n'est pas exécutable telle qu'écrite, c'est ce document qui est faux : le dire dans le rapport, ne pas improviser.

## L'invariant : la clôture n'est jamais automatique

- L'humain **confirme le mois** à clôturer (étape 0), **prend toutes les décisions métier** (étape 4) et **franchit les jalons** (données publiables, mois soldé).
- Le référentiel analytique (rattachements clients, ajustements du cutoff (l'arrêté mensuel, projet par projet, du chiffre d'affaires et du coût produits), taxonomie P&L, rubriques de paie) n'est maintenu **que par cette routine**, et toujours sur décision humaine.
- Un agent qui rencontre une décision **s'arrête, liste ce qu'il a trouvé avec une proposition, et n'écrit rien** avant validation.

## 0. Prérequis, pré-vol d'ouverture et GO

1. Accès à l'entrepôt ouvert en lecture (rôle lecture seule pour tout ce qui n'écrit pas). Si l'accès ne s'ouvre pas : **s'arrêter et le signaler**, ne jamais contourner.
2. Dépôt propre et tests verts (`uv run pytest -q`).
3. **Pré-vol d'ouverture**, avant toute extraction (à ne pas confondre avec le contrôle de fin de clôture de l'étape 6, qui est le second et dernier pré-vol, avant diffusion) :

   ```bash
   python -m controles.cloturer --exemple <dossier> --periode P
   ```

   Rien n'est extrait ni chargé. Le pré-vol d'ouverture déduit le mois attendu de la date du jour (le mois précédent), le compare à `P`, vérifie le dépôt de paie, le dernier extrait de chaque source contre le dernier chargé, et imprime un bilan **manquants / incohérences / mode par source**.

   La session **présente ce bilan à l'humain et attend sa confirmation du mois**. La validation du cutoff du mois dans l'outil de gestion de projets ne se voit pas d'ici : c'est l'humain qui la confirme. **Sans GO, on ne va pas plus loin.** Un manquant : s'arrêter et le dire (cas courant : la paie pas encore déposée). Une incohérence (mois inattendu, extrait orphelin, mois déjà chargé) : la présenter, l'humain tranche.

   Le **mode de chaque source** vient du registre des chargements : absente du registre, extraction **complète** (premier passage) ; présente, extraction **delta** à fenêtre glissante M-2..M, chaînée au dernier extrait chargé. Le CRM et la paie sont toujours complets.
4. **Point de retour** : instantané de la base avant toute écriture. Si l'instantané échoue, **s'arrêter** : pas de clôture sans point de retour.
5. Vérifier que **l'instantané des marts de P-1** existe (il a été figé en fin de clôture précédente) : il sert d'oracle M-1 à l'étape 6 (la référence figée du mois précédent, contre laquelle on vérifie que les mois passés n'ont pas bougé). Absent : le dire avant de commencer, ne pas le recréer maintenant (les marts portent peut-être déjà autre chose que l'état de fin de P-1).

## 1. Source manuelle : la paie

Seule la paie reste déposée à la main. Le chargement de paie **remplace** les tables à partir de ce seul dépôt : le dépôt doit être un jeu **complet**, historique compris. Vérifier que chaque fichier **couvre P** ; un fichier manquant ou d'un autre mois : **s'arrêter et le signaler**.

## 2. Extractions (lecture seule, extraits figés)

Chaque source est lue par API **en lecture seule** (GET uniquement : les jetons ne permettent pas d'écrire) et écrite d'abord en **extrait figé** daté sur disque, puis chargée depuis cet extrait. Deux chargements du même extrait donnent la même base. Noter le nom exact de chaque extrait.

| Source | Contenu |
|---|---|
| Outil de gestion de projets | projets, avancement, cutoff par projet, temps et absences, factures et achats exportés |
| CRM | deals et organisations (toujours complet) |
| Logiciel comptable | grand livre des exercices ouverts |
| Paie | dépôt manuel de l'étape 1 |

Les extractions qui sollicitent une même API se lancent **l'une après l'autre**, jamais en parallèle. Un extrait interrompu, sans manifeste, est ignoré par le code.

## 3. Chargements en production

**Ordre impératif : le cutoff des projets EN PREMIER.** C'est le seul chargement qui porte un contrôle bloquant ; s'il bloque, **aucune autre source n'est chargée** et la clôture s'arrête là, pour que la production ne mélange jamais deux mois.

Blocages attendus, et quoi faire :

- **Contrôle `cutoff contre totaux de l'outil` en échec** : le total reconstitué d'une entité diffère du total de l'outil de plus de 1 EUR, après retrait des exceptions du registre. Sur un mois clos, **ne pas forcer**. Diagnostiquer en lecture seule depuis l'extrait figé (retirer les projets un à un jusqu'à trouver ceux qui portent l'écart), puis rapporter projet, montants et cause présumée : c'est une **décision de l'étape 4**. Un écart que l'outil ne compte pas reçoit, sur décision humaine, **deux lignes** : un ajustement du cutoff qui le neutralise et une exception motivée au registre. Le contrôle admet alors l'écart si le résiduel tient dans 1 EUR, et bloque sinon, y compris si l'outil se met à compter la ligne (l'exception est périmée et se retire). Après la décision, recharger le même extrait.
- **Parent de delta incorrect** : ne jamais forcer. Cas courant : un extrait delta extrait mais jamais chargé, que le delta suivant a pris pour parent. Deux sorties à présenter : charger d'abord l'orphelin s'il est bon, ou le supprimer et réextraire.
- **Versions de cutoff de P-1 et P-2 modifiées** dans l'outil depuis le chargement précédent : pas un blocage, mais une liste à présenter, l'humain décide d'un éventuel ajustement.
- **Registre d'anomalies du CRM** : le chargement applique les corrections `ouvert` dont la source n'a pas bougé et signale celles dont la source s'est corrigée (ligne à repasser `resolu`, geste humain).

## 4. Décisions métier : ne jamais trancher seul

| Décision | Où elle se voit | Ce qui est mis à jour, après validation |
|---|---|---|
| Ajustement du cutoff (annulation, décalage, ajout), écart au contrôle des totaux de l'outil | blocage du chargement ; liste des versions de cutoff modifiées | `regles/ajustements_cutoff.csv` et, pour un écart que l'outil ne compte pas, `regles/exceptions_totaux_outil.csv` |
| Rattachement d'un nouveau client, organisation, deal ou projet à un groupe (MDM : le référentiel des clients et de leurs rattachements) | suggestions du mois ; garde en tête du pipeline ; contrôle « production sans groupe » | référentiel `regles/groupes_clients.csv`, `regles/xref_client_groupe.csv`, **uniquement par le script d'application** |
| Compte du grand livre sans poste P&L | contrôle de module du pipeline | `regles/taxonomie_pnl.csv` |
| Rubrique de paie sans compte | contrôle de module du pipeline | `regles/passage_rubrique_compte.csv` |
| Écart de cadrage paie expliqué | fin de clôture | `regles/registre_exceptions_cadrage.csv` (motif, référence, statut) |
| Écart de l'oracle M-1 sur un mois passé | fin de clôture | `regles/ecarts_snap_qualifies.csv` (montant et cause obligatoires) |
| Correction d'une donnée CRM qui ne peut pas être faite à la source | blocage « dates inversées » | `regles/registre_anomalies_crm.csv` |

**Arbitrages MDM.** Après le chargement, générer les suggestions du mois, puis les présenter **par blocs** : les rattachements automatiques à valider en bloc, les **prioritaires** (projet avec production sur P, organisation qui porte un deal ouvert) à arbitrer un par un, le reste laissé vide. L'humain remplit la colonne `decision` ; le script d'application montre d'abord ce qu'il ferait (simulation, option `--dry-run`), puis applique et archive. **L'agent ne remplit jamais `decision` et n'écrit jamais dans le référentiel à la main.** Tant qu'un arbitrage prioritaire est en attente, le pipeline s'arrête à la garde : c'est voulu.

## 5. Pipeline

```bash
python -m controles.cloturer --exemple <dossier> --periode P --aujourdhui <date> --go
```

Reconstruit `stg`, `mart` et `ctrl` depuis `raw`, chaîne complète, jamais une étape isolée. Les référentiels versionnés sont relus à chaque passage : une décision écrite dans `regles/` s'applique au pipeline suivant. Une erreur de contrôle de module (compte orphelin, rubrique sans compte, dates inversées, grain rompu) est **bloquante** : la rapporter, ne pas contourner.

## 6. Contrôles et fin de clôture

1. **Contrôles du mois** : cadrage des ventes (factures de l'outil contre journal des ventes), cadrage des achats de sous-traitance (outil contre grand livre), cadrage en valeur de la paie (livre contre journal de paie), vraisemblance de la production contre les douze mois précédents, deals disparus du CRM. Les pièces à instruire sont des **constats** ; le résidu inexpliqué d'un tableau de passage, un écart de paie non expliqué et une production hors bornes sont **bloquants**.
2. **Contrôle de fin de clôture** (le pré-vol avant diffusion) : date de clôture du modèle égale au dernier jour de P, paie couverte, cadrage paie sans écart non expliqué, aucun projet avec production sans groupe client, aucun arbitrage MDM en attente, contrôles du mois calculés et sans bloquant en échec, **oracle M-1** conforme (les marts courants contre l'instantané de P-1, sur tous les mois antérieurs à P : un mois passé qui bouge est soit une décision qualifiée au registre, soit une régression à rapporter).

Un échec se rapporte et se présente à l'humain ; **il ne se contourne pas**. Un mois réellement exceptionnel (hors bornes de vraisemblance) se confirme par l'humain et s'écrit dans le rapport.

## 7. Récapitulatif et rapport

Le récapitulatif métier (CA, marge, taux de marge, top groupes, nouveaux groupes, P&L comptable, coût de paie, prévisionnel CRM) s'imprime toujours, **avec le mois à côté de l'historique**, et porte en tête son statut : NON DIFFUSABLE tant que la fin de clôture n'est pas conforme.

Écrire le rapport de clôture (hors dépôt, il contient des données client) : bilan du pré-vol d'ouverture et GO, extraits et modes, blocages et ce qui a été fait, décisions prises et décisions en attente, résultat de chaque contrôle.

## 8. Clôture de la clôture

Seulement quand la fin de clôture est conforme, ou que l'humain a accepté en connaissance de cause ce qui reste en échec :

1. **Figer l'instantané des marts de P** (`--figer`) : c'est l'oracle M-1 de la clôture suivante. Refusé si la date de clôture n'est pas la fin de P ou si l'instantané existe déjà.
2. **Commit par chemins explicites** des seuls référentiels et registres modifiés, message qui dit les décisions humaines. Jamais d'ajout global ; aucune donnée client.
3. **Journal du hub récurrent** : une ligne datée (mois, modes, blocages, décisions, résultat de la fin de clôture). Cf. `hub-recurrent-et-iteration.md`.
4. **Export client** depuis les marts, puis sauvegarde des extraits figés (sans eux, la chaîne de delta est perdue).

## Ce que tu ne fais jamais

- Inventer un mois si l'humain ne répond pas clairement.
- Trancher une décision métier, remplir une colonne `decision`, écrire dans le référentiel à la main.
- Forcer un contrôle, qualifier un écart sans en avoir trouvé la cause, ajouter une ligne de registre sans montant.
- Corriger une donnée directement en base : elle serait effacée au rechargement suivant. Elle va au registre, ou à la source.
- Appeler une API en écriture.
- Sauter une étape « parce que ça a marché la dernière fois ».
- Commiter une donnée client, un mot de passe ou un jeton.

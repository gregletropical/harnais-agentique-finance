---
type: process
summary: "Chaîne canonique de la clôture mensuelle en quatre phases : fiabilisation des entrants comptables, reconstruction de l'entrepôt, contrôles et écarts en tolérance zéro, restitution. Instanciée chaque mois en une note d'itération."
---

# Process — Clôture mensuelle de l'entrepôt de données finance

> Chaîne canonique, version anonymisée. Elle s'instancie chaque mois dans une note d'itération (cf. `hub-recurrent-et-iteration.md`). **Elle ne se modifie qu'après une itération**, à la lumière de ce qu'elle a appris, jamais en cours de mois.

## Jour de référence

**`J` = 1er jour ouvré du mois suivant**, sous une condition qui prime sur le calendrier : **le cutoff mensuel de l'outil de gestion de projets (l'arrêté, projet par projet, du chiffre d'affaires et du coût produits sur le mois) doit être validé.** Avant, l'information métier est fausse par construction et rien ne sert de lancer quoi que ce soit.

**Échéance dure : la synthèse est présentée au client au plus tard à `J+5` jours ouvrés.** C'est la seule date que le client voit, et elle ne bouge pas.

**Gel des entrants comptables à `J+3`.** La boucle avec la production comptable court de `J-3` à `J+3` ; passé ce point, le grand livre est extrait et ne bouge plus. Si `J+3` est trop court, c'est la **synthèse** qui glisse, jamais le gel qui saute : une synthèse construite sur des entrants mouvants n'est pas une synthèse en retard, c'est une synthèse fausse.

## Les quatre phases

```
Phase A — Entrants comptables    J-3 → J+3   ─┐
                                              ├─► Phase C ─► jalon ─► Phase D
Phase B — Entrepôt               J   → J+3   ─┘   contrôles           restitution
```

**A et B sont largement parallèles** : A dépend du logiciel comptable, B de l'outil de gestion de projets, du CRM et de la paie. Elles ne se rejoignent qu'en deux points, le gel du grand livre (A5 alimente B3) et les contrôles croisés de la phase C. C'est cette structure qui rend le process **connectable** : une nouvelle famille de contrôles, une connectique API ou le volet budgétaire se greffent **dans une phase** sans toucher aux autres.

## Chaîne canonique

Colonnes : **Qui** (agent ou humain), **Énergie** (admin : exécution simple ; deep : concentration ; créatif : restitution), **Durée** (mesurée sur exécution réelle, pas estimée), **Dépend de** (fin → début), **Jour cible** (décalage relatif à `J`).

### Phase A — Fiabilisation des entrants comptables

| # | Étape | Qui | Énergie | Durée | Dépend de | Jour cible |
|---|---|---|---|---|---|---|
| A1 | Boucle avec la production comptable : pièces manquantes, imputations à corriger | humain | admin | 1h | — | `J-3` |
| A2 | Détection par API : soldes anormaux, comptes d'attente, doublons d'auxiliaires, flux muet | agent | admin | 15m | — | `J+1` |
| A3 | Diff contre le mois précédent : ne garder que ce qui est nouveau | agent | admin | 10m | A2 | `J+2` |
| A4 | Arbitrage des anomalies nouvelles, **une exception enregistrée par anomalie** | humain | deep | 1h30m | A3 | `J+2` |
| A5 | **Gel** : extraction du grand livre | humain | admin | 15m | A1, A4 | `J+3` |
| A6 | **JALON — Entrants comptables gelés** | humain | — | — | A5 | `J+3` |

### Phase B — Reconstruction de l'entrepôt

| # | Étape | Qui | Énergie | Durée | Dépend de | Jour cible |
|---|---|---|---|---|---|---|
| B1 | Dépôt de la paie du mois (seule source encore manuelle) | humain | admin | 20m | — | `J` |
| B2 | Pré-vol d'ouverture (bilan des sources), GO sur le mois | agent puis humain | admin | 15m | B1 | `J` |
| B3 | Extractions API (projets, temps, CRM, grand livre gelé) | agent | admin | 20m | A6, B2 | `J+3` |
| B4 | Chargement du cutoff d'abord, avec son contrôle bloquant | agent | admin | 10m | B3 | `J+3` |
| B5 | Arbitrage des ajustements de cutoff (annulation, décalage, ajout) | humain | deep | 30m | B4 | `J+3` |
| B6 | Chargement des autres sources | agent | admin | 10m | B5 | `J+3` |
| B7 | MDM (référentiel des clients et de leurs rattachements) : suggestions, arbitrage des **prioritaires uniquement**, application | agent + humain | admin | 20m | B6 | `J+3` |
| B8 | Pipeline complet (jamais une étape isolée) | agent | deep | 30m | B7 | `J+3` |
| B9 | Boucle des comptes orphelins de la taxonomie P&L | agent + humain | deep | 20m | B8 | `J+3` |
| B10 | **JALON — Entrepôt reconstruit, tous tests verts** | — | — | — | B9 | `J+3` |

### Phase C — Contrôles et écarts

| # | Étape | Qui | Énergie | Durée | Dépend de | Jour cible |
|---|---|---|---|---|---|---|
| C1 | Contrôles de qualité de l'entrepôt (date de clôture, couverture paie, vraisemblance) | agent | admin | 15m | B10 | `J+3` |
| C2 | Contrôles croisés entrepôt x comptabilité (ventes, achats, paie) | agent | deep | 30m | A6, B10 | `J+4` |
| C3 | Relevé des registres : **tout écart est expliqué ou enregistré comme exception** | agent | admin | 15m | C1, C2 | `J+4` |
| C4 | Arbitrage des écarts non expliqués | humain | deep | 45m | C3 | `J+4` |
| C5 | **JALON — Données publiables** (revue argumentée) | humain | — | 30m | C4 | `J+4` |

### Phase D — Restitution

| # | Étape | Qui | Énergie | Durée | Dépend de | Jour cible |
|---|---|---|---|---|---|---|
| D1 | Récapitulatif métier : CA, marge, taux, top clients, nouveaux groupes | agent | admin | 10m | C5 | `J+4` |
| D2 | Montage et présentation de la synthèse au client | humain | créatif | 1h30m | D1 | `J+5` |
| D3 | Instantané des marts, commit par chemins explicites | agent | admin | 15m | C5 | `J+4` |
| D4 | **JALON — Clôture du mois soldée** | — | — | — | D2, D3 | `J+5` |

## Qui fait quoi : la règle, pas le cas par cas

**L'agent prépare, l'humain décide.** C'est la séparation préparateur / réviseur du contrôle interne, transposée : celui qui produit ne se contrôle pas lui-même.

| Revient à l'agent | Revient à l'humain |
|---|---|
| Tout ce qui est déterministe : pré-vol d'ouverture, chargements, pipeline, contrôles, récapitulatif | Tout ce qui est un **jugement métier** : ajustements, imputations, arbitrage des écarts |
| Détecter, mesurer, présenter l'écart avec son état « avant » | **Trancher** l'écart et en porter la responsabilité |
| Proposer un rattachement avec ses voisins et un candidat | **Valider** le rattachement |
| Le commit et la trace | **Franchir les jalons** |

**Les trois jalons de validation ne se délèguent jamais** : A6 (entrants gelés), C5 (données publiables), D4 (mois soldé). Un jalon franchi est un engagement daté.

## Règles dures

### Tolérance zéro sur les écarts

**Il n'y a pas de seuil de matérialité sur un écart de réconciliation.** Un écart, même au centime, signale une anomalie du pipeline, et un écart d'un centime toléré aujourd'hui devient un écart important dont plus personne ne connaît l'origine. Le contrôle ne rapporte pas « 0 écart au-dessus du seuil » mais **« 0 écart non expliqué »**. Chaque écart connu porte sa cause, sa référence et sa résolution attendue dans un registre versionné. Un écart d'arrondi **reste un écart** : il s'explique une fois, et on n'y revient plus. Ce qui est interdit, c'est qu'il soit tu.

**La métrique à surveiller est le nombre d'exceptions ouvertes, pas leur montant.** Si la liste enfle, le pipeline a un problème systémique et c'est le moment de corriger le traitement de masse plutôt que d'instruire les cas un par un.

### Le registre d'anomalies

Toute correction qui ne peut pas être faite à la source vit dans un registre versionné, **jamais dans la base**. Le chargement n'applique que les lignes `ouvert`, et signale de lui-même celles dont la source s'est corrigée entre-temps : l'obsolescence est pilotée par la donnée, pas par une date de péremption. Origine de la règle : des corrections faites directement dans une table brute ont été effacées au rechargement suivant, sans que personne s'en aperçoive.

### La porte de publication

C5 se franchit en **revue argumentée** : l'humain instruit chaque écart non expliqué avant de signer. L'allègement vers un simple contrôle de vraisemblance ne se décide pas au feeling : il se déclenche après **trois clôtures consécutives sans écart non expliqué**, critère que l'itération suivante vérifie seule dans les précédentes.

## Reprise hors cycle

La chaîne décrit un cycle complet. Elle ne couvre pas le cas où l'on revient sur une clôture déjà soldée (un ajustement retiré parce que les opérationnels sont revenus sur leur demande). **On ne relance jamais tous les chargements pour une reprise hors cycle** : on recharge la seule source touchée, puis le pipeline complet.

| # | Étape | Détail |
|---|---|---|
| R1 | Sauvegarde datée du référentiel touché | le filet local |
| R2 | Modifier le référentiel | et **contrôler le diff** : il doit porter la seule ligne visée, sans reformatage des autres |
| R3 | Recharger la seule source touchée | les chargements sont isolables |
| R4 | Pipeline complet | jamais une étape isolée |
| R5 | Contrôles de qualité et vérification ciblée | la ligne visée, et les autres périodes retrouvées à l'identique (non-régression) |

L'itération de la période concernée est un **enregistrement** : ses chiffres ne se réécrivent pas. La reprise s'y consigne en **addendum daté**.

## Pièges connus

- **Le cutoff doit être validé avant `J`.** Sinon toute la chaîne travaille sur des chiffres faux, et rien dans le pipeline ne le signalera, sauf le contrôle de vraisemblance.
- **Le remplacement des sources de paie, pas leur empilement** : un dépôt partiel efface l'historique, un dépôt doublé compte deux fois les mêmes mois.
- **Ne jamais rejouer une étape isolée du pipeline** : les rattachements au référentiel décrochent en silence.
- **Une correction faite à la main en base ne survit pas à son chargement.** D'où le registre d'anomalies, et la règle de reprise hors cycle.
- **Un contrôle qui ne s'est jamais exécuté n'est pas un contrôle testé.** Un contrôle dormant peut mentir longtemps : tant que son chemin de code n'a jamais tourné, rien ne dit qu'il sait échouer. D'où un test par contrôle, qui le fait échouer volontairement.
- **Valider la forme n'est pas valider la vraisemblance.** Un export amputé de l'essentiel du chiffre d'affaires a traversé tous les contrôles de structure ; seul un humain comparant le total à l'historique l'a arrêté.
- **Une valeur reconstituée doit se distinguer d'une valeur saisie.** Une marge estimée pour débloquer le pipeline entre sinon dans le prévisionnel client sans marqueur.

## Journal du process

- **Création** — depuis le cadrage du hub récurrent et le run réel de la première clôture outillée. La chaîne des phases B, C et D est mesurée sur l'exécution.
- **Itération suivante** — ajout de la section Reprise hors cycle, révélée par un ajustement annulé après une clôture soldée.
- **Itération suivante** — ajout du contrôle de vraisemblance de la production contre les douze mois précédents, après l'export amputé.
- **Bascule** — l'entrepôt passe des exports manuels aux extraits API figés avec mode delta ; le pré-vol d'ouverture et le contrôle de fin de clôture deviennent des scripts, plus des listes à cocher.

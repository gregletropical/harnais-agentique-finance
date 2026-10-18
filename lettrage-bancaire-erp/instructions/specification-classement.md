# Spécification du classement — le lint de comptabilisation

*Note de méthode adaptée et anonymisée. Elle est écrite pour qu'une session vierge puisse faire évoluer le script sans relire l'historique. Elle existe parce que le geste a d'abord été fait plusieurs fois à la main avec des requêtes réécrites à chaque passage : c'est exactement là que la variance s'installe.*

## 1. Ce qu'on veut

Un script qui rejoue la routine de lettrage bancaire **à l'identique, tous les matins**, produit un rapport lisible, puis exécute les cas non ambigus après GO. Objectif final : **délégable au comptable du client**. Les règles doivent donc être **dans le code**, pas dans la consigne. Critère de conception : toute règle est binaire, requêtable et testable par un agent sans jugement.

## 2. Les classes

| Classe | Famille | Définition | Traitement |
|---|---|---|---|
| **A** | exécutable | Le libellé cite une référence de pièce **et** le montant correspond au reste dû (pièce entière, sous-ensemble unique des pièces citées, ou échéances ouvertes les plus anciennes dans l'ordre, sans saut) | Lettrage |
| **A′₁** | exécutable | Pas de référence, mais tiers identifié et correspondance **triviale** : combinaison exacte unique de **3 pièces au plus**, le tiers n'ayant **pas plus de 8 pièces ouvertes** | Lettrage, **avec activité de validation au comptable** |
| **B** | exécutable | Le montant correspond à **un seul** paiement par lot envoyé | Rapprochement du lot |
| **N** | exécutable | Virement groupé (`/NBT n`) = **n** paiements en cours du même journal, datés au plus 5 jours avant, combinaison exacte **unique** de taille n | Lettrage avec ces n paiements |
| **R** | exécutable | Remboursement d'un trop-perçu client face à **une seule** ligne client créditrice ouverte au montant exact | Lettrage ; plus d'une candidate → D |
| **I** | exécutable | Imputation sans facture d'une catégorie **actée** (`regles/categories.py`) | Imputation de la contrepartie d'attente |
| **A′₂** | à arbitrer | Combinaison exacte unique, mais **au-delà** des seuils | Proposée avec le détail, exécutée seulement sur validation |
| **C** | à arbitrer | Règlement **partiel** d'une pièce citée | Proposé |
| **E** | à arbitrer | Échéancier négocié (`ECHEANCIER n/m`) : périmètre = factures du tiers aux dates citées, lignes dans l'ordre, dernière partielle ; versement final qui ne couvre pas le périmètre → « écart de solde d'échéancier » ; sans date citée → D | Proposition détaillée, jamais exécutée par le script |
| **P** | exception | Ligne **partiellement traitée** par le robot ou un humain : une partie des contreparties est posée, le reste dort en attente | Signalée, jamais complétée : le solde en suspens ne correspond pas forcément au reste dû |
| **D** | exception | Plusieurs combinaisons, aucune, tiers inconnu, incertain ou ambigu, montant ≠ reste dû, double paiement probable, doublon par réimport, exercice clos, catégorie hors plafond ou hors périmètre | Signalée, jamais exécutée |

**L'ordre des étapes de `classer()` est lui-même une règle** : exercice clos, puis ligne partielle, puis catégorie actée, puis lot, puis virement groupé, puis pièces citées, puis échéancier, puis remboursement, puis combinaison chez le tiers, puis catégorie « à défaut de facture ».

## 3. Pourquoi A′ est en deux crans

Une combinaison exacte **n'est pas une preuve de paiement**, c'est une coïncidence arithmétique dont la probabilité croît violemment avec le nombre de pièces ouvertes. Des cas réels ont fixé les seuils :

- Un virement important face à **plusieurs dizaines de pièces ouvertes** : des milliers de combinaisons exactes possibles. En retenir une aurait pu fabriquer de faux impayés et solder à tort d'autres factures.
- Un virement face à une poignée de pièces ouvertes et une seule combinaison exacte : exécutable, sous réserve d'une validation a posteriori par le comptable.

Le discriminant n'est donc pas « la combinaison est-elle unique » mais **« combien de combinaisons le tiers rendait-il possibles »**. Les seuils sont un compromis à recalibrer avec les données : le script journalise, pour chaque ligne A′, le nombre de pièces ouvertes et le nombre de combinaisons exactes.

Toute ligne exécutée en A′₁ — lettrée par déduction, sans référence citée par le client — reçoit une **activité « À faire » au comptable** sur la pièce de banque. Le texte dit trois choses et rien de plus : la composition retenue, le fait que c'est la seule combinaison exacte, et que le lettrage est fait sans confirmation du client ; puis il demande de marquer l'activité « Terminée » si elle est validée, ou de signaler s'il faut annuler. C'est ce qui rend l'automatisme acceptable : il agit, mais il le dit.

## 4. Identification du tiers : jamais de devinette

- Les **deux premiers mots significatifs** du libellé doivent figurer dans le nom du tiers (un mot seul suffit s'il est le nom exact, ou s'il fait au moins 4 caractères) : un particulier « M JEAN DUPONT » ne se rattache pas à une adresse « rue Jean Jaurès ».
- Sigles à points compactés (« S.T.X. » = « STX »), formes juridiques ignorées (« SAS ALPHA » = « ALPHA »).
- Plusieurs tiers plausibles : les fiches archivées **sans aucune pièce** (doublons d'import) sont écartées ; ensuite, seul le nom exact départage ; sinon, D.
- À défaut de tiers par le nom : **précédent bancaire unanime** — au moins deux lignes déjà rapprochées du même émetteur (`/FRM`), à défaut du même créancier SEPA, à défaut du même libellé, toutes sur le même tiers. Un seul discordant bloque la règle.
- Homonyme sans pièce : si la fiche trouvée par le nom n'a aucune pièce ouverte et que les précédents désignent unanimement une autre fiche qui en a, le précédent l'emporte.
- Recherche **par montant** en dernier recours : une pièce au montant exact chez un tiers dont le nom ne correspond pas → D « tiers incertain », jamais un lettrage.
- Garde-fou : si le libellé cite un numéro de facture qu'aucune pièce de la combinaison ne porte, l'appariement est refusé, même au montant exact.

## 5. Catégories d'imputation (classe I)

Une catégorie n'entre dans `regles/categories.py` qu'**après arbitrage** de l'utilisateur, avec ses précédents relevés au grand livre et la décision qui l'a actée. Chaque catégorie peut porter : une restriction de société, un compte propre à une société, un tiers à poser, un plafond, l'exclusion si un tiers est déjà posé, un lettrage obligatoire avec une OD (paiement de TVA : contrôle d'unicité bloquant), un lettrage à faire ensuite (paie), ou la mention « à arbitrer » (reconnue, compte non tranché : signalée, jamais exécutée). Une catégorie reconnue sur une société où elle n'est pas actée est signalée comme « extension à arbitrer ».

## 6. Garde-fous non négociables

1. **Tolérance nulle** : la somme des restes dus doit égaler le montant de la ligne **au centime**. Un écart se passe par une écriture explicite après arbitrage, jamais par une tolérance.
2. **Somme recalculée juste avant l'appel**, contre l'ERP relu à cet instant. Sinon, arrêt.
3. **Arrêt sur ambiguïté** : plus d'une combinaison exacte, ou tiers non certain → D, aucune écriture.
4. **Aucune relance automatique** d'un appel en échec.
5. **Jamais d'écriture sur un exercice clos** : le verrou de la société est contrôlé avant tout appel. Même un lettrage qui ne crée aucune écriture modifierait un compte de tiers audité.
6. **Relecture systématique après écriture** : état de la ligne bancaire, statut de paiement des pièces, numéro de lettrage, pièce de TVA sur encaissements générée le cas échéant.
7. **Continuité des soldes** : une ligne qui compense exactement un écart apparu entre solde banque et solde ERP est sortie des exécutables avant classement. Cas fondateur : la reconnexion d'une banque a réimporté une ligne déjà supprimée, et une catégorie actée l'aurait imputée sans rien signaler.
8. **Pré-vol** : toute catégorie d'écriture nouvelle passe par le protocole, avec un pré-rapport horodaté.
9. **Méthode, jamais écriture directe d'un champ** : poser un tiers sur une ligne bancaire par la méthode de l'écran de rapprochement ; écrire le champ directement relance une resynchronisation qui supprime les contreparties déjà posées.

## 7. Ce que le script ne fait pas

- Il ne **crée** ni facture ni avoir : il apparie et impute.
- Il ne touche pas aux imputations hors catégories actées : il les liste.
- Il ne **corrige jamais** un lettrage du robot ou d'un humain : il signale.
- Il ne décide pas à la place de l'exécutant sur les exceptions.

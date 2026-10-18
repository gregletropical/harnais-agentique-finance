# Routine comptable du matin — procédure autoportante

*Lancée chaque matin ouvré par la commande `/routine-matin`, après le passage du robot de rapprochement de l'ERP et la synchronisation bancaire du matin. Cette procédure se suffit : un agent qui ne connaît rien du client doit pouvoir la dérouler en entier.*

*Version publiée : adaptée et anonymisée. Les commandes `etat.py` et `plan_ecriture.py` tournent ici sur des exemples synthétiques ; en production, elles lisent l'ERP en lecture seule et l'écriture passe par un adaptateur non publié.*

## 0. Principes non négociables

1. **Lecture libre, écriture sur GO.** Toute écriture dans l'ERP (lettrage, imputation, OD, activité, note, suppression) suit un GO de l'utilisateur donné **en conversation** ; l'agent le recopie mot pour mot dans le compte rendu (`--go "<citation>"`). Pas de GO, pas d'écriture.
2. **Simulation d'abord.** Tout script d'écriture tourne d'abord sans `--executer`. On n'exécute que ce que la simulation a validé, et on **relit** l'ERP après chaque geste.
3. **Arrêt à la première anomalie, jamais de relance.** Un appel en échec ne se rejoue pas : on rend la main à l'utilisateur avec l'état exact.
4. **On ne sollicite personne tant qu'on n'est pas bloqué par un élément extérieur** (cf. `regles-de-conduite-erp.md`).
5. **Traçabilité dans l'ERP.** Toute pièce traitée après un **arbitrage** reçoit une note interne sans mention, préfixée `[Lettrage AAAA-MM-JJ]`, suivie d'une phrase à la première personne de l'utilisateur. Les cas évidents n'ont que le compte rendu.
6. **Jamais d'écriture sur un exercice clos** ; une période de TVA déclarée se corrige sur la déclaration du mois en cours.
7. **Les données client ne se commitent jamais** : tout ce qui sort dans le dossier des livrables reste local.
8. **Dans l'ERP, on s'exprime toujours comme l'utilisateur** : la clé API écrit sous son nom (cf. `regles-de-conduite-erp.md`).
9. **Une note se relit dans l'interface.** Si l'API échappe le HTML d'une note, les balises s'affichent en texte : le client ERP corrige le corps, le relit, et lève une erreur s'il reste échappé. On ne contourne jamais ce client.

## 1. État des lieux et premier passage

```bash
python controles/etat.py --sortie sortie/              # lecture seule → AAAA-MM-JJ_HHMM_etat.{md,json}
python controles/plan_ecriture.py --etat sortie/…_etat.json   # simulation sur cet état
```

Lire le rapport :

- **Synchronisation bancaire** : heure du dernier passage de chaque banque ; une banque figée depuis plus de 24 heures se signale.
- **Continuité des soldes** : une alerte signifie que le solde ERP d'un journal s'écarte du solde transmis par la banque (ligne supprimée puis réimportée, ou ligne manquante). La ligne qui compense exactement l'écart est sortie des exécutables en exception « doublon probable », **avant** tout classement. Un journal dont la banque transmet un solde non arrêté est déclaré « non contrôlable », jamais en alerte.
- **Section 1, exécutable** (classes A, A′₁, B, N, R, I), **section 2, à arbitrer** (A′₂, C, E), **section 3, exceptions** (P, D) — nouvelles d'abord, stock déjà signalé ensuite.
- **Rapprochements automatiques de la nuit** : ceux du robot de l'ERP qui ne sont ni sur 411/401 ni complets.
- **Dérive** : les compteurs qui ont bougé depuis la veille.

Les classes et catégories sont définies dans `specification-classement.md` ; le code de référence est `regles/classement.py` et `regles/categories.py`.

## 2. Suivi des activités et des mentions

Script de suivi (lecture seule, non publié : il lit les activités et le fil de discussion des pièces dans l'ERP). Pour l'utilisateur, traiter chaque section du rapport de suivi comme si c'était sa demande :

- **Activités émises terminées** depuis le dernier contrôle : vérifier dans l'ERP que l'action est réellement faite (facture saisie, pièce jointe présente, pièce lettrée, statut de paiement). Lire le retour **et les commentaires** postés sur la pièce. Alerte si « terminé » mais non fait ou mal fait, ou si un commentaire appelle une action de l'utilisateur.
- **Activités annulées** : vérifier que la situation finale est propre ; sinon, proposer la remise au propre.
- **Activités assignées à l'utilisateur** et mentions reçues sans réponse : si tous les éléments sont dans l'ERP, **préparer l'action** et la soumettre à l'arbitrage dans le rapport final ; s'il manque un élément de l'utilisateur, le demander ; s'il manque un élément d'un tiers, **demander à l'utilisateur avant** de créer l'activité qui le sollicite.

## 3. Analyse des cas nouveaux

Pour chaque ligne **nouvelle** des sections 2 et 3 (le stock déjà formalisé ne se ré-analyse pas), dérouler cette checklist fermée, en lecture seule, et noter ce qu'elle établit :

1. **Libellé complet** et détail de la transaction ; société, journal.
2. **Tiers** : nom du libellé (sigles à points compactés), fiches homonymes ou fiches archivées sans pièce, **précédents bancaires** du même émetteur (libellé identique à défaut), même journal, au moins deux, tous sur le même tiers.
3. **Pièces ouvertes du tiers** : montant exact, combinaisons exactes (combien ? au-delà de 3 pièces appariées ou de 8 pièces ouvertes, c'est une coïncidence possible), **échéances** d'une facture à plusieurs lignes, **échéancier négocié** (libellé `ECHEANCIER n/m`, dates de factures citées).
4. **Double paiement** : facture du même montant déjà payée récemment.
5. **Catégorie d'imputation** possible (prélèvement récurrent sans facture : frais bancaires, organismes sociaux, impôts…) : précédents et compte. Une catégorie nouvelle se **propose**, elle ne s'ajoute pas.
6. **Pièce dans l'ERP** : pièce jointe sur la pièce de banque, le bon de commande ou le tiers ; fil de discussion.
7. **Conclusion** : écriture proposée (geste, comptes, montants), niveau de certitude, et — seulement si bloqué par un élément extérieur — la personne et l'élément à demander.

Pour plusieurs cas indépendants, lancer les analyses **en parallèle** (un sous-agent par cas).

## 4. Rapport final pour le GO

Un seul message, structuré :

1. **Évident** — ce qui s'exécute sur simple GO : section 1 du rapport + cas nouveaux établis avec certitude + actions de suivi finalisables. Tableau : ligne, montant, tiers, écriture, activité ou note prévue.
2. **Arbitrages** — un point par cas, avec faits, options, recommandation.
3. **Sollicitations proposées** — uniquement les blocages extérieurs : qui, quoi, pourquoi on ne peut pas avancer seuls.
4. **Suivi** — alertes sur les activités et mentions.
5. **Dérive** — les compteurs qui ont bougé, une ligne chacun.

S'il y a plus de cinq arbitrages, proposer de les porter dans une note de travail à encarts question / réponse.

## 5. Exécution après GO

```bash
python controles/plan_ecriture.py --etat sortie/…_etat.json --go "<citation exacte du GO>"
```

En production, la même commande avec `--executer` exécute les lignes exécutables, dans l'ordre A, A′₁, B, N, R, I, en recalculant chaque garde-fou juste avant chaque appel. Elle refuse un état de plus de deux heures.

Les arbitrages hors script s'exécutent par un **script dédié** (simulation par défaut, `--executer`, garde-fous recalculés avant chaque appel, arrêt à la première anomalie, relecture), conservé ensuite dans les livrables, et passent par le **pré-vol** (`protocole-prevol.md`) dès qu'il s'agit d'une catégorie d'écriture nouvelle.

Puis :

- **Activités** (blocage extérieur uniquement) : type « À faire », échéance à J+5, texte court à la première personne : ce qu'on sait, la question précise, « marque l'activité Terminée une fois fait ». Une activité par groupe de lignes de même nature.
- **Lignes A′₁** : une activité au comptable sur la pièce de banque, pour valider a posteriori un lettrage fait par déduction (cf. `specification-classement.md`).
- **Notes d'arbitrage** sans mention sur chaque pièce arbitrée, préfixe `[Lettrage AAAA-MM-JJ]`.
- Une activité envoyée à tort se **termine avec un mot d'excuse** et l'action est faite par nous.

## 6. Formalisation

- **Compte rendu** dans les livrables (produit par le plan d'écriture et les scripts dédiés) : il fait foi en cas de question des mois plus tard.
- **Base de connaissance** : une ligne datée dans le journal de la note de méthode **seulement** si la procédure a évolué ou si un fait marquant s'est produit (nouvelle catégorie, nouveau geste, anomalie).
- **Évolution du script** : toute nouvelle catégorie ou règle se code dans `regles/` avec ses tests (`pytest`), puis se commite par chemins explicites.

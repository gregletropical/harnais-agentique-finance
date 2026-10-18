# Catalogue des règles du lint

61 règles : 26 ERROR, 27 WARN, 8 INFO. Elles reprennent les 60 règles du lint en service sur le référentiel d'origine ; trois règles propres à un client (rattachement d'un hub à un projet dans son outil de suivi) ont été généralisées en `ref-externe-*`, et une règle a été ajoutée : `summary-trop-long`, qui n'existait qu'en consigne (« 50 mots maximum »).

**Lecture des sévérités** : ERROR = la note **ment** · WARN = la note est **incomplète** · INFO = **signal**, pas dette. Les constats d'une note endormie (`standby`, `avorte`, `archive`) passent en dette froide, visible avec `--froid`.

## Structure de la note

| Règle | Sév. | Ce qu'elle attrape |
|---|---|---|
| `illisible` | ERROR | fichier impossible à lire |
| `frontmatter-absent` | ERROR | aucun bloc `---` en tête |
| `frontmatter-illisible` | ERROR | YAML invalide ou délimiteur de fin absent |
| `note-orpheline` | WARN | aucun wikilink sortant dans le périmètre soumis |
| `cle-obsolete` | WARN | clef d'avant la refonte (`statut`, `lie`…) avec sa remplaçante |
| `cle-en-attente-arbitrage` | INFO | clef dont le sort n'est pas tranché |
| `template-sans-frontmatter` | WARN | template sans schéma |
| `template-clef-manquante` | WARN | template sans `type`, `summary` ou `created` |

## Vocabulaires fermés

| Règle | Sév. | Ce qu'elle attrape |
|---|---|---|
| `type-absent` | WARN | pas de `type:` |
| `type-invalide` | ERROR | `type:` hors des 17 valeurs |
| `type-supprime` | ERROR | ancien type supprimé, avec la cible de migration |
| `type-a-remapper` | WARN | type isolé à remapper (dette planifiée) |
| `status-invalide` | ERROR | `status:` hors cycle de vie |
| `source-absent` | WARN | provenance non qualifiée (la règle « human = immuable » ne protège que ce qui est qualifié) |
| `source-invalide` | ERROR | `source:` hors `human / ai / mixte` |
| `sujet-absent` | WARN | pas de `sujet:` (hors journaux et fiches personnes) |
| `sujet-trop-nombreux` | WARN | plus de 3 sujets |
| `sujet-pas-un-wikilink` | ERROR | valeur texte au lieu de `"[[sujet]]"` |
| `sujet-yaml-imbrique` | ERROR | `- [[x]]` non quoté, parsé en liste imbriquée |
| `sujet-hors-vocabulaire` | ERROR | cible hors du dossier des sujets (même si la note existe ailleurs) |
| `sujet-sur-note-sujet` | ERROR | une note de sujet porte elle-même `sujet:` |
| `recurrence-invalide` | ERROR | `recurrence:` hors vocabulaire |

## Properties contrôlées

| Règle | Sév. | Ce qu'elle attrape |
|---|---|---|
| `summary-absent` | WARN | pas de `summary` |
| `summary-trop-court` | INFO | moins de 20 caractères |
| `summary-trop-long` | WARN | plus de 50 mots |
| `created-absent` | WARN | pas de date de création |
| `created-format` | WARN | date hors `AAAA-MM-JJ` |
| `peremption-format` | WARN | hors `AAAA / AAAA-MM / permanent` |
| `perime-non-archive` | INFO | date de péremption dépassée, note non archivée |
| `importance-hors-bornes` | WARN | hors 1-5 |
| `importance-non-numerique` | WARN | valeur non numérique |
| `diese-dans-frontmatter` | ERROR | `#` dans un tag de frontmatter (crée un tag en double) |
| `tags-en-frontmatter` | WARN | taxonomie thématique en tags au lieu de `sujet:` |

## Axe projet et focus

| Règle | Sév. | Ce qu'elle attrape |
|---|---|---|
| `projet-pas-un-wikilink` | ERROR | `projet:` en texte libre |
| `projet-cible-introuvable` | ERROR | `projet:` vers une note inexistante |
| `projet-cible-non-projet` | ERROR | `projet:` vers autre chose qu'un hub `projet-chantier` |
| `recurrence-hors-hub` | ERROR | `recurrence:` sur une note qui n'est pas un hub |
| `focus-hors-hub` | ERROR | `focus:` sur une note qui n'est pas un hub |
| `focus-invalide` | ERROR | `focus:` non booléen (une chaîne ne serait comptée nulle part) |
| `focus-hors-plafond` | ERROR | plus de 3 hubs en focus dans le vault, posé sur chacun |
| `ref-externe-hors-hub` | ERROR | `ref_externe:` hors hub |
| `ref-externe-invalide` | ERROR | `ref_externe:` qui n'est pas un entier positif |
| `ref-externe-hors-perimetre` | ERROR | `ref_externe:` hors des dossiers clients déclarés |
| `actif-dormant` | INFO | hub `active` sans commit depuis 30 jours (bascule jamais automatique) |

## Tâches et dépendances

| Règle | Sév. | Ce qu'elle attrape |
|---|---|---|
| `id-en-double` | ERROR | même `🆔` sur deux lignes du vault |
| `dependance-morte` | ERROR | `⛔` vers un `🆔` qui n'existe pas |
| `cycle-dependances` | ERROR | A dépend de B qui dépend de A |
| `jalon-franchissable` | INFO | toutes les dépendances d'un jalon sont faites : il attend sa validation |
| `jalon-sans-prefixe` | WARN | statut `[J]` sans `🏁 JALON — ` |
| `jalon-sans-statut` | WARN | `🏁` sur une tâche ouverte qui n'est pas `[J]` |
| `jalon-avec-energie` | WARN | tag d'énergie sur un jalon |
| `emoji-reserve-hors-tache` | WARN | `🆔`/`⛔` en décoration dans le texte |
| `tache-dans-journal` | WARN | tâche ouverte dans un journal |
| `tache-doublon-probable` | WARN | deux tâches ouvertes quasi identiques dans deux fichiers (Jaccard ≥ 0,5) |

## Écriture et dialogue

| Règle | Sév. | Ce qu'elle attrape |
|---|---|---|
| `tag-inline-hors-whitelist` | WARN | `#mot` dans le corps hors cas autorisés |
| `tag-hors-ligne-tache` | INFO | tag d'énergie hors ligne de tâche |
| `retour-chariot-en-phrase` | WARN | phrase coupée par un retour à la ligne (hors notes humaines) |
| `reponses-en-attente` | INFO | encart `[!todo] Réponse` vide : une question attend l'humain |
| `quote-sans-reponse` | WARN | commentaire de l'humain sans réponse imbriquée de l'agent |

## Structure du vault

| Règle | Sév. | Ce qu'elle attrape |
|---|---|---|
| `dossier-non-frontiere` | INFO | sous-dossier hors liste blanche : un dossier ne classe pas, il cloisonne |
| `agents-md-taille` | WARN | fichier d'instructions de l'agent au-delà de son plafond |

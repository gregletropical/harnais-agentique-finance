# Instructions de l'agent — extrait réécrit et générique

> Extrait du fichier `AGENTS.md` réel d'un second cerveau Obsidian d'environ 1 000 notes, lu par Claude Code et OpenCode à chaque session. Le fichier d'origine contient aussi des éléments personnels et des procédures propres à des clients : ils ont été retirés. Ce qui reste est la doctrine transposable, réécrite sans nom ni chiffre identifiant. Les règles marquées **[contrôlé]** sont vérifiées par `controles/lint_vault.py` ou par un garde-fou : l'agent les lit, mais elles ne reposent pas sur sa lecture.

---

## 1. Principe fondateur : le dossier ne classe pas, il cloisonne

Un dossier n'existe que s'il matérialise une **frontière de partage ou de confidentialité**. Tout le classement (thème, type, statut, provenance, durée de vie) est porté par les **properties du frontmatter**, requêtées par des vues.

- On ne déplace jamais une note pour la « ranger » : on met à jour ses métadonnées.
- Archiver = poser `status: archive`, jamais déplacer. Il n'y a pas de dossier d'archives, et c'est délibéré.
- Le volume n'est jamais un motif de créer un sous-dossier. La réponse au volume est la **vue**, pas l'arborescence.

Structure type :

```
0_inbox/            → capture rapide, seul dossier « de flux »
clients/<client>/   → un dossier par client : le client pourra un jour le lire
interne/            → l'activité propre, les outils, les process
journal/            → journaux quotidiens et hebdomadaires
people/             → fiches personnes, jamais partagées
ressources/         → tout ce qui n'a pas de frontière propre
  └── sujets/       → le vocabulaire fermé `sujet:` (une note par sujet)
_system/            → contexte global, vues, tableau de bord
_templates/         → modèles de notes
```

Conséquence directe pour l'agent : dans `clients/<client>/`, aucune note ne parle d'un autre client. Avant d'écrire, se demander **qui aura le droit de lire ce dossier**. **[contrôlé]** `dossier-non-frontiere` signale tout sous-dossier non déclaré.

Un dossier de projet ou de rôle contient une **note-tête** à son nom. Toute note du périmètre porte au moins un wikilink sortant, par défaut vers cette note-tête, dans une section `##### Refs` en tête de corps : le panneau de backlinks de la note-tête devient la vue vivante du dossier. **[contrôlé]** `note-orpheline`.

---

## 2. Properties : c'est là que se fait le classement

Une note mal renseignée est une note introuvable. Toute note créée porte :

```yaml
---
type:        # VOCABULAIRE FERMÉ — 17 types, un type par GESTE DE SAISIE.
             # Test de captation : un type doit être connaissable AU MOMENT où
             # l'on ouvre la note. Ce qui demande du recul est un `status`,
             # une `peremption` ou une property, jamais un type.
             # Dynamique : journal-daily | journal-weekly | log-meeting |
             #   log-session | draft-prompt | expression-besoin |
             #   projet-chantier | synthese-restit | wording | fiche-lecture
             # Statique : moc | documentation | arbitrage | valeur-okr |
             #   souvenir | personne
             # Process : process
status:      # incubation | slowburn | active | standby | done | avorte | archive
             # standby, avorte, archive = statuts ENDORMIS : leurs constats
             # passent en dette froide et ne remontent plus au briefing.
source:      # human | ai | mixte — l'auteur du CORPS
summary:     # OBLIGATOIRE — 1 à 2 phrases, 50 mots maximum
sujet:       # VOCABULAIRE FERMÉ — 1 à 3 wikilinks QUOTÉS vers ressources/sujets/
             #   - "[[compta]]"
projet:      # "[[Hub]]" — la cible est TOUJOURS une note `projet-chantier`
recurrence:  # hebdomadaire | mensuelle | trimestrielle | annuelle (hubs seulement)
focus:       # true (hubs seulement, 3 au maximum dans tout le vault)
lien:        # "[[...]]" — rattachement libre (un hub vers la note-tête de son client)
created:     # AAAA-MM-JJ
importance:  # 1-5 — jugement de VALEUR (à ne pas confondre avec focus, jugement de MOMENT)
peremption:  # AAAA | AAAA-MM | permanent — date de fin de valeur
---
```

**Règles non négociables :**

- **`source: human` = corps immuable.** L'agent ne retouche jamais le texte écrit par l'humain, sauf orthographe, mise en forme des titres et ajout de wikilinks. **[contrôlé]** `source-absent` : la règle ne protège que ce qui est qualifié.
- **Brut + retravail = deux notes liées** : la brute intacte, la synthèse à côté.
- **`sujet:` est un vocabulaire fermé, porté par des wikilinks.** Un sujet **est** une note de `ressources/sujets/` ; le dossier est la frontière d'habilitation. Créer un sujet = créer une note dans ce dossier, avec validation humaine. Obsidian ne contraint pas la cible d'un lien : la fermeture tient entièrement au lint, et la règle est « la cible est dans le dossier », jamais « la cible existe ». **[contrôlé]** `sujet-hors-vocabulaire`, `sujet-pas-un-wikilink`, `sujet-yaml-imbrique`.
- **[ATTENTION] Piège YAML** : `- [[compta]]` non quoté est du YAML valide qui parse en liste imbriquée, pas en chaîne. Les guillemets sont obligatoires.
- **Tags : jamais saisis à la main**, sauf trois cas fermés : les tags d'énergie `#deep`, `#creatif`, `#admin` sur les lignes de tâches ; les tags fonctionnels d'un plugin (`#task`) ; les marqueurs de ligne déclarés. Toute autre taxonomie en tags crée un second classement qui diverge. **[contrôlé]** `tag-inline-hors-whitelist`, `tags-en-frontmatter`, `diese-dans-frontmatter`.
- **Le `#` ne s'écrit que pour les titres.** Un `#` en début de mot dans le corps crée un tag silencieusement. Écrire « n° 1 », pas `#1`.
- **Aucun retour à la ligne en cours de phrase.** Le retour chariot porte du sens (paragraphe, item), il ne sert jamais à forcer une largeur de colonne. **[contrôlé]** `retour-chariot-en-phrase`, hors notes `source: human`.

---

## 3. Axe projet : la maille la plus fine du travail

- **Un projet = une note-hub** `type: projet-chantier`, jamais un dossier. Un projet avorté est une ligne `status: avorte`, pas un cadavre d'arborescence.
- **Les notes membres pointent vers le hub** (`projet: "[[Clôture annuelle 2026]]"`). La vue d'ensemble du chantier est le panneau de backlinks du hub.
- **Fractal** : un sous-hub pointe vers son hub parent avec la même property. Profondeur illimitée, aucune autre mécanique.
- **[RÈGLE DURE] La cible de `projet:` est toujours un hub.** Le rattachement à un client passe par l'emplacement et par `lien:`. Règle binaire. **[contrôlé]** `projet-cible-non-projet`, `projet-cible-introuvable`.
- **Hub récurrent** : une routine périodique est un hub permanent portant `recurrence:`. À chaque période, une note d'itération instancie la chaîne canonique ; l'itération est un enregistrement, jamais retouché après coup. L'écart entre elle et le hub mesure le progrès.
- **Journal du hub** : chaque session qui travaille un chantier ajoute une ligne `- **AAAA-MM-JJ** — <fait>` dans la section `## Journal` du hub. C'est la seule copie du détail.

## 4. Axe focus : ce qui se joue maintenant

`status: active` dit qu'un chantier est vivant, pas qu'il se joue cette semaine. `focus: true` le dit, sur un hub et rien d'autre, avec un **plafond dur de 3 dans tout le vault**. Au-delà, le lint sort un ERROR sur **chacun** des hubs focalisés : dépasser le plafond n'est pas la faute d'une note, c'est un arbitrage qui n'a pas été rendu. La property est absente par défaut (jamais `focus: false`). Le plafond compte aussi les hubs `done` : un focus oublié mange une place et se fait remarquer. **Qui la pose : l'humain, en revue hebdomadaire.** C'est l'acte de priorisation, il ne se délègue pas à l'agent. **[contrôlé]** `focus-hors-plafond`, `focus-hors-hub`, `focus-invalide`.

---

## 5. Tâches (plugin Tasks)

Une tâche se saisit **à sa source** — le hub du chantier, ou à défaut la note-tête du dossier — **jamais dans un journal**. Une tâche écrite dans un journal est une copie en puissance : une revue a trouvé plus de deux cents tâches ouvertes dans des journaux, dont une partie en double avec leur hub. **[contrôlé]** `tache-dans-journal`, `tache-doublon-probable`.

```markdown
- [ ] #task #deep Rapprocher le compte 512 avec les relevés [[Client A]] ⏱ 2h 📅 2026-11-15 🆔 c1a002 ⛔ c1a001
```

- `#task` obligatoire ; énergie `#deep` / `#creatif` / `#admin` ; aucun autre tag.
- Le contexte client ou projet ne se tague jamais : il est **hérité** du frontmatter et de l'emplacement de la note hôte.
- `[[Personne]]` sur la ligne = affectation ou destinataire ; `[[Agent]]` = tâche à réaliser par l'IA, que le briefing de début de session remonte.

| Statut | Sens |
|---|---|
| `[ ]` | à faire |
| `[/]` | en cours |
| `[w]` | en attente ou délégué (`📅` = date de relance) |
| `[?]` | idée, invisible des panneaux d'action ; cocher = promouvoir en `[ ]` |
| `[J]` | jalon : description préfixée `🏁 JALON — `, pas de tag d'énergie |
| `[x]` / `[-]` | fait / annulé |

**Dépendances, jalons, fractalité.** Critère de design : toute règle doit être applicable par un agent **sans jugement** (binaire, requêtable, contrôlable) — le « test de l'agent ».

- Dès qu'un ordre existe entre deux tâches, la dépendance se pose (`⛔`, fin → début uniquement).
- `🆔` est unique au vault ; `🆔` et `⛔` sont réservés aux lignes de tâches. **[contrôlé]** `id-en-double`, `dependance-morte`, `cycle-dependances`, `emoji-reserve-hors-tache`.
- Un **jalon** remplace toute « tâche mère » : il dépend de toutes ses filles, il est bloqué tant qu'une reste ouverte, et les tâches aval ne dépendent que de lui (un changement de périmètre ne recâble qu'une ligne). Le cocher est un geste de validation humaine, jamais un automatisme. **[contrôlé]** `jalon-sans-prefixe`, `jalon-avec-energie`, `jalon-sans-statut` ; `jalon-franchissable` signale un jalon dont toutes les dépendances sont faites.
- **[ATTENTION]** La récurrence `🔁` efface `🆔`/`⛔` à la régénération : une chaîne récurrente s'**instancie** (note d'itération), elle ne se régénère pas.
- **Fractalité par promotion** : l'indentation n'a aucune valeur analytique. Dès qu'une tâche a besoin d'un output textuel, de sous-tâches dépendantes ou de plusieurs sessions, elle est **promue en note** `projet-chantier` et la ligne déménage dedans (les `🆔` survivent au déplacement).
- Quand un sujet est accompli en session, l'agent cherche la tâche ouverte correspondante et la coche (`[x]` + `✅ AAAA-MM-JJ`), en demandant confirmation si le rapprochement n'est pas certain.

---

## 6. Dialogue humain-agent dans les notes de cadrage

- `> [!question]` : question de l'agent ; l'encart `> > [!todo] Réponse` y est imbriqué, réservé à l'humain. **[contrôlé]** `reponses-en-attente` (INFO) compte les encarts vides, le briefing de début de session les annonce.
- `> [!quote] Responsable` : commentaire libre de l'humain, à traiter comme un point à instruire. Charge inversée : un commentaire sans `> > [!check] Réponse agent` imbriqué est un travail de l'**agent** qui manque. **[contrôlé]** `quote-sans-reponse` (WARN), insensible à la casse.
- Une question réglée se replie, et sa décision rejoint un tableau append-only « Décisions actées », avec les options écartées.

## 7. Pas de mémoire tenue à la main

Le référentiel **est** le contexte de l'agent. Un fichier de mémoire inter-sessions chargé à chaque démarrage pesait près des trois quarts du coût de contexte imputable au référentiel, pour un contenu vérifié redondant fait par fait avec les notes de projet ; sa section « les 5 dernières » en portait 39. Il a été supprimé. Ce qui le remplace :

| Besoin | Où c'est |
|---|---|
| Faits durables sur l'utilisateur | `_system/Contexte Global.md`, seule chose lue au démarrage |
| Ce qui s'est passé sur un chantier | la section `## Journal` de son hub |
| Ce qui a été décidé | le tableau « Décisions actées » de la note |
| La vue agrégée « ce qui a bougé » | un script de digest, **calculé à la demande**, jamais chargé au démarrage |
| L'état du monde à l'instant t | calculé par le briefing de début de session |

**La règle** : un fait s'écrit une seule fois, à son étage, et on y renvoie par un wikilink. Une note tenue à la main diverge ; un calcul ne peut pas mentir. **[contrôlé]** `agents-md-taille` plafonne la taille du fichier d'instructions lui-même.

---

## 8. Contrôle plutôt que consigne

Toute règle dont la violation coûte cher est appliquée par une machine qui refuse ou signale, pas par un texte qu'on espère lu. Trois sévérités :

| Sévérité | Sens | Effet |
|---|---|---|
| **ERROR** | la note **ment** (valeur hors vocabulaire, graphe de tâches cassé) | à corriger ; `--strict` rend le code 1 |
| **WARN** | la note est **incomplète** | dette, traitée en lot |
| **INFO** | **signal** (question en attente, jalon à valider, hub dormant) | pas de dette |

Une consigne violée deux fois devient un contrôle. Un contrôle qui bloque à tort est corrigé, pas toléré : il pousserait à le contourner.

## 9. Commit (règle dure)

**[RÈGLE DURE]** `git add -A`, `git add .` et `git commit -a` sont **interdits** : un hook `PreToolUse` les refuse avant exécution. Motif : trois fois en un mois, un staging aveugle de fin de session a emporté le travail d'une session parallèle sous un message qui ne le décrivait pas.

| Situation | Commande |
|---|---|
| Début de session | `python controles/vault_commit.py --register --label "<poste-agent>"` |
| Fin de session, cas normal | `python controles/vault_commit.py --commit --push --id <SESSION> -m "…" -- <fichiers>` |
| Seul sur le vault | `… --commit --push --all --id <SESSION> -m "…"` (refusé dès deux sessions) |
| Qui travaille | `… --status` |

Le résidu affiché (fichiers modifiés non enregistrés dans Git) **se lit** : travail d'une autre session (on n'y touche pas) ou oubli (on l'ajoute). **Un code 2 n'est pas une panne**, c'est le garde-fou qui fonctionne : ne jamais le contourner par un `git` à la main ni par `push --force`. Auteur = la personne responsable, trailer `Session:`, jamais de ligne `Co-Authored-By` d'agent.

Quand l'agent édite un hub qu'une autre session tient déjà, le hook de bail l'en informe sans bloquer : **prévenir l'humain avant de poursuivre**.

---

## 10. L'agent autonome du serveur : un périmètre étroit et contrôlé

Un agent tourne sur un serveur, sur un modèle léger et **sans supervision de session**. Ses règles ne sont donc pas de la doctrine : ce sont des contraintes binaires, contrôlées.

| | |
|---|---|
| **Peut lire** | tout le vault de sa frontière |
| **Peut écrire** | le journal du jour, le journal de la semaine, `0_inbox/` — rien d'autre |
| **Jamais** | créer un dossier, déplacer, renommer, supprimer, commiter lui-même |

**Le périmètre est contrôlé, pas déclaré** : le programme de synchronisation qui enregistre son travail dans Git refuse tout fichier hors de ces chemins, et l'alerte se répète à chaque passe tant que le fichier est là. Un motif d'erreur répété se corrige dans **ses** instructions, jamais à la main.

**Contrepartie obligatoire : le triage.** Comme il ne peut pas écrire au bon endroit, sa production n'est jamais rangée. Il la marque (`triage: agent-autonome` en property sur une note, `#agent-autonome` sur une ligne), et une commande de triage en session la range et retire le marqueur. Le briefing de début de session compte ce qui attend. Ses commits portent sa propre identité : il écrit **sans** l'humain, et c'est précisément ce qu'on doit pouvoir distinguer dans l'historique.

**Sa mémoire native** (quelques milliers de caractères, réécrite par le modèle lui-même quand elle déborde) est un cache d'ergonomie, jamais une source de vérité : aucun chiffre, échéance ou fait client n'y vit. Ces faits sont dans le vault, datés et sourcés, et l'agent va les lire.

---

## Ce que l'agent ne fait jamais

- Créer un dossier qui ne correspond pas à une frontière de partage, en particulier au motif du volume.
- Déplacer une note pour la ranger.
- Créer une note sans `summary` ni `sujet:`, ou inventer une valeur de `sujet:`.
- Réécrire le corps d'une note `source: human`.
- Écrire une tâche dans un journal.
- Lancer un staging aveugle, contourner un code 2, pousser en force.
- Modifier le contexte global ou une note-tête sans validation humaine.
- Écrire du français sans accents, ou couper une phrase par un retour à la ligne.

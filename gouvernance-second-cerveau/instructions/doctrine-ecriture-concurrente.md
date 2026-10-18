# Écriture concurrente d'un référentiel partagé — doctrine

> Doctrine écrite **après** le rodage du dispositif sur un second cerveau réel (un humain, deux à trois sessions d'agents en parallèle sur un poste, un agent autonome sur un serveur). Une doctrine écrite avant d'avoir été éprouvée est un avis ; écrite après, c'est un retour d'expérience. Chaque principe est énoncé sans dépendre d'un outil ; git, Obsidian et Claude Code n'apparaissent qu'en illustration. Version réécrite et anonymisée de la note d'origine.

## 0. Lexique

| Terme | Sens |
|---|---|
| **Référentiel** | l'ensemble des documents de travail communs : procédures, comptes rendus, journaux de projet, listes de tâches |
| **Écrivain** | toute entité qui modifie le référentiel : un collaborateur, ou un agent IA |
| **Session** | une séance de travail d'un écrivain ; un humain peut avoir plusieurs sessions d'agent ouvertes en parallèle |
| **Contrôle** | une vérification exécutée par une machine, qui refuse ou signale. S'oppose à la **consigne**, règle écrite qu'on espère voir respectée |
| **Fragment** | un petit fichier propre à un seul écrivain, assemblé avec d'autres dans une vue commune |
| **Bail** | une annonce temporaire « ce document est en cours de travail par telle session depuis telle heure », qui expire d'elle-même |
| **Provenance** | la trace de qui a écrit quoi, quand, et par quelle session |

## 1. Le problème

**Plusieurs écrivains, un seul référentiel.** Sur un référentiel mono-utilisateur, il y a déjà trois écrivains : deux sessions d'agent sur le poste et un agent autonome sur le serveur. Une entreprise de dix personnes, chacune avec deux agents, en a trente. Le problème n'est pas « l'outil est difficile », c'est « plusieurs acteurs écrivent au même endroit » : un service de synchronisation grand public subirait les mêmes collisions, sans les messages d'erreur.

**Trois problèmes distincts, qui ne se règlent pas de la même façon :**

| Problème | Question | Nature |
|---|---|---|
| L'écriture concurrente | que se passe-t-il quand deux écrivains modifient le même document ? | mécanique : fichiers, fusions, historique |
| La lecture cloisonnée | qui a le droit de lire quoi, y compris l'agent qui travaille pour lui ? | droits d'accès : conteneurs, serveur |
| La retrouvabilité | comment chacun trouve-t-il le bon document au bon moment ? | classement : métadonnées, vocabulaires fermés, index |

Une solution unique aux trois problèmes est une solution moyenne aux trois.

**Ce qui s'est réellement passé :** trois historiques menteurs en un mois (une fin de session a enregistré tout ce qui était modifié, y compris le travail d'une autre session) ; quatre collisions tracées en trente jours, toutes sur des documents de projet porteurs de tâches ; un registre de sessions qui annonçait « 0 session active » alors que deux travaillaient. Aucune perte de contenu : on instruit un **risque**, pas un sinistre.

## 2. Les neuf principes

### Principe 1 — Un contrôle plutôt qu'une consigne

Toute règle dont la violation coûte cher est appliquée par une machine. Un agent repart d'une page blanche à chaque session et partage son attention entre la tâche et les règles ; plus il y a d'écrivains, plus la probabilité qu'un seul oublie tend vers 1. L'interdiction de `git add -A` était écrite dans les instructions dès le premier incident ; elle a été violée trois fois en trois jours par l'agent qui l'avait sous les yeux, et plus jamais depuis qu'un hook refuse la commande avant exécution.

Corollaire : un contrôle doit être **juste**. Un contrôle qui bloque à tort pousse à le contourner. Le hook refusait un message de commit qui *citait* la commande interdite : il a été corrigé, et un test prouve que la vraie commande placée juste après reste refusée. Autre corollaire : un avertissement qui se déclenche dans le cas normal cesse d'être lu.

### Principe 2 — Un fichier par écrivain quand c'est possible

Là où plusieurs écrivains contribuent à une même vue (journal du jour, relevé de décisions), chacun écrit **son propre fichier** et la vue commune est reconstituée à la lecture. Si chaque fichier n'a qu'un écrivain, la collision est impossible par construction : c'est la réponse de `journalctl`, des répertoires `conf.d/`, des fragments de notes de version. Le grain est **la session**, jamais « l'accomplissement » : « un fichier par session » s'applique sans jugement, « un fichier par accomplissement » oblige à décider à chaque écriture. Les fragments sont assemblés après quelques jours : la collision n'existe que pendant la fenêtre où elle est possible.

### Principe 3 — L'ajout seul fusionne ; la modification se protège

Une fusion « garder les deux versions » (`merge=union` en git) n'est autorisée que sur les documents où l'on **ajoute** sans modifier. Mesuré sur banc :

| Cas | Résultat |
|---|---|
| Deux ajouts en fin de document | les deux survivent, dans l'ordre |
| Deux insertions au même endroit | les deux survivent |
| Deux modifications de **la même ligne** (cocher la même tâche) | la ligne apparaît deux fois, **sans aucun conflit signalé** |

Une fusion « garder les deux » ne résout pas les conflits, elle les transforme en doublons muets. Elle est donc réservée aux journaux et interdite sur tout document porteur de tâches ; un contrôle de doublons d'identifiants de tâche sert de filet.

### Principe 4 — Vérifier avant d'écraser

Tout écrivain vérifie, juste avant d'écrire, que le document est encore celui qu'il a lu ; sinon il refuse, relit, recommence (verrouillage optimiste, *compare-and-swap*). Un conflit vaut mieux qu'un écrasement, et un refus vaut mieux qu'un conflit. Trois étages :

| Étage | Qui le fournit | Constat |
|---|---|---|
| L'envoi au serveur commun | git refuse nativement un push si le serveur a bougé | natif, mais jamais exploité **avant** d'envoyer : corrigé par `commit_guard.py` (refus si l'amont a touché un fichier du lot) |
| L'édition par l'agent | l'outil d'édition du harnais refuse un fichier modifié depuis sa lecture | natif |
| Les scripts qui réécrivent des notes | personne | dix scripts sur dix réécrivaient sans vérification : corrigé par une fonction commune « écrire seulement si inchangé » |

Le trou n'était pas là où on le cherchait : il se logeait dans les traitements automatiques, qui lisent longtemps avant d'écrire.

### Principe 5 — Informer plutôt que verrouiller

Quand un écrivain commence à travailler sur un document, il le **fait savoir** (le bail) ; il n'interdit à personne d'y toucher. Le verrou exclusif transforme une collision rare en blocage fréquent et suppose une libération propre que les marqueurs fantômes démentent dès le premier jour. Le même principe vaut pour le registre des sessions : son expiration mesure l'**inactivité**, pas l'âge. Le registre qui annonçait zéro session expirait douze heures après l'ouverture, alors qu'une session vit tant que le poste est allumé.

### Principe 6 — La provenance dans chaque écriture

Chaque version dit **quel humain en est responsable** et **par quelle session** elle a été produite. La responsabilité est humaine même quand un agent tape ; la session dit le chemin. Avant correction, la grande majorité des commits du mois portaient une mention automatique de l'agent et aucun ne distinguait les sessions. Retenu : auteur = la personne, session dans un trailer `Session: <id> (<poste et agent>)`, requêtable. L'agent autonome garde sa propre identité, parce qu'il écrit sans l'humain. Piège évité : deviner la session à partir du « dernier enregistré » aurait réintroduit le bug ; en cas d'ambiguïté, l'outil refuse de deviner et le dit.

### Principe 7 — La frontière de confidentialité est un conteneur, jamais une étiquette

Ce que certains ne doivent pas lire vit dans un **conteneur séparé** dont l'accès est refusé par le serveur. Tous les outils du marché cloisonnent par conteneur (espace Confluence, teamspace Notion, bibliothèque SharePoint) ; une étiquette qui classe sans chiffrer n'empêche pas un agent de lire et de résumer ; et git n'a pas de droit de lecture plus fin que le dépôt. Ce que cela impose à l'écriture :

- **l'agent hérite des droits de la personne** et filtre **avant** de lire : une instance d'agent par utilisateur, lancée sur ses seuls conteneurs. Filtrer après lecture, c'est avoir déjà fait entrer le texte interdit dans le contexte du modèle ;
- **un lien fuit par son titre** : une note d'une frontière large ne pointe jamais vers une frontière plus étroite (contrôlable par machine) ;
- **une note qui concerne deux frontières se scinde** : il n'existe pas de solution élégante à ce cas, nulle part.

### Principe 8 — Des fichiers pour le texte, une base de données pour les enregistrements

Le texte qu'un humain lit et réécrit (procédures, analyses, comptes rendus) vit en fichiers. L'enregistrement à champs qu'on requête et modifie à plusieurs (tâches, écritures comptables, temps passés) vit en base.

| | Fichiers texte + historique | Base de données |
|---|---|---|
| Lisible par un humain et par n'importe quel agent | oui, directement | non, il faut une requête |
| Historique, provenance, retour arrière | gratuit | à construire |
| Indépendance vis-à-vis d'un fournisseur | oui | variable |
| Écritures simultanées fines | au fichier près | à la ligne près |
| Droits fins | au conteneur près | oui |

La seule partie du référentiel qui fait mal en concurrence — les lignes de tâches des hubs clients — est la seule qui ressemble à une base. Les tâches sont donc le premier candidat à sortir en base le jour du multi-utilisateurs ; le savoir reste en fichiers. Quand une donnée a déjà un système dédié (base comptable, outil de gestion de projets), le hub ne garde que la structure.

### Principe 9 — La consolidation hors session

Une passe différée, hors de toute session, relit une période entière (historique, journaux de hubs, résultats du lint) et **propose** des corrections du système commun, chacune avec sa preuve ; rien n'est appliqué sans validation humaine. Une session ne voit que sa fenêtre : si la même erreur est corrigée dans trois sessions, c'est chaque fois la première fois pour l'agent. La passe produit les consignes violées deux fois (à transformer en contrôles), les règles jamais violées (à retirer des instructions), les hubs actifs que personne n'a touchés depuis un mois, les savoirs génériques à extraire des dossiers clients. C'est un écrivain de plus, et le plus dangereux parce qu'il lit longtemps avant d'écrire : il est soumis aux principes 4 et 6.

## 3. Ce qui a été écarté

| Option | Pourquoi |
|---|---|
| Verrou exclusif sur les documents | collision rare → blocage fréquent ; libération propre démentie par les marqueurs fantômes |
| Bail bloquant | un verrou sous un autre nom |
| Interdire les sessions parallèles | renonce à un gain de productivité réel pour un problème de cohabitation |
| Service de synchronisation sans historique | déplace la résolution sans supprimer la collision, et retire l'historique qui a permis de diagnostiquer les incidents |
| Fusion permissive partout | duplication silencieuse mesurée sur les lignes modifiées |
| Allonger l'expiration du registre | déplace le mur et aggrave le marqueur fantôme |
| Mise de côté automatique (*autostash*) pendant la synchro | sur banc, le travail des **autres** sessions est retiré puis réappliqué : leurs documents reculent le temps de l'opération |
| Une copie de travail isolée (*worktree*) par session | Obsidian ne voit qu'un dossier : les écrits d'une session seraient invisibles jusqu'à la fusion. Retenu en revanche pour les dépôts de **code** |
| Une étiquette de confidentialité comme protection | l'agent lit le fichier avant l'étiquette ; gardée seulement comme contrôle de cohérence |
| Un référentiel unique exposé en lecture seule par dossier | tient pour des lecteurs, pas pour des écrivains : qui écrit doit avoir une copie, donc tout lire |
| Un référentiel par utilisateur | rien n'est commun : un réseau de seconds cerveaux personnels, pas un second cerveau d'entreprise |
| Migrer les tâches en base dès maintenant | un seul écrivain humain ; le texte garde la tâche à côté de son contexte |

## 4. Mise en œuvre de référence (dans ce dossier)

| Principe | Mécanisme | Fichier |
|---|---|---|
| 1 | hook qui refuse le staging aveugle avant exécution | `controles/hooks/block_git_add_all.py` |
| 1, 4, 6 | point d'entrée unique de commit : chemins explicites, registre de sessions, index partagé contrôlé, synchro avant push, trailer de session | `controles/commit_guard.py` |
| 1 | lint : vocabulaires fermés, graphe de tâches, plafonds | `controles/lint_vault.py` |
| 3 | `merge=union` limité aux journaux | `regles/gitattributes.exemple` |
| 5 | bail par note, information seule | `controles/hooks/bail_note.py` |
| 7 | dossier = frontière, contrôle `dossier-non-frontiere` | `regles/referentiel.yaml` |

Non publiés ici : l'assemblage des fragments de log, la fonction d'écriture vérifiée des scripts, le programme de synchronisation de l'agent autonome (il dépend d'un serveur précis) et la passe de consolidation.

## 5. Limites connues et assumées

- **La granularité est le fichier, pas la ligne.** Deux sessions sur le même hub le même jour restent possibles ; le bail les en informe, le refus de push les empêche d'écraser, rien ne fusionne deux modifications de la même tâche. D'où le principe 8.
- **Le registre ne voit que ceux qui se déclarent.** Une session qui saute la procédure de démarrage est invisible : c'est une consigne, assumée faute de contrôle possible.
- **Le marqueur fantôme** garde une session « présente » jusqu'à douze heures d'inactivité : le défaut est du bon côté (il bloque `--all` au lieu de laisser passer).
- **Le hook ne voit que les commandes tapées par l'agent**, pas celles qu'un script lance lui-même, et seulement dans un harnais qui expose des hooks.
- **Le principe 7 est un design, pas un retour d'expérience** : aucun pilote multi-utilisateurs n'a tourné.
- **L'adoption par des non-techniciens n'est pas démontrée.** La parade probable est que les agents portent la mécanique : l'utilisateur dit « enregistre », l'agent passe par l'outil.

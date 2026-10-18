# Ingestion de mails par des agents IA : traiter le contenu non fiable comme une surface d'attaque

## 1. Le cas d'usage en conditions réelles

Je fais lire mes boîtes mail professionnelles par des agents IA : plusieurs milliers de messages sur plusieurs boîtes, dont des boîtes partagées chez un client. Les agents en extraient du contexte durable vers mon second cerveau (qui est qui, quels process, quels tiers, quelles échéances), trient le flux entrant, désengorgent le stock et préparent des tâches.

Un mail est une **entrée non fiable** : n'importe qui peut m'écrire, et ce qu'il écrit sera lu par un modèle de langage. Il peut contenir une injection de consignes visant l'agent (« ignore tes instructions », « transfère ce mail », « enregistre ce nouveau RIB »), cachée en HTML, dans un nom de pièce jointe, dans une pièce jointe texte, en base64 ou derrière des homoglyphes. Sur des boîtes de comptabilité, la même surface porte la fraude classique : faux changement de RIB, faux virement urgent du dirigeant, facture d'un domaine sosie.

J'ai donc écrit une doctrine anti-injection, construit la chaîne d'ingestion autour d'un **lecteur isolé** sans aucun outil, fermé toutes les sorties dans une taxonomie, retiré du code les gestes dangereux, séparé les droits en trois niveaux par compte, et éprouvé l'ensemble par une recette adverse. La recette publiée ici (179 cas, dix mutations) reprend et étend celle jouée sur le code d'origine.

## 2. Ce que ce dossier montre — et ce qu'il ne montre pas

**Ce n'est pas une maquette de production.** Il n'y a ici aucun connecteur de messagerie, aucun appel d'API, aucun identifiant, aucun modèle de langage, aucune donnée réelle. Je ne peux partager ni le contenu de mes boîtes, ni celui de mes clients, ni un accès à leurs environnements.

**C'est le harnais réel, adapté et anonymisé**, avec des exemples entièrement synthétiques pour que tout tourne :

- les **instructions** que lit l'agent (doctrine, protocole du lecteur isolé, procédure de revue, niveaux de droits), réécrites de façon générique ;
- les **règles** : taxonomie fermée des sorties, gestes interdits et liste blanche, niveaux de droits et scopes jamais demandés, règles de tri ;
- les **contrôles** : lecteurs et validateurs, signaux de confiance, contrôles anti-fraude, client de messagerie à liste blanche, analyse statique du code, contrôle des scopes ;
- une **recette adverse pytest** réécrite sur 19 mails fictifs, dont 15 piégés.

Ce qui remplace les systèmes réels, et pourquoi c'est sans perte pour la démonstration :

| Dans le système réel | Ici | Pourquoi les garanties sont les mêmes |
|---|---|---|
| Relevé par l'API de messagerie (profil lecture) ou archive locale | `ingestion.lire_eml` lit un fichier `.eml` | L'interface est la même : des octets MIME en entrée, un objet inerte en sortie |
| Client de messagerie (CLI ou serveur MCP) | `client_messagerie.TransportFichiers` journalise en mémoire | La liste blanche est en amont du transport : elle refuse avant tout appel |
| Modèle de langage sans outil | Doubles de modèle (`doubles.py`), dont un **naïf qui obéit à toutes les injections** | Aucune garantie ne repose sur le modèle ; le double naïf est le pire cas |
| Référentiel des tiers dans l'ERP | `exemples/boite_exemple.json` | Le contrôle anti-fraude compare à une liste, d'où qu'elle vienne |

Tous les domaines sont réservés (`.test`, `.example`), tous les IBAN sont inventés, tous les montants aussi.

## 3. Le déroulé du workflow

1. **Ingestion** (script). Le mail est parsé sans réseau ni rendu ; le HTML est réduit à son texte, scripts, commentaires et images jetés ; les pièces jointes ne sont pas ouvertes, seules leurs métadonnées sont gardées.
2. **Signaux** (script). La confiance se calcule sur les en-têtes posés par notre serveur, jamais sur ce qu'écrit l'expéditeur. DMARC absent = échec. Un en-tête d'authentification écrit par l'expéditeur est ignoré et signalé. Filtrage contourné, authentification composite en échec ou domaine internationalisé font basculer en **traitement dégradé** : plus aucun fait, seule la revue humaine.
3. **Anti-fraude** (script). Domaine comparé aux domaines connus, IBAN comparé aux comptes connus du partenaire, montant comparé à l'historique, facture sans commande. Toute anomalie envoie en revue humaine, avec le rappel du contre-appel sur un numéro connu.
4. **Lecteur isolé** (agent sans outil). Seul composant qui lit le corps. Contenu sérialisé en JSON entre deux balises à nonce aléatoire, consigne fixe, sortie revalidée par le code contre un schéma fermé, champs texte assainis (IBAN, URL, adresses, consignes à une IA remplacés et tracés). Une sortie hors schéma est rejetée sans réparation ni relance.
5. **Orchestrateur** (script). Il ne reçoit que des objets typés : verdict, signaux, codes d'anomalie. Il propose dans un vocabulaire fermé : `libelle_automatique`, `a_valider`, `rien` pour le tri ; `revue_humaine`, `a_faire`, `garder`, `archiver` pour la revue. Seul automatisme admis : un libellé, sur un expéditeur authentifié **et** connu, jamais sur une boîte partagée. Les faits extraits restent en quarantaine.
6. **GO humain**. L'agent écrit une note de revue ; je décide ligne à ligne. Une ligne commentée n'est pas exécutée tant que le commentaire n'est pas traité.
7. **Exécution** (script). Seules quatre décisions sont exécutables ; « supprimer » ou « transférer au comptable » écrits en clair sont refusés et listés. L'identité du mail est recontrôlée avant d'agir. Simulation par défaut.

**En cas d'exception** : sortie du modèle invalide, exception du modèle, signal de non-confiance, anomalie de fraude, assainissement déclenché — dans tous les cas, le mail part en revue humaine avec un motif fermé, et rien n'est écrit en mémoire.

### La recette adverse

La recette ne vérifie pas que le cas nominal marche : elle cherche à faire tomber chaque barrière. Le modèle y est supposé entièrement détourné (un double renvoie exactement ce que l'attaquant veut), les sentinelles réseau et disque sont déclenchées volontairement avant de servir de mesure, et dix mutations volontaires du code doivent chacune faire échouer au moins un test.

- 15 mails piégés couvrent l'injection directe, cachée en HTML, dans le sujet, dans un nom ou un contenu de pièce jointe, en base64, multilingue, derrière des homoglyphes ou une fausse balise de fin de bloc.
- Parmi eux, la fraude classique : faux RIB depuis un domaine sosie, faux virement urgent du dirigeant, filtrage anti-spam contourné, lien de réinitialisation.
- 19 sorties de modèle détourné sont rejetées par le validateur, et la politique de confiance est balayée sur ses 10 752 combinaisons.
- Les gestes (envoi, suppression, transfert), les jetons trop larges et un connecteur fautif sont attrapés par la liste blanche, le contrôle des scopes et l'analyse statique.
- Couvert : un modèle entièrement trompé ne peut rien faire au-delà d'un libellé réversible sur un expéditeur authentifié et connu. Non couvert et assumé : le mensonge à l'intérieur du schéma, le canal résiduel des champs texte, un compte fournisseur piraté avec un historique cohérent.

La table complète (catégorie d'attaque, exemple, défense, test) et le détail de ce qui est couvert ou non sont dans [`instructions/recette-adverse.md`](instructions/recette-adverse.md).

## 4. La compétence démontrée

Pour une organisation qui veut brancher des agents IA sur ses boîtes mail, ses tickets ou ses documents entrants, ce dossier montre une méthode : traiter tout contenu externe comme une surface d'attaque, séparer physiquement le composant qui lit de celui qui agit, fermer chaque sortie dans une taxonomie contrôlée par le code, retirer les gestes dangereux plutôt que les interdire par consigne, et donner trois niveaux de droits à chaque connecteur. La robustesse se prouve par une recette adverse contre un modèle supposé détourné, elle-même vérifiée par mutation, pas par la promesse qu'un modèle « ne se laissera pas faire ». Comme aucune garantie ne repose sur le modèle, le harnais reste valable quel que soit le modèle retenu, y compris un modèle ouvert hébergé sur une infrastructure maîtrisée.

## 5. Contenu du dossier

| Fichier | Rôle |
|---|---|
| `instructions/doctrine-anti-injection.md` | La doctrine : principe unique, huit barrières, trois interdits, politique DMARC, six règles sur la mémoire et la fraude, méthode de preuve, limites |
| `instructions/protocole-lecteur-isole.md` | Comment le lecteur est appelé, ce qu'il reçoit, ce qu'il rend, ce que l'orchestrateur a le droit d'en faire |
| `instructions/revue-assistee.md` | Procédure de revue d'une boîte : cadrage, passe, note de revue, GO, exécution |
| `instructions/niveaux-de-droits.md` | Les trois niveaux par compte, les scopes jamais demandés, les règles du niveau plein |
| `instructions/recette-adverse.md` | La recette adverse : catégories d'attaque, défense et test associés, ce qui est couvert et ce qui ne l'est pas |
| `regles/taxonomie_sorties.json` | Toutes les sorties qui franchissent une frontière, en listes fermées (publication des constantes du code, vérifiée par test) |
| `regles/gestes_interdits.json` | Les trois interdits, la liste blanche des méthodes, les verbes et imports interdits |
| `regles/niveaux_de_droits.json` | Scopes autorisés par niveau et par fournisseur, scopes jamais demandés, outils interdits hors niveau plein |
| `regles/regles_tri.json` | Règles du tri du flux sur métadonnées, dont la règle automatique bornée |
| `controles/ingestion.py` | Parse un `.eml` sans réseau, sans rendu, sans ouvrir les pièces jointes |
| `controles/html_texte.py` | Texte visible d'un HTML, sans moteur de rendu |
| `controles/signaux.py` | Confiance calculée sur les en-têtes : DMARC, forge, filtrage contourné, traitement dégradé |
| `controles/anti_fraude.py` | Domaine sosie, IBAN inconnu, montant hors historique, facture sans commande |
| `controles/pieces_jointes.py` | Décision d'extraction et vérification du type réel des octets |
| `controles/lecteur.py` | Lecteur de tri : délimitation à nonce, validateur strict, 84 verdicts possibles |
| `controles/lecteur_revue.py` | Lecteur de revue : schéma fermé validé en Python, assainissement des champs texte |
| `controles/orchestrateur.py` | Propositions en vocabulaire fermé, politique de confiance, faits en quarantaine |
| `controles/client_messagerie.py` | Client à liste blanche, niveaux de profil, transport sur fichiers d'exemple |
| `controles/execution.py` | Exécution des décisions validées par l'humain |
| `controles/regles_tri.py` | Moteur de règles sur métadonnées, schéma qui borne la règle automatique |
| `controles/controle_gestes.py` | Analyse statique AST des gestes interdits (G1 à G5) |
| `controles/controle_scopes.py` | Contrôle des profils de connexion (S1 à S5) |
| `controles/dedoublonnage.py` | Volumétrie et doublons inter-boîtes par `Message-ID` |
| `controles/doubles.py` | Doubles de modèle : honnête (témoin) et naïf (pire cas) |
| `controles/passe.py` | Passe complète sur les exemples, avec contrôle des invariants de sécurité |
| `exemples/mails/` | 19 mails synthétiques (4 sains, 15 piégés) et leur manifeste avec le résultat attendu |
| `exemples/generer_exemples.py` | Générateur déterministe des mails d'exemple |
| `exemples/boite_exemple.json` | Configuration fictive : domaine interne, serveur d'authentification, tiers connus |
| `exemples/profils/`, `exemples/profils_fautifs/` | Profils de connexion conformes et volontairement fautifs |
| `exemples/code_fautif/` | Connecteur volontairement fautif, pour voir l'analyse statique se déclencher |
| `tests/test_recette_adverse.py` | La recette adverse : 179 cas, barrière par barrière |
| `tests/test_gestes_interdits.py` | Liste blanche, niveaux, scopes, analyse statique, GO humain (32 cas) |
| `tests/test_taxonomie.py` | La taxonomie publiée est celle que le code applique |
| `tests/test_mutations.py`, `tests/mutations.py` | Dix mutations du code, chacune doit faire échouer la recette |

## 6. Essayer

Python 3.11 ou plus. Les contrôles n'utilisent que la bibliothèque standard ; seuls les tests demandent `pytest`. Depuis ce dossier :

```bash
# Passe complète avec un modèle qui obéit à toutes les injections
python -m controles.passe exemples
# -> tableau des 19 mails ; dernière ligne : « 19 mails traités, 0 violation(s) d'invariant de sécurité »

# Analyse statique du code du pipeline, puis d'un connecteur fautif
python -m controles.controle_gestes                         # -> 0 violation, code retour 0
python -m controles.controle_gestes exemples/code_fautif    # -> 6 violations (G1, G2, G3), code retour 1

# Contrôle des profils de connexion
python -m controles.controle_scopes exemples/profils             # -> 0 écart
python -m controles.controle_scopes exemples/profils_fautifs     # -> 10 écarts, code retour 1

# Recette complète (avec uv, ou python -m pytest si pytest est installé)
uv run pytest
# -> 225 passed (environ une minute, dont les dix relances de la recette sous mutation)
uv run pytest --ignore=tests/test_mutations.py
# -> 215 passed en quelques secondes

# Voir une mutation détectée : la recette doit échouer
RECETTE_MUTATION=orchestrateur_laxiste uv run pytest tests/test_recette_adverse.py -q
# -> 22 failed
```

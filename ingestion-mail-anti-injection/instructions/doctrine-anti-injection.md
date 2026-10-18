# Doctrine anti-injection pour une entrée non fiable

Doctrine réutilisable pour tout agent qui lit un contenu produit par un tiers non contrôlé : un mail, mais aussi un formulaire, un ticket de support, un document déposé, une page web ou la sortie d'une API tierce.
Le principe, les huit barrières et les six règles complémentaires ne dépendent d'aucune spécificité du courrier électronique.
Seule la politique de confiance du §5 est propre au mail, parce qu'elle s'appuie sur un signal du protocole (DMARC) ; chaque canal doit définir le sien.

Chaque règle de ce document est **vérifiable** : la colonne « où c'est contrôlé » renvoie au code et au test de ce dossier qui la font respecter.
Une règle qui ne se vérifie que par relecture n'est pas une barrière, c'est un vœu.

## 1. Quand cette doctrine s'applique

Dès qu'un agent va lire un contenu qu'un tiers contrôle et qu'un humain n'a pas validé avant lecture.

La cause du risque n'est pas la boîte mail, c'est la réunion de trois conditions, la « lethal trifecta » décrite par Simon Willison (juin 2025) : accès à des données privées, exposition à du contenu non fiable, capacité d'exfiltration vers l'extérieur.
Retirer une seule des trois branches suffit à rendre l'attaque impossible.
Cette doctrine retire systématiquement la troisième, l'exfiltration, parce que c'est la seule qu'un système de lecture peut abandonner sans perdre sa raison d'être.
Elle réduit aussi la deuxième autant que possible : ce qui est non fiable ne touche qu'un composant qui ne peut rien faire.

## 2. Le principe unique

**Le contenu d'une entrée non fiable est une donnée, jamais une instruction.**

Toutes les barrières ci-dessous sont la mise en œuvre technique de cette phrase.
Jamais une consigne au modèle de « faire attention » : toujours une contrainte que le système ne peut pas contourner, même quand le modèle est trompé.

Vocabulaire de référence : OWASP Top 10 pour les applications LLM, entrée `LLM01: Prompt Injection`.
Une entrée lue en tâche de fond relève de l'injection **indirecte** : l'attaquant n'écrit pas dans le prompt, il écrit dans une donnée que le système ira lire.

## 3. Les huit barrières

Dans l'ordre où elles bloquent une attaque : plus une barrière est haute, plus elle coupe tôt.

| # | Barrière | Ce qu'elle bloque | Mise en œuvre | Où c'est contrôlé |
|---|---|---|---|---|
| 1 | Aucun accès réseau sortant pendant le traitement | L'exfiltration par appel réseau, canal exact d'`EchoLeak` (CVE-2025-32711, injection sans clic dans un assistant bureautique, exfiltration par chargement de ressource distante) | Le composant qui parse et lit le contenu travaille sur des octets locaux, sans aucune requête sortante | `controle_gestes.py` (G1, G2) ; `test_b1_aucun_acces_reseau` sous sentinelle `socket.connect`, elle-même auto-contrôlée |
| 2 | Jamais de rendu | Le chargement d'une image ou d'une ressource distante embarquée, à la fois traqueur et canal d'exfiltration ; l'exécution de script | On extrait le texte, on ne rend rien ; aucun moteur de rendu dans les dépendances | `html_texte.py` ; `test_b2_*` |
| 3 | Aucune ouverture de pièce jointe | L'exécution d'une macro, l'exploitation d'un parseur, un fichier déguisé | On stocke nom, type déclaré, taille et empreinte ; on n'ouvre pas, on ne décompresse pas. L'extraction de texte, si elle est permise, est une étape séparée et conditionnelle (règle 6 du §6) | `ingestion.py`, `pieces_jointes.py` ; `test_b3_*` |
| 4 | Contenu délimité et neutralisé avant tout modèle | La confusion entre instruction et donnée, c'est-à-dire l'injection elle-même | Texte brut, tronqué, caractères invisibles et bidirectionnels retirés, sérialisé en JSON, encadré par des balises à nonce aléatoire, consigne fixe qui ne dépend jamais du contenu. Le sujet et les noms de pièces jointes sont **dans** le bloc, jamais à côté | `lecteur.preparer`, `lecteur_revue.preparer` ; `test_b4_*` |
| 5 | Sortie du modèle contrainte à un schéma fermé | Le détournement du modèle vers une action arbitraire, quel que soit le contenu lu. C'est la barrière la plus efficace du lot | Le lecteur ne produit qu'un objet validé contre un schéma fermé, sans réparation, sans repli permissif, sans relance ; le motif de rejet est lui-même un code fermé | `lecteur.valider_sortie`, `lecteur_revue.valider_sortie` ; `test_b5_*` |
| 6 | Séparation des rôles lecteur / orchestrateur | La propagation d'une instruction injectée vers un composant capable d'agir | Le lecteur voit le contenu et n'a aucun outil ; l'orchestrateur a les outils et ne voit jamais le contenu brut. La frontière est un **type**, pas une consigne | `orchestrateur.py` ; analyse AST (G5) ; `test_b6_*` dont un balayage exhaustif de la politique |
| 7 | Séparation physique des droits | Qu'une lecture produise une écriture, par erreur de raisonnement du modèle ou de l'humain | Un jeton par niveau (lecture, maintenance, plein) ; le jeton de lecture est *techniquement* incapable d'écrire faute de scope. Le lecteur, lui, ne détient aucun jeton du tout | `controle_scopes.py`, `client_messagerie.py` ; `test_b7_*`, `test_gestes_interdits.py` |
| 8 | Politique de confiance calculable pour l'action | Qu'une action automatique s'applique à une entrée dont l'origine n'est pas vérifiable | Une action automatique exige une origine authentifiée par un signal calculable **et** un émetteur déjà en relation ; tout le reste n'est qu'une proposition soumise à l'humain | `signaux.py`, `orchestrateur.decider` ; `test_b8_*` |

> **Le filtre du canal n'est pas une barrière, et le croire est un risque en soi.**
> Un tri amont (dossier spam, modération d'un formulaire) est utile pour l'analyse, mais il ne protège de rien : une attaque ciblée est précisément conçue pour passer ce filtre.
> Les huit barrières s'appliquent à **toute** entrée, quel que soit le tri dont elle est issue.

## 4. Les trois interdits

Trois gestes à ne jamais accorder à un traitement automatisé, sous aucun prétexte ni même à titre d'essai.
Ce sont exactement ceux qu'un attaquant cherche à obtenir.

- **Aucune ouverture de lien ou de ressource distante référencée dans l'entrée.**
- **Aucun envoi automatique** : toute sortie rédigée (réponse, message, publication) reste un brouillon soumis à validation humaine.
- **Aucune suppression** : les gestes autorisés sont additifs et réversibles (libeller, classer, archiver), jamais destructifs.

Ces interdits ne sont pas écrits dans un prompt.
Ils sont absents du vocabulaire de l'orchestrateur (`PROPOSITIONS`, `DECISIONS_REVUE`), absents de la liste blanche du client de messagerie (`regles/gestes_interdits.json`), refusés par l'analyse statique du code (G3) et absents des scopes demandés (`regles/niveaux_de_droits.json`).
Quatre contrôles indépendants pour la même règle : si l'un saute, les trois autres tiennent.

## 5. Politique de confiance pour le mail (DMARC)

Instanciation, pour le canal mail, de la barrière 8.

**Ce qu'on accorde à un message aligné DMARC et connu.**
Un message dont le verdict DMARC est `pass` **et** qui provient d'un émetteur déjà en relation peut alimenter une proposition automatique ou un geste additif et réversible (un libellé), dans le respect strict des barrières 5 à 7.
Jamais un accès direct à un outil, jamais une action irréversible.

**Ce qu'on refuse à un message en échec ou sans verdict.**
Aucune automatisation, même partielle : seule une proposition soumise à validation humaine.
**Un verdict absent est un échec, jamais un neutre**, et une valeur inconnue devient `absent`.
Les vieux messages ne portent souvent aucun verdict exploitable : la politique ne s'applique donc qu'au flux entrant, jamais rétroactivement pour qualifier un stock ancien.

**Seul l'en-tête posé par notre serveur compte.**
Un expéditeur peut écrire lui-même un `Authentication-Results: ... dmarc=pass` dans son message.
On ne lit que l'en-tête dont l'identifiant de serveur est le nôtre, et tout autre en-tête portant un résultat est signalé comme une tentative de forge.

**DMARC n'autorise jamais à traiter le corps comme une instruction.**
DMARC authentifie le domaine émetteur, pas le contenu.
Un expéditeur légitime peut avoir un compte compromis, ou relayer sans le savoir un contenu piégé : le corps reste délimité (barrière 4) et lu par le seul composant sans outil (barrière 6).
À l'inverse, un attaquant qui possède un domaine sosie obtient un DMARC `pass` parfaitement valide : l'authentification ne dit rien de la légitimité, d'où les contrôles anti-fraude de la règle 5 du §6.

**Vérification.**
Les verdicts se calculent hors ligne depuis les en-têtes, sans appeler aucun service.
Tout traitement d'action déclenché sans verdict `pass` rattaché à une relation connue doit échouer explicitement, jamais tomber sur une valeur par défaut permissive.

## 6. Six règles complémentaires : la mémoire et les boîtes exposées

Ajoutées après un essai : un lecteur isolé a déjoué un faux changement de RIB, puis a quand même écrit un faux fait durable sur le tiers usurpé.
Aucune des huit barrières ne couvrait ce cas.
C'est la phase « persistance » de la *promptware kill chain* (Brodt, Feldman, Schneier, Nassi, janvier 2026) : l'entrée ne cherche plus à faire agir l'agent, elle cherche à **écrire dans sa mémoire** pour être relue plus tard comme une vérité.

| # | Règle | Où c'est contrôlé |
|---|---|---|
| 1 | **Un fait extrait d'une entrée n'entre jamais en mémoire (second cerveau, base, mémoire d'agent) sans validation humaine.** Jamais, même ensuite, s'il vient d'une entrée suspecte, non authentifiée ou d'un émetteur inconnu. Un fait extrait est une affirmation de l'émetteur, datée et sourcée, pas une connaissance : il reste en quarantaine | `orchestrateur.faits_candidats` ; `test_5bis_persistance_bloquee`, `test_5bis_aucun_fait_tire_d_un_mail_piege` |
| 2 | **La sortie du lecteur est vérifiée par le code**, pas seulement par sa consigne : toute valeur texte contenant un IBAN, une URL, une adresse de courriel ou une formule adressée à une IA est remplacée, et le rejet est tracé | `lecteur_revue.assainir` ; `test_b5_assainissement_des_champs_texte` |
| 3 | **Les champs texte libres du lecteur sont un canal résiduel** vers l'orchestrateur : bornés en longueur, affichés à l'humain, jamais interprétés comme des consignes. Là où c'est possible, on les supprime : le lecteur de tri n'a aucun champ libre (84 verdicts possibles) | `lecteur_revue.SCHEMA` (`maxLength`) ; `test_b5_capacite_du_canal` |
| 4 | **Signal de non-confiance calculé sur les en-têtes posés à l'entrée** : filtrage contourné (`SFV:SK*`), `compauth=fail`, catégorie anti-spam non vide, DMARC autre que `pass` hors courrier interne, en-tête d'authentification forgé, domaine internationalisé. Ce signal fait basculer en **traitement dégradé** : métadonnées gardées, aucun fait tiré, seule proposition la revue humaine | `signaux.py` ; `test_5bis_traitement_degrade` |
| 5 | **La fraude comptable se contrôle par du code contre le référentiel des tiers, pas par le modèle** : domaine comparé aux domaines connus (distance d'édition, inclusion, homographes), IBAN cité comparé aux comptes connus du partenaire, montant comparé à l'historique, facture sans commande signalée. Toute anomalie déclenche une revue humaine. **Le contre-appel sur un numéro déjà connu reste humain par nature**, et un mail authentifié n'en dispense jamais | `anti_fraude.py` ; `test_5bis_fraude_controlee_par_le_code`, `test_5bis_domaines_sosies` |
| 6 | **Pièces jointes d'une boîte exposée** : seuls les types attendus, vérifiés sur le type réel des octets et non sur l'extension, d'un expéditeur authentifié et d'un domaine autorisé ; un domaine nouveau se présente à l'humain avant toute extraction. Aucune URL extraite n'est suivie. Le texte extrait repasse par le lecteur, jamais par l'orchestrateur | `pieces_jointes.py` ; `test_b3_extraction_conditionnelle` |

## 7. Prouver plutôt que promettre

Une doctrine ne vaut que par sa recette.
Trois principes de méthode, appliqués dans `tests/` :

1. **Le modèle est supposé entièrement détourné.** La recette remplace le modèle par un double qui renvoie exactement ce que l'attaquant veut. Si rien ne franchit la frontière dans ce pire cas, un vrai modèle ne peut pas faire pire. La défense ne dépend donc pas de la robustesse du modèle choisi, ce qui la rend indépendante du fournisseur.
2. **Les instruments sont auto-contrôlés.** Avant de compter « 0 connexion réseau », on vérifie que la sentinelle crie quand on la déclenche volontairement. Un 0 est une mesure, pas un silence.
3. **La recette est elle-même testée par mutation.** Dix mutations volontaires du code (validateur permissif, balises non neutralisées, orchestrateur laxiste, exception propagée, sujet recopié dans la consigne, verdict absent traité comme neutre, en-tête forgé accepté, assainissement désactivé, faits versés sans contrôle, liste blanche ouverte) doivent chacune faire échouer au moins un test. Un test qui ne sait pas échouer est un faux sentiment de sécurité.

## 8. Ce que cette doctrine ne couvre pas

Il n'existe **aucune défense fiable et générale** contre l'injection indirecte à ce jour.
Les approches de recherche (patron dual LLM, classifieurs de détection) réduisent le risque, aucune ne l'annule.
Le consensus est architectural, pas algorithmique : on ne rend pas l'agent incapable d'être trompé, on le rend incapable de nuire quand il est trompé.

Limites assumées, à connaître avant de déployer :

- **Un modèle détourné peut mentir à l'intérieur du schéma.** Classer un message piégé en « Clients, urgence haute » est une sortie valide. C'est pourquoi un verdict de modèle peut abaisser la confiance, jamais l'élever : seul un geste additif et réversible (un libellé) reste possible sur un émetteur authentifié et connu, et c'est un risque résiduel accepté.
- **Les champs texte bornés restent un canal**, même assainis : un attaquant peut faire écrire une phrase trompeuse sans URL ni IBAN dans un résumé d'action. Elle est montrée à l'humain, jamais exécutée.
- **Le texte caché par CSS n'est pas filtré.** Il est délimité comme le reste, mais il atteint le modèle.
- **La table d'homoglyphes est partielle.** Une table complète (Unicode TR39) est préférable en production.
- **Un compte légitime compromis avec historique cohérent** (même domaine, même IBAN, montant habituel) passe les contrôles anti-fraude : seul le contre-appel humain le détecte.

Un dernier angle mort fréquent d'une doctrine centrée sur « empêcher l'agent de nuire » : **les données collectées sont elles-mêmes un actif à protéger**.
Une copie de contenus confidentiels de tiers n'entre jamais dans un dépôt versionné ni dans un second cerveau partagé, vit sur un volume chiffré, et sa durée de conservation est décidée à l'avance.

## Sources

- Simon Willison, « The lethal trifecta for AI agents », juin 2025 : les trois conditions du risque d'exfiltration (§1).
- Brodt, Feldman, Schneier, Nassi, *promptware kill chain*, janvier 2026 : la phase de persistance en mémoire (§6).
- CVE-2025-32711 (« EchoLeak ») : injection sans clic dans un assistant bureautique, exfiltration par chargement de ressource distante (barrière 1).

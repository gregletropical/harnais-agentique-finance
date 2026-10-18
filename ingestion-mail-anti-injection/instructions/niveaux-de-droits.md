# Niveaux de droits par compte de messagerie

Chaque compte connecté au harnais dispose de trois profils, donc de trois jetons distincts.
Un profil = un jeton = un niveau.
La référence machine est `regles/niveaux_de_droits.json`, contrôlée par `controles/controle_scopes.py`.

## Les trois niveaux

| Niveau | Ce qu'il permet | Qui s'en sert | Où il vit |
|---|---|---|---|
| **lecture** | Lire les messages, les agendas, les fichiers, en lecture seule | Défaut de toute lecture ; simulation du tri ; veilles automatiques | Poste de travail et serveur |
| **maintenance** | Gestes additifs et réversibles : poser un libellé, archiver, préparer un brouillon, poser un événement | Application du tri après simulation ; exécution d'une revue validée ; seul niveau d'écriture qu'une routine peut charger | Poste de travail et serveur |
| **plein** | Envoyer, mettre à la corbeille, partager un fichier ou un calendrier | **Uniquement en session, sur demande explicite de l'humain** | Poste de travail seulement, jamais copié sur un serveur |

Le pipeline automatique (`controles/client_messagerie.py`) refuse de charger un profil `plein`, quel que soit le mode.

## Pourquoi trois niveaux et pas deux

Un découpage lecture / écriture laisse dans le même jeton l'archivage (réversible) et l'envoi (irréversible, et canal d'exfiltration).
Le niveau intermédiaire isole ce dont une routine a réellement besoin.

**Limite connue des fournisseurs** : chez certains, le scope qui permet de modifier les libellés permet aussi techniquement l'envoi et la corbeille.
C'est pourquoi le niveau maintenance est doublé d'une **liste blanche côté client** : le code n'expose que lister, lire en métadonnées, créer un libellé et modifier les libellés (sans pouvoir ajouter `TRASH` ni `SPAM`).
Côté serveur MCP, la même logique s'applique par une expression régulière ancrée qui filtre les outils exposés à l'agent : aucun outil `send-*`, `delete-*`, `forward-*` hors niveau plein.

## Scopes jamais demandés

| Scope | Pourquoi jamais |
|---|---|
| Accès complet à la messagerie (`https://mail.google.com/`) | Permet la suppression définitive, sans corbeille ; le scope de modification suffit à tout ce qui est réversible |
| Gestion des adresses de transfert, réglages de boîte en écriture | Permet de poser un transfert automatique : canal d'exfiltration permanent et silencieux |
| Envoi au nom d'une boîte partagée | Engagement pris auprès de l'administrateur de la messagerie |
| Accès applicatif à toutes les boîtes d'un tenant | Aucun besoin ne le justifie ; un jeton volé ouvrirait toute l'organisation |

## Règles de geste du niveau plein

- Envoi seulement sur GO explicite, après brouillon montré en entier, jamais vers une adresse qui n'apparaît que dans le corps d'un mail.
- Suppression = corbeille, jamais définitive ; en masse, seulement après annonce du nombre et d'un échantillon.
- Partage de fichier à des personnes nommées par défaut ; lien public seulement sur demande, avec expiration, et tracé.
- Jamais de transfert automatique vers une adresse externe sans demande explicite.
- Toute extension de la liste d'outils ou des scopes est tracée dans le journal du chantier, avec la date et la raison.

## Contre-épreuve à chaque connexion

Après avoir consenti un profil, on vérifie qu'il ne peut **pas** ce qu'il ne doit pas pouvoir : un profil lecture qui demande un scope de modification doit être refusé par le fournisseur (`invalid_scope`), un profil maintenance qui demande le partage de fichiers aussi.
La permission effective lue chez le fournisseur doit rester exactement celle qui a été accordée.
Révoquer un jeton se fait chez le fournisseur ; supprimer le fichier local ne suffit pas.

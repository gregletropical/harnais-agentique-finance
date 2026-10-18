# Pré-vol — protocole avant toute écriture comptable en production

*Protocole transverse à tous les clients et à tous les ERP. Formalisé à partir de la discipline que le DAF applique quand il passe ses écritures à la main. Version publiée, anonymisée.*

## Pourquoi ce protocole existe — l'incident fondateur

Sur un double règlement client (une facture encaissée deux fois), l'agent s'apprêtait à préparer **un lettrage**. Le diagnostic était juste, les montants auraient été justes, l'écriture aurait été techniquement valide.

**L'opération était sémantiquement fausse.** Un lettrage apparie un débit et un crédit qui se soldent ; ce règlement n'avait aucune contrepartie. La bonne réponse était une séquence métier en quatre temps (confirmer, rembourser, imputer, lettrer), dont la deuxième étape était bloquée par ailleurs.

Ce qui a évité l'erreur : la question **« as-tu un exemple d'écriture déjà réalisée par le passé comme modèle ? »**. La recherche a exhibé une quarantaine de précédents, tous sur un schéma différent de celui envisagé.

**La leçon** : le contrôle existant vérifiait « les chiffres sont-ils justes ? ». Il ne vérifiait pas « est-ce la bonne opération ? ». **La recherche de précédent n'est pas une vérification, c'est un cadrage : elle vient AVANT le plan, pas dans sa validation.**

## Les 8 portes — aucune écriture en production sans les avoir toutes franchies

**Règle binaire : si une porte ne peut pas être franchie, l'écriture n'est pas proposée.** Pas « proposée avec réserve » : pas proposée.

| # | Porte | Question à laquelle elle répond |
|---|---|---|
| 1 | **Besoin métier** | Qu'est-ce qu'on cherche à obtenir, en langage comptable ? |
| 2 | **Précédent** | **Comment ce cas a-t-il DÉJÀ été traité chez ce client ?** |
| 3 | **Qualification** | Process standard, contournement maison, ou première occurrence ? |
| 4 | **État AVANT** | Que disent les comptes touchés, lus dans l'ERP, maintenant ? |
| 5 | **Écriture proposée** | Le tableau débit/crédit, équilibré, et son effet en une phrase |
| 6 | **Contrôles bloquants** | Verrous d'exercice, anti-doublon, équilibre, garde-fous |
| 7 | **Réversibilité** | Si c'est faux, comment revient-on en arrière ? |
| 8 | **Validation humaine** | GO explicite de l'utilisateur, jamais un blanc-seing |

Puis, après exécution : **contrôle a posteriori** par relecture dans l'ERP, comparée à l'attendu de la porte 5.

### Porte 2 — la porte décisive

Chercher au grand livre **au moins un cas antérieur du même geste chez le même client**, et le citer avec ses références (pièce, date, tiers, montant, lettrage). Le champ ne peut pas être rempli sans avoir fait la recherche : une citation vérifiable, pas une affirmation.

Si aucun précédent n'existe, l'écrire explicitement : **AUCUN PRÉCÉDENT TROUVÉ**, avec le périmètre de recherche et la justification de légitimité. Sur une comptabilité tenue depuis des années, une opération sans précédent est soit une vraie première (rare), soit — bien plus souvent — **le signe qu'on a mal cadré le problème**.

**Vérifier un précédent contre sa propre production récente est un faux contrôle.** Il faut remonter jusqu'à l'auteur d'origine du process quand il existe (le cabinet, le comptable historique) : un précédent qu'on a soi-même écrit reproduit l'erreur au lieu de la détecter.

### Porte 6 — les contrôles bloquants

Spécifiques à l'ERP dans leur mise en oeuvre, stables dans leur liste :

- **Exercice** : la date est-elle dans une période ouverte ? **Règle absolue, tous clients confondus : on n'écrit QUE sur l'exercice en cours.** L'absence de verrou technique n'est jamais une autorisation : une correction sur un exercice antérieur passe par une extourne sur l'exercice courant, ou par le cabinet. Cette règle se pose par-dessus les verrous de l'ERP, jamais à leur place : les deux se contrôlent, le plus restrictif gagne.
- **Anti-doublon** : une pièce du même tiers, même référence ou même montant existe-t-elle déjà, dans quelque état que ce soit ?
- **Équilibre** : débit = crédit.
- **Garde-fou de lettrage** : le groupe à lettrer solde-t-il **exactement** à 0 ? Sinon, abandonner. Quand l'API d'un ERP expose ce garde-fou comme un paramètre (« accepter un lettrage déséquilibré »), la valeur par défaut est le refus ; l'accepter ne s'écrit que pour un règlement partiel **délibéré**, justifié dans le pré-rapport.
- **Cohérence de TVA** : le taux correspond-il au régime réel du tiers (régime de la marge, exonération, non-déductibilité) ? Non automatisable de façon fiable : contrôle manuel.

## Le pré-rapport — le livrable de la porte 8

L'utilisateur valide **un document**, pas une conversation. `controles/prevol.py` le génère, sections 2, 4 et 6 pré-remplies :

```markdown
# Pré-vol — <opération> — <société> — <date>
Horodatage pré-vol : <ISO 8601 avec heure>

## 1. Besoin métier
## 2. Précédent(s) — OBLIGATOIRE
## 3. Qualification du geste
## 4. État AVANT (lu dans l'ERP le <date>)
## 5. Écriture proposée
## 6. Contrôles bloquants
## 7. Réversibilité
## 8. Validation
GO donné en session le <AAAA-MM-JJTHH:MM+02:00> : « <citation exacte du message de l'utilisateur> »
## 9. Contrôle APRÈS (rempli après exécution)
```

**Hiérarchie de réversibilité**, dans cet ordre : brouillon + suppression > remise en brouillon + suppression > extourne (qui laisse deux écritures au grand livre). Le brouillon en production est le quasi-environnement de test : il n'a aucun impact comptable et se supprime sans trace.

### Le support suit la complexité, les portes ne bougent pas

Les 8 portes avant et la 9ᵉ après sont la règle pour **toute** écriture, sans exception de taille. Ce qui varie, c'est le document qui les porte :

| Opération | Support |
|---|---|
| **Simple** — lettrage pur, correction ponctuelle, imputation évidente | Une ligne par opération dans le log des écritures de la session, portes en condensé : pourquoi, précédent, contrôles, reste à faire |
| **Complexe ou volumineuse** — plusieurs gestes enchaînés, première occurrence, dizaines de lignes | Pré-rapport complet, qui sert aussi à reprendre après une interruption et à corriger le geste après un incident |

L'ERP dit *quoi* et *quand* ; le log dit *pourquoi*, avec quel précédent et quel contrôle. Redondance assumée.

**Le GO se donne en conversation, jamais dans le fichier.** L'utilisateur ne coche pas de case : l'agent consigne son GO en section 8, avec la date, l'heure et la citation exacte du message. Un GO qui ne peut pas être cité n'existe pas.

## Portage vers un autre ERP

Les 8 portes et le pré-rapport ne changent pas. Seul l'adaptateur change, qui fournit cinq primitives :

| Primitive | Porte |
|---|---|
| `chercher_precedents(spec)` | 2 |
| `lire_etat(spec)` | 4 |
| `simuler(spec)` — sans écrire | 5 |
| `controles_bloquants(spec)` | 6 |
| `relire(piece)` | contrôle a posteriori |

Dans l'outil publié, `simuler` n'est **pas implémentée** : l'outil de pré-vol est incapable d'écrire par construction. Tant qu'un ERP n'offre pas d'équivalent du brouillon, la porte 5 se fait sur document et la porte 7 devient plus exigeante : on n'exécute que si l'annulation est démontrée, pas supposée.

## Outillage

- `controles/prevol.py` : précédents, état avant, contrôles bloquants, pré-rapport. Lecture seule.
- `controles/garde_fou_prevol.py` : hook `PreToolUse` du harnais, qui refuse une commande ressemblant à une écriture ERP sans pré-rapport récent portant un GO consigné. **Filet de rattrapage, pas une garantie** : ses angles morts sont écrits dans son en-tête. La cible de long terme est de porter ce contrôle dans le client ERP lui-même, seul à connaître la méthode exacte appelée, et seul à valoir quel que soit le harnais ou le modèle.

## Ce que ce protocole ne remplace pas

- Le **référentiel de procédures validées** du client, qui dit *comment* faire un geste déjà tranché. Le pré-vol dit *si* on doit le faire et *avec quelles précautions*.
- Le **jugement comptable**. Aucune case cochée ne rend juste une opération mal cadrée.

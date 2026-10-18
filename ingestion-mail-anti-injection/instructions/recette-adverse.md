# Recette adverse : attaques, défenses, tests

La recette (`tests/test_recette_adverse.py`, 179 cas ; `tests/test_gestes_interdits.py`, 32 cas) ne vérifie pas que le cas nominal marche : elle cherche à faire tomber chaque barrière de la [doctrine](doctrine-anti-injection.md). Les références B1 à B8 renvoient aux barrières de la doctrine, G1 à G5 à l'analyse statique (`controles/controle_gestes.py`), S1 à S5 au contrôle des scopes (`controles/controle_scopes.py`).

## 1. Trois principes qui la rendent probante

- **Le modèle est supposé entièrement détourné** : un double renvoie exactement ce que l'attaquant veut ; si rien ne passe dans ce pire cas, un vrai modèle ne peut pas faire pire.
- **Les instruments sont auto-contrôlés** : les sentinelles réseau et disque sont déclenchées volontairement avant de servir de mesure.
- **La recette est testée par mutation** : dix mutations volontaires du code (`tests/mutations.py`) doivent chacune faire échouer au moins un test (de 1 à 22 échecs selon la mutation).

## 2. Catégories d'attaque

| Catégorie d'attaque | Exemple | Défense | Test |
|---|---|---|---|
| Injection directe, usurpation du système, champ d'action forgé | `04_injection_directe.eml` | Délimitation à nonce (B4), rejet `champ_inconnu` (B5), DMARC en échec (B8) | `test_b5_sortie_detournee_rejetee` |
| Injection cachée en HTML : texte masqué, blanc sur blanc, commentaire, script, pixel distant, depuis un compte légitime compromis | `05_injection_html_cachee.eml` | Extraction sans rendu (B2), texte caché délimité (B4), assainissement de la sortie | `test_b2_html_sans_rendu`, `test_b2_texte_cache_reste_une_donnee_delimitee` |
| Faux administrateur : nom affiché trompeur, domaine sosie, en-tête d'authentification forgé | `06_faux_administrateur.eml` | Seul l'en-tête de notre serveur compte, forge signalée ; sosie par inclusion | `test_b8_entete_auth_forge_ignore` |
| Consigne dans une pièce jointe texte, tentative de persistance (faux RIB à mémoriser) | `07_consigne_piece_jointe.eml` | Texte de la pièce dans le bloc ; `iban_inconnu` ; assainissement ; aucun fait | `test_5bis_persistance_bloquee` |
| Fichier déguisé (archive ZIP en `.txt`) | `08_piece_jointe_deguisee.eml` | Type réel vérifié sur les octets, jamais décompressé (B3) | `test_b3_piece_jointe_jamais_ouverte` |
| Fraude au dirigeant : sosie authentifié, urgence, confidentialité | `09_virement_urgent_dirigeant.eml` | `domaine_sosie`, `iban_sans_partenaire`, `montant_hors_historique` | `test_5bis_fraude_controlee_par_le_code` |
| Faux changement de RIB depuis un sosie du fournisseur | `10_changement_rib_sosie_fournisseur.eml` | Distance d'édition, IBAN inconnu, facture sans commande | `test_5bis_fraude_controlee_par_le_code` |
| Hameçonnage par lien de réinitialisation | `11_lien_reinitialisation.eml` | Aucun lien suivi, sentinelle réseau (B1) ; URL refusée en sortie ; règle `suspect` | `test_b1_aucun_acces_reseau` |
| Unicode trompeur : homographe dans le domaine, inversion bidi, largeur nulle, homoglyphes | `12_unicode_trompeur.eml` | Drapeau `domaine_non_ascii`, squelette d'homoglyphes, invisibles retirés | `test_b4_bidi_et_largeur_nulle_retires`, `test_5bis_domaines_sosies` |
| Charge utile dans le sujet et le nom de pièce jointe | `13_injection_sujet_et_nom_pj.eml` | Sujet et noms dans le bloc, une seule occurrence | `test_b4_sujet_et_nom_pj_dans_le_bloc` |
| Instruction en base64 « décode et exécute » | `14_base64_decode_execute.eml` | Jamais décodé par la chaîne ; motif refusé en sortie | `test_b4_base64_jamais_decode` |
| Fausse balise de fin de bloc, rupture de JSON | `15_fausse_balise_rupture_json.eml` | Nonce imprévisible, balises cassées, JSON sur une ligne | `test_b4_fausse_balise_neutralisee` |
| Filtrage anti-spam contourné sur un tiers connu | `16_filtrage_contourne.eml` | Traitement dégradé : aucun fait, revue humaine seule | `test_5bis_traitement_degrade` |
| Injection multilingue | `17_multilingue.eml` | Protection structurelle, pas lexicale | `test_b4_structure_invariante` |
| Demande de texte libre et de champ supplémentaire | `18_texte_libre_et_faux_champ.eml` | Rejet sans réparation, motif fermé | `test_b5_sortie_detournee_rejetee` |
| 19 sorties de modèle détourné (texte libre, clé dupliquée, homoglyphe dans une énumération, JSON suivi de texte, NaN, imbrication profonde...) | en ligne | Validateur strict du lecteur | `test_b5_sortie_detournee_rejetee` |
| Mensonge à l'intérieur du schéma | en ligne | L'orchestrateur n'élève jamais la confiance sur la foi du modèle ; balayage exhaustif de 10 752 combinaisons | `test_b6_mensonge_encaisse`, `test_b6_balayage_exhaustif_de_la_politique` |
| Envoi, suppression, corbeille, transfert par le client de messagerie | en ligne | Liste blanche, niveau plein interdit au pipeline, `TRASH`/`SPAM` refusés en ajout | `test_gestes_interdits.py` |
| Jeton trop large (suppression définitive, transfert automatique, plein sur serveur, outils d'envoi en lecture) | `exemples/profils_fautifs/` | Contrôle des scopes S1 à S5 | `test_profils_fautifs_detectes` |
| Connecteur qui envoie, exécute ou suit un lien | `exemples/code_fautif/` | Analyse AST G1 à G5 | `test_connecteur_fautif_detecte` |
| Témoins : mails légitimes, doublon inter-boîtes | `01`, `02`, `03`, `19` | Pas de sur-blocage ; une décision par `Message-ID` | `test_temoin_negatif_mail_legitime`, `test_dedoublonnage_inter_boites` |

## 3. Ce que la défense couvre, et ce qu'elle ne couvre pas

**Couvert** : un modèle entièrement trompé ne peut ni envoyer, ni supprimer, ni suivre un lien, ni ouvrir une pièce jointe, ni écrire un fait en mémoire, ni déclencher un geste au-delà d'un libellé réversible sur un expéditeur authentifié et connu. Ce n'est pas une affirmation sur le modèle : c'est une propriété du code, vérifiée par la recette.

**Non couvert, et assumé** :

- **le mensonge dans le schéma** : un compte légitime compromis peut obtenir un libellé automatique erroné sur un mail piégé (cas `05`) ; c'est le risque résiduel accepté, additif et réversible ;
- **le canal résiduel des champs texte** du lecteur de revue : une phrase trompeuse sans URL ni IBAN peut atteindre la note de revue ; elle est affichée, jamais exécutée ;
- **le texte caché par CSS** atteint le modèle, délimité comme le reste ;
- **la table d'homoglyphes est partielle** (une table Unicode TR39 complète serait préférable) ;
- **un compte fournisseur piraté avec un historique cohérent** passe les contrôles anti-fraude : seul le contre-appel humain le détecte ;
- **le comportement d'un vrai modèle** face aux injections n'est pas mesuré ici, volontairement : la défense ne doit pas en dépendre ;
- **la barrière réseau est testée au niveau Python** (sentinelle sur les sockets) ; elle doit se doubler, en production, d'un environnement sans route sortante, que ce dépôt ne peut pas montrer.

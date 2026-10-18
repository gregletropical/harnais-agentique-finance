-- stg_projet : projets de l'outil de gestion de projets, rattachés à leur groupe client (référentiel MDM).
-- Un projet interne n'a pas de groupe par construction ; un projet client sans rattachement garde
-- id_groupe NULL : c'est le contrôle « production sans groupe client » qui le relève, pas une jointure
-- interne qui le ferait disparaître en silence.
CREATE TABLE stg_projet AS
SELECT p.id_projet, p.libelle, p.client, p.interne, p.entite,
       CASE WHEN p.interne = 1 THEN NULL ELSE x.id_groupe END AS id_groupe
FROM raw_projets p
LEFT JOIN ref_xref_client x ON x.client = p.client;

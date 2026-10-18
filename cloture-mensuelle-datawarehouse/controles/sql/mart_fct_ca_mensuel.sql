-- mart_fct_ca_mensuel : CA et marge brute produits par mois et groupe client (projets clients seuls :
-- les projets internes portent du coût hors marge brute de production).
CREATE TABLE mart_fct_ca_mensuel AS
SELECT periode AS mois, id_groupe, ROUND(SUM(ca), 2) AS ca, ROUND(SUM(mb), 2) AS mb
FROM stg_cutoff
WHERE interne = 0
GROUP BY periode, id_groupe;

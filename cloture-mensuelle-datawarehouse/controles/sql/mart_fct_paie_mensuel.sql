-- mart_fct_paie_mensuel : coût de paie mensuel (charges patronales comprises) depuis le livre de paie.
CREATE TABLE mart_fct_paie_mensuel AS
SELECT mois, COUNT(DISTINCT matricule) AS effectif, ROUND(SUM(montant), 2) AS cout_total
FROM stg_paie_livre_compte
GROUP BY mois;

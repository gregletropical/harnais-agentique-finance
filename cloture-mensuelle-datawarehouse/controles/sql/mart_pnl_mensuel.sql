-- mart_pnl_mensuel : P&L comptable mensuel par poste (produits positifs, charges négatives).
CREATE TABLE mart_pnl_mensuel AS
SELECT mois, poste_pnl, sous_poste, ROUND(SUM(montant_signe), 2) AS montant
FROM stg_gl_pnl
GROUP BY mois, poste_pnl, sous_poste;

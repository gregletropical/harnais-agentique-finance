-- stg_gl_pnl : lignes de classes 6 et 7 du grand livre, classées au poste P&L par le préfixe de compte
-- le plus long de la taxonomie. Un compte sans poste (orphelin) garde poste_pnl NULL et bloque le pipeline.
CREATE TABLE stg_gl_pnl AS
SELECT g.entite, g.journal, substr(g.date, 1, 7) AS mois, g.piece, g.compte, g.tiers,
       ROUND(g.credit - g.debit, 2) AS montant_signe,
       (SELECT t.poste_pnl FROM ref_taxonomie_pnl t WHERE g.compte LIKE t.prefixe_compte || '%'
        ORDER BY length(t.prefixe_compte) DESC LIMIT 1) AS poste_pnl,
       (SELECT t.sous_poste FROM ref_taxonomie_pnl t WHERE g.compte LIKE t.prefixe_compte || '%'
        ORDER BY length(t.prefixe_compte) DESC LIMIT 1) AS sous_poste
FROM raw_grand_livre g
WHERE substr(g.compte, 1, 1) IN ('6', '7');

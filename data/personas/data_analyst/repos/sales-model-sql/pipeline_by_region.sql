-- SYNTHETIC sample code for GigBid persona data_analyst. provenance: personas@228603469f77
-- Weekly pipeline by region and rep (star schema: fact_deals, dim_rep, dim_date)
SELECT d.week_start,
       r.region,
       r.rep_name,
       SUM(f.amount) FILTER (WHERE f.stage = 'won')  AS won_amount,
       SUM(f.amount) FILTER (WHERE f.stage <> 'lost') AS open_pipeline,
       COUNT(*)                                      AS deals
FROM fact_deals f
JOIN dim_rep r  ON r.rep_id = f.rep_id
JOIN dim_date d ON d.date_id = f.created_date_id
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 4 DESC;

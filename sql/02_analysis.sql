-- Bad-buy (kick) analysis. Each query answers one buying question.
-- Run:  psql -U postgres -d kicked -f /project/sql/02_analysis.sql

\echo '== Q1. Which makes kick most? (makes with 300+ cars, ranked, with lift vs. fleet average)'
WITH fleet AS (
    SELECT avg(isbadbuy) AS fleet_rate FROM purchases
), by_make AS (
    SELECT make, count(*) AS cars, avg(isbadbuy) AS kick_rate
    FROM purchases
    GROUP BY make
    HAVING count(*) >= 300
)
SELECT make,
       cars,
       round(100 * kick_rate, 1)                                   AS kick_pct,
       round(kick_rate / fleet_rate, 2)                            AS lift_vs_fleet,
       rank() OVER (ORDER BY kick_rate DESC)                       AS risk_rank,
       round(100.0 * sum(cars) OVER (ORDER BY kick_rate DESC)
             / sum(cars) OVER (), 1)                               AS cum_pct_of_volume
FROM by_make CROSS JOIN fleet
ORDER BY kick_rate DESC;

\echo '== Q2. Age x mileage grid: kick rate and volume per cell'
SELECT vehicle_age,
       mileage_band,
       count(*)                          AS cars,
       round(100 * avg(isbadbuy), 1)     AS kick_pct
FROM purchases
GROUP BY vehicle_age, mileage_band
HAVING count(*) >= 50
ORDER BY vehicle_age, mileage_band;

\echo '== Q3. Auction houses: monthly kick rate, 3-month rolling rate, and change vs. previous month'
WITH monthly AS (
    SELECT auction,
           date_trunc('month', purch_date)::date AS month,
           count(*)                            AS cars,
           sum(isbadbuy)                       AS kicks
    FROM purchases
    GROUP BY auction, date_trunc('month', purch_date)
)
SELECT auction,
       month,
       cars,
       round(100.0 * kicks / cars, 1)                                         AS kick_pct,
       -- volume-weighted rolling rate, not an average of averages
       round(100.0 * sum(kicks) OVER w3 / sum(cars) OVER w3, 1)               AS kick_pct_3mo,
       round(100.0 * kicks / cars
             - 100.0 * lag(kicks) OVER w / lag(cars) OVER w, 1)               AS pp_change_vs_prev
FROM monthly
WINDOW w  AS (PARTITION BY auction ORDER BY month),
       w3 AS (PARTITION BY auction ORDER BY month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
ORDER BY auction, month;

\echo '== Q4. Riskiest model within each of the top 10 makes by volume'
WITH top_makes AS (
    SELECT make FROM purchases GROUP BY make ORDER BY count(*) DESC LIMIT 10
), by_model AS (
    SELECT p.make, p.model, count(*) AS cars, avg(isbadbuy) AS kick_rate
    FROM purchases p JOIN top_makes USING (make)
    GROUP BY p.make, p.model
    HAVING count(*) >= 100
), ranked AS (
    SELECT *,
           row_number() OVER (PARTITION BY make ORDER BY kick_rate DESC) AS rn,
           avg(kick_rate) OVER (PARTITION BY make)                      AS make_avg_of_models
    FROM by_model
)
SELECT make, model, cars,
       round(100 * kick_rate, 1)           AS kick_pct,
       round(100 * make_avg_of_models, 1)  AS make_model_avg_pct
FROM ranked
WHERE rn = 1
ORDER BY kick_rate DESC;

\echo '== Q5. Does paying above market predict kicks? Kick rate by price-to-MMR quintile'
WITH q AS (
    SELECT *, ntile(5) OVER (ORDER BY price_to_mmr) AS price_quintile
    FROM purchases
    WHERE price_to_mmr IS NOT NULL
)
SELECT price_quintile,
       round(min(price_to_mmr), 2)       AS ratio_from,
       round(max(price_to_mmr), 2)       AS ratio_to,
       count(*)                          AS cars,
       round(100 * avg(isbadbuy), 1)     AS kick_pct
FROM q
GROUP BY price_quintile
ORDER BY price_quintile;

\echo '== Q6. Missing wheel-type flag by auction house (the single strongest raw signal)'
SELECT auction,
       count(*) FILTER (WHERE wheel_type = 'Missing')                                   AS missing_cars,
       round(100 * avg(isbadbuy) FILTER (WHERE wheel_type = 'Missing'), 1)              AS kick_pct_missing,
       round(100 * avg(isbadbuy) FILTER (WHERE wheel_type <> 'Missing'), 1)             AS kick_pct_present,
       round(100.0 * count(*) FILTER (WHERE wheel_type = 'Missing') / count(*), 1)      AS pct_missing
FROM purchases
GROUP BY auction
ORDER BY auction;

\echo '== Q7. Buyers: each buyer vs. their own trailing 3 months (top 5 buyers by volume)'
WITH top_buyers AS (
    SELECT buyer_id FROM purchases GROUP BY buyer_id ORDER BY count(*) DESC LIMIT 5
), m AS (
    SELECT buyer_id, date_trunc('month', purch_date)::date AS month,
           count(*) AS cars, sum(isbadbuy) AS kicks
    FROM purchases JOIN top_buyers USING (buyer_id)
    GROUP BY buyer_id, date_trunc('month', purch_date)
)
SELECT buyer_id, month, cars,
       round(100.0 * kicks / cars, 1) AS kick_pct,
       round(100.0 * sum(kicks) OVER t / nullif(sum(cars) OVER t, 0), 1) AS trailing_3mo_pct,
       sum(cars) OVER (PARTITION BY buyer_id ORDER BY month)              AS cumulative_cars
FROM m
WINDOW t AS (PARTITION BY buyer_id ORDER BY month ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING)
ORDER BY buyer_id, month;

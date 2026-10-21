-- Segment extracts for the Tableau dashboard (written to /project/tableau/).
-- Run:  psql -U postgres -d kicked -f /project/sql/03_tableau_exports.sql

-- One row per segment value, long format, so one Tableau sheet can switch dimension with a parameter.
\copy (WITH fleet AS (SELECT avg(isbadbuy) AS r FROM purchases), seg AS (SELECT 'Make' AS dimension, make AS segment, isbadbuy FROM purchases UNION ALL SELECT 'Vehicle age', vehicle_age || ' yrs', isbadbuy FROM purchases UNION ALL SELECT 'Mileage band', mileage_band, isbadbuy FROM purchases UNION ALL SELECT 'Auction house', auction, isbadbuy FROM purchases UNION ALL SELECT 'Size', size, isbadbuy FROM purchases UNION ALL SELECT 'Wheel type', wheel_type, isbadbuy FROM purchases) SELECT dimension, segment, count(*) AS cars, sum(isbadbuy) AS kicks, round(avg(isbadbuy), 4) AS kick_rate, round(avg(isbadbuy) / max(fleet.r), 2) AS lift_vs_fleet FROM seg CROSS JOIN fleet WHERE segment IS NOT NULL GROUP BY dimension, segment HAVING count(*) >= 100 ORDER BY dimension, kick_rate DESC) TO '/project/tableau/segment_risk.csv' WITH (FORMAT csv, HEADER true)

\copy (SELECT vehicle_age, mileage_band, count(*) AS cars, round(avg(isbadbuy), 4) AS kick_rate FROM purchases GROUP BY 1, 2 ORDER BY 1, 2) TO '/project/tableau/age_mileage_grid.csv' WITH (FORMAT csv, HEADER true)

\copy (SELECT auction, date_trunc('month', purch_date)::date AS month, count(*) AS cars, sum(isbadbuy) AS kicks, round(avg(isbadbuy), 4) AS kick_rate FROM purchases GROUP BY 1, 2 ORDER BY 1, 2) TO '/project/tableau/auction_monthly.csv' WITH (FORMAT csv, HEADER true)

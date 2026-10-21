-- Load Kaggle training.csv into Postgres and expose a cleaned, typed view.
-- Run inside the container:  psql -U postgres -d kicked -f /project/sql/01_load.sql

DROP TABLE IF EXISTS raw_purchases CASCADE;
CREATE TABLE raw_purchases (
    refid int PRIMARY KEY,
    isbadbuy smallint NOT NULL,
    purchdate text,
    auction text,
    vehyear int,
    vehicleage int,
    make text,
    model text,
    trim text,
    submodel text,
    color text,
    transmission text,
    wheeltypeid int,
    wheeltype text,
    vehodo int,
    nationality text,
    size text,
    topthreeamericanname text,
    mmr_acq_auction_avg numeric,
    mmr_acq_auction_clean numeric,
    mmr_acq_retail_avg numeric,
    mmr_acq_retail_clean numeric,
    mmr_cur_auction_avg numeric,
    mmr_cur_auction_clean numeric,
    mmr_cur_retail_avg numeric,
    mmr_cur_retail_clean numeric,
    primeunit text,
    aucguart text,
    byrno int,
    vnzip1 text,
    vnst text,
    vehbcost numeric,
    isonlinesale smallint,
    warrantycost numeric
);

\copy raw_purchases FROM '/project/data/training.csv' WITH (FORMAT csv, HEADER true, NULL 'NULL')

-- Typed, cleaned view that every analysis query reads from.
CREATE OR REPLACE VIEW purchases AS
SELECT
    refid,
    isbadbuy,
    to_date(purchdate, 'MM/DD/YYYY')                     AS purch_date,
    auction,
    vehicleage                                            AS vehicle_age,
    make,
    model,
    upper(transmission)                                   AS transmission,  -- raw has 'Manual' and 'MANUAL'
    coalesce(wheeltype, 'Missing')                        AS wheel_type,
    vehodo                                                AS odometer,
    CASE WHEN vehodo < 50000 THEN '1: <50K'
         WHEN vehodo < 70000 THEN '2: 50-70K'
         WHEN vehodo < 85000 THEN '3: 70-85K'
         ELSE '4: 85K+' END                               AS mileage_band,
    size,
    nullif(mmr_acq_auction_avg, 0)                        AS mmr_auction_avg,  -- 0 = no price
    nullif(mmr_acq_retail_avg, 0)                         AS mmr_retail_avg,
    vehbcost                                              AS price_paid,
    vehbcost / nullif(mmr_acq_auction_avg, 0)             AS price_to_mmr,
    byrno                                                 AS buyer_id,
    vnst                                                  AS state,
    isonlinesale = 1                                      AS is_online,
    warrantycost                                          AS warranty_cost
FROM raw_purchases;

SELECT count(*) AS rows_loaded, round(avg(isbadbuy), 4) AS bad_buy_rate FROM purchases;

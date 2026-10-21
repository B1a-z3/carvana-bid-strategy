# Auction Bid Strategy: Which Used Cars Go Bad, and What Should We Bid?

**Live app:** https://carvana-bid-strategy-cp2bch6sjsclzdxmtt8fz8.streamlit.app/ · **Tableau Public:** https://public.tableau.com/app/profile/nihal.lokesh/viz/Carvana-auction-bid-strategy/Whereistherisk

Carvana buys thousands of cars at auction. In the 72,983 purchases in Carvana's Kaggle dataset ([Don't Get Kicked!](https://www.kaggle.com/c/DontGetKicked)), about **1 in 8 (12.3%)** turned out to be a "bad buy" (a *kick*). This project finds what drives bad buys and tests a risk-adjusted bid policy against Carvana's real purchases.

## Key results

| Metric | Result |
|---|---|
| Back-tested saving (Aug–Dec 2010) | **+$4.42M (+27% profit)** |
| Bad-buy rate | **12.8% → 8.0%** |
| Trade-off | **28% fewer cars bought** |
| Risk model (XGBoost) | AUC 0.767; logistic regression reaches 0.750 |

- **Biggest risk driver:** cars with no `WheelType` recorded go bad 70.5% of the time, against 12.3% for the fleet.
- **Age and mileage compound:** 1-year-old cars go bad about 4% of the time. 9-year-old cars with 85K+ miles go bad about 34% of the time.
- **ADESA** runs about 3–4 points above Manheim, even for cars of the same age.
- **Confounding check:** paying above market looks risky overall, but the effect disappears once you control for vehicle age.

## What's in the project

| Part | Where | What it does |
|---|---|---|
| 1. Warehouse SQL | `sql/` (Postgres 16) | Loads the data, then uses CTEs and window functions to break down kick rates by make, age × mileage, auction trend, riskiest model per make, overpayment and buyer. Output: `reports/sql_results.txt` |
| 2. Risk drivers | `drivers.py`, [docs/drivers.md](docs/drivers.md) | Logistic regression odds ratios next to XGBoost SHAP values, with the reason behind each driver. |
| 3. Bid policy | `bid_strategy.py` | Builds the model, sets a maximum bid per car and runs an out-of-time back-test. |
| 4. Experiment design | `ab_test.py`, [docs/ab_test_plan.md](docs/ab_test_plan.md) | A buyer-week randomized A/B test plan, with power calculation and simulation. |
| 5. Dashboards | `tableau/`, `app.py` | A Tableau workbook ([build guide](tableau/BUILD.md)) and a Streamlit version of the same two pages. |

## How the bid policy works

1. **Score each car's probability of being a bad buy** (`p_kick`). XGBoost does this using only information available before bidding. Three groups of columns are left out on purpose:
   - `VehBCost`, the price paid, because that's the bid being decided.
   - `MMRCurrent*`, because those prices are dated after the purchase.
   - `BYRNO`, the ID of the buyer who won the car.
2. **Turn the probability into a maximum bid:** expected resale value minus the risk-adjusted expected loss.
   `max_bid = (V − OH) − p · (V − R·A + K)`
3. **Pass** on any car whose auction price is above the maximum bid.
4. **Back-test** with a time-based split: train on the first 60% of purchases, tune on the next 20%, and test on the last 20% (Aug–Dec 2010, 14,470 cars). Then compare profit with what Carvana actually bought.

| Strategy | Cars bought | Kick rate | Profit | Per car |
|---|---|---|---|---|
| Historical (bought everything) | 14,470 | 12.8% | $16.5M | $1,143 |
| Flat-risk bid (price discipline, no model) | 11,214 | 11.6% | $19.6M | $1,751 |
| **XGBoost risk bid** | **10,375** | **8.0%** | **$21.0M** | **$2,020** |

The policy passes on 4,095 cars:

| Cars passed | Count | Effect on profit |
|---|---|---|
| Kicks | 1,028 | +$4.50M of losses avoided |
| Good cars that were overpriced | 1,362 | +$0.81M of losses avoided |
| Profitable good cars | 1,705 | −$0.89M of profit given up |

The saving stays positive under every cost scenario tested, ranging from $2.6M to $6.6M (see `reports/metrics.txt`).

### Cost assumptions (`ECON` in `bid_strategy.py`)

| Symbol | Meaning | Default |
|---|---|---|
| V | Sale value of a good car | MMR acquisition retail average |
| R·A | A kicked car is dumped at R × MMR auction average | R = 0.70 |
| OH | Recon, transport and selling cost per car | $1,000 |
| K | Extra cost of handling a kick | $500 |

## Repo structure

```
├── app.py                  # Streamlit app (both dashboards)
├── requirements.txt        # app dependencies (used by Streamlit Cloud)
├── .streamlit/config.toml  # app theme
├── bid_strategy.py         # risk model, max-bid rule, back-test → reports/
├── drivers.py              # logistic regression + XGBoost SHAP drivers
├── ab_test.py              # A/B power calculation and simulation
├── sql/                    # Postgres load, analysis queries, Tableau exports
├── docs/                   # drivers write-up, A/B test plan
├── tableau/                # dashboard.twb, build guide, CSVs feeding the dashboards
└── reports/                # model metrics, charts, per-car back-test
```

## Run it

**The app only.** It uses the committed CSVs, so no Kaggle data is needed:

```bash
git clone https://github.com/B1a-z3/carvana-bid-strategy.git
cd carvana-bid-strategy
pip install -r requirements.txt
streamlit run app.py
```

**The full pipeline.** First download `training.csv` and `test.csv` from [Kaggle](https://www.kaggle.com/c/DontGetKicked/data) into `data/`. Then run:

```bash
pip install scikit-learn xgboost statsmodels matplotlib
docker run -d --name kicked-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=kicked -v "$PWD:/project" postgres:16
docker exec kicked-pg psql -U postgres -d kicked -f /project/sql/01_load.sql
docker exec kicked-pg psql -U postgres -d kicked -f /project/sql/02_analysis.sql
docker exec kicked-pg psql -U postgres -d kicked -f /project/sql/03_tableau_exports.sql
python bid_strategy.py
python drivers.py
python ab_test.py
```

- In Git Bash on Windows, set `MSYS_NO_PATHCONV=1` first so the `/project/...` paths aren't rewritten.
- `ab_test.py` takes about 7 minutes, because it runs 6,400 simulated regressions.

## Caveats

- **The dollar figures depend on the cost assumptions above.** The data has no resale prices or kick losses, so treat them as a back-test, not a forecast.
- **We only see cars Carvana won.** The back-test can measure the value of passing on cars Carvana bought, but not of cars a higher bid would have won. Real-world lift will be smaller, and the A/B plan is sized for that.
- **Check when `WheelType` is recorded.** If it's filled in or blanked after a kick, it leaks the label (see [docs/drivers.md](docs/drivers.md)).
- **The win rule is simplified.** It ignores competing bidders.
- **Cars with no market price get no bid.** This affects about 1% of cars.

## Tools

Python (pandas, scikit-learn, XGBoost, statsmodels) · PostgreSQL · Tableau · Streamlit · Plotly

## Data note

The raw Kaggle data is not included, because the competition rules don't allow redistributing it. Only the derived outputs the dashboards use are committed.

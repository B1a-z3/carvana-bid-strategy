# A/B test plan: risk-adjusted bid ceilings

The numbers on this page come from `python ab_test.py`, which writes `reports/ab_test.txt`. They're based on the Aug to Dec 2010 back-test window: 63 buyers and about 35 active buyer-weeks per week.

## 1. Hypothesis

- **H1:** Capping each bid at the model's risk-adjusted maximum (`max_bid` = expected resale − P(kick) × loss if kicked − costs) increases **total profit per buyer-week** compared with current buying practice.
- **H0:** There is no difference.

The back-test predicts +$6,249 per buyer-week (+27%). The real lift will be smaller, because the back-test only credits the cars we pass on. The test is sized assuming the real lift may be half the back-test lift.

## 2. Randomization unit: the buyer-week

| Option | Why not, or why |
|---|---|
| Car (lot) | Rejected. One buyer can't apply two bidding rules within the same auction session, so the arms would contaminate each other. |
| Buyer | Rejected. There are only about 63 buyers, and volume is very uneven (the top buyer does 5% of all purchases). That gives too few clusters and too much imbalance. |
| Auction location | Rejected. There are too few locations, and they differ a lot. |
| **Buyer-week (chosen)** | Each buyer is randomly assigned to the new policy in half of their weeks, stratified within buyer. Every buyer serves as their own control, which removes differences in buyer skill. Week fixed effects absorb market-wide swings. |

Risks of this design and how to handle them:
- **Carry-over.** A buyer who learns from the model may bid differently in control weeks too. Measure the gap between control weeks and the pre-period. If carry-over is suspected, switch to a staggered rollout where each buyer moves to the new policy for good and never goes back.
- **Shared auctions.** Treatment buyers bidding less could hand cheaper cars to Carvana's own control buyers at the same sale. Log same-sale overlaps and run a sensitivity check that excludes them.

## 3. Metrics

| Type | Metric | Why |
|---|---|---|
| **Primary** | Profit per buyer-week = Σ (resale − price − recon − kick loss) | The business outcome. It's not *per car*, because buying fewer cars mechanically raises per-car profit. |
| Secondary | Kick rate; profit per car; average price paid vs. MMR | Explain *how* the profit moved. |
| **Guardrail** | Cars bought per buyer-week. Stop if it falls more than 35% (back-test predicts −28%). | Carvana needs inventory. A policy that saves money by starving the lots is a loss. |
| **Guardrail** | Days-to-sale and gross margin on retail sales | Catches whether the cars we skip were replaced by cars that are slower or cheaper to sell. |
| **Guardrail** | Win rate on cars bid on, and buyer override rate | Checks that the model ceiling is actually followed and isn't failing to compete. |
| Leading indicator | Kick rate at 30 days | Profit isn't known until the car is resold, about 60 to 90 days later. Kicks show up within weeks. |

## 4. Sample size and power

Settings: two-sided, α = 0.05, power 80%. The within-buyer SD of profit per buyer-week is $25,676.

| True lift | Minimum detectable effect per buyer-week | Buyer-weeks per arm (analytic) | Weeks at ~35 per week |
|---|---|---|---|
| 100% of back-test | $6,249 | 265 | 15 |
| 50% of back-test | $3,125 | 1,060 | 60 |
| 25% of back-test | $1,562 | 4,240 | 240 |

The simulation uses the real 20-week window. It runs 400 random assignments per cell and fits OLS with buyer and week fixed effects, with standard errors clustered by buyer.

| True lift \ weeks run | 2 | 4 | 8 | 20 |
|---|---|---|---|---|
| 0% (A/A false-positive rate) | 0.01 | 0.01 | 0.03 | 0.06 |
| 25% | 0.01 | 0.03 | 0.04 | 0.12 |
| 50% | 0.00 | 0.07 | 0.12 | 0.37 |
| 100% | 0.03 | 0.22 | 0.45 | **0.82** |

What this means:

- **Total profit is a noisy metric.** Week-to-week swings in how many cars a buyer buys swamp the effect. Even a full back-test-sized lift needs about 20 weeks to detect.
- **Plan for 20 weeks.** Before launch, pre-register a variance-reduced primary metric: **profit per car evaluated**, where the denominator is the lots a buyer bid on, which can be recorded in both arms. This removes the volume noise. It can't be simulated here, because the Kaggle data only contains cars that were won.
- **Use CUPED** (adjust for each buyer's pre-period profit). It typically adds another 20 to 40% of effective sample size.
- **Kick rate is the early read.** Detecting 12.8% → 8.0% needs only about 630 cars per arm, roughly 2 weeks of volume, before inflating for clustering. If kick rate hasn't moved by week 4, the mechanism isn't working, so stop and debug rather than wait for profit.
- **A/A check:** the false-positive rate stays between 0.01 and 0.06, close to the nominal α of 0.05. That confirms the clustered analysis isn't overstating significance with this few buyers.

## 5. Analysis and decision rules

1. **Model:** `profit ~ treatment + buyer FE + week FE`, with standard errors clustered by buyer. Report the lift with a 95% CI in dollars per buyer-week, and also annualized.
2. **Before reading the result, check:**
   - Sample-ratio mismatch (each buyer should be close to 50/50).
   - Compliance: what share of treatment-week bids stayed under `max_bid`.
   - The guardrails.
3. **Decision:**

| Result | Action |
|---|---|
| Primary significant and positive, guardrails OK | Roll out. |
| Primary positive but not significant, kick rate clearly down, volume guardrail OK | Extend the test, or roll out with ongoing monitoring. The direction is right and the cost of being wrong is small. |
| Volume guardrail breached | Don't roll out as-is. Re-tune the margin, since a bid ceiling above break-even trades some kick risk for volume, then re-test. |
| Kick rate unchanged | The model isn't working out of sample. Investigate drift and the wheel-type leakage question in `drivers.md` before anything else. |

4. **Segments:** check the effect by auction house and by vehicle age. These are pre-registered as secondary, so they aren't fishing.

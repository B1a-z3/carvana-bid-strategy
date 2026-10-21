# Tableau dashboard: build guide

This is a two-page dashboard for a non-technical audience such as a purchasing manager or a finance partner. Every chart answers one question, and the question is the chart title. You can build it in Tableau Public (free) in about an hour.

## Data sources (all CSV, connect with Text File)

| File | Made by | Grain |
|---|---|---|
| `tableau/segment_risk.csv` | `sql/03_tableau_exports.sql` | One row per segment value (dimension, segment, cars, kick_rate, lift_vs_fleet) |
| `tableau/age_mileage_grid.csv` | `sql/03_tableau_exports.sql` | Vehicle age × mileage band |
| `tableau/auction_monthly.csv` | `sql/03_tableau_exports.sql` | Auction house × month |
| `reports/policy_backtest.csv` | `bid_strategy.py` | One row per car in the Aug to Dec 2010 back-test |

Each file is its own data source. No joins are needed.

## Calculated fields (on `policy_backtest`)

```
Decision            = IF [Keep] THEN "Buy" ELSE "Pass" END
Outcome             = IF [Is Bad Buy] = 1 THEN "Kicked" ELSE "Good" END
Historical Profit   = [Profit If Bought]
Policy Profit       = IF [Keep] THEN [Profit If Bought] ELSE 0 END
Saving              = SUM([Policy Profit]) - SUM([Historical Profit])
Kicks Avoided       = SUM(IF NOT [Keep] AND [Is Bad Buy] = 1 THEN 1 ELSE 0 END)
Paid Over Max Bid   = [Veh B Cost] - [Max Bid]
Pass Reason         = IF [Keep] THEN "Bought"
                      ELSEIF [Is Bad Buy] = 1 THEN "Passed: kick avoided"
                      ELSEIF [Profit If Bought] < 0 THEN "Passed: good car, but overpriced"
                      ELSE "Passed: profitable car given up" END
```

Parameter for page 1: **Break down by**, a string list with the values Make, Vehicle age, Mileage band, Auction house, Size and Wheel type. Add the filter `[Dimension] = [Break down by]` to the `segment_risk` sheet, and show the parameter control.

## Page 1: "Where is the risk?"

| # | Sheet | Build | Notes for the audience |
|---|---|---|---|
| 1 | KPI tiles | 72,983 cars bought · 12.3% turned out bad · 1 in 8 | Big numbers only. Tableau has no tile object, so use text sheets. |
| 2 | "Which segments go bad most often?" | Horizontal bar: segment on rows, kick_rate on columns, sorted descending, with the parameter control on top. Use one color, and add a reference line at the 12.3% fleet average. | The tooltip says "X% of these cars were bad buys, Y× the average". |
| 3 | "Older + higher-mileage = riskier" | Heatmap from `age_mileage_grid`: age on columns, mileage band on rows, color = kick_rate on a single-hue sequential scale, label = kick_rate. Filter cars ≥ 50. | This is the clearest single picture for buyers. |
| 4 | "Is any auction getting worse?" | Line: month on columns, kick_rate on rows, color = auction (3 colors). Add a 3-month moving average as a table calculation. | Highlights ADESA running above the others. |

## Page 2: "What would the new bid policy have done?"

| # | Sheet | Build | Notes for the audience |
|---|---|---|---|
| 5 | KPI tiles | Saving **+$4.4M (+27%)** · Kick rate **12.8% → 8.0%** · Cars bought **−28%** | Show the volume drop next to the saving. Hiding the trade-off loses trust. |
| 6 | "Where does the $4.4M come from?" | Bar on `Pass Reason`, value = −SUM([Historical Profit]), colored green or red by sign. | Avoided $4.50M of kick losses (1,028 cars) + avoided $0.81M on overpriced good cars (1,362) − gave up $0.89M on profitable cars (1,705) = **+$4.42M**. |
| 7 | "Price paid vs. what we'd bid" | Scatter: Max Bid on X, VehBCost on Y, color = Pass Reason, with a diagonal reference line (y = x). | Dots above the line are cars we paid more for than they were worth to us. |
| 8 | "Savings build up every week" | Line: WEEK(PurchDate) on columns, RUNNING_SUM of [Saving] on rows. | Shows the gain is steady, not one lucky week. |
| 9 | "Saving by auction house" | Bar: Auction on rows, [Saving] on columns, with [Kicks Avoided] in the tooltip. | Tells the business where to roll out first. |

## Design rules for this audience

- Write every title as a plain-English question, with no column names or jargon. Say "bad buy", not "IsBadBuy".
- Format percentages to 1 decimal place and dollars in $K or $M.
- Use one accent color for "risk" and one for "saving". Red and green only on the waterfall, and with labels so it doesn't rely on color alone.
- Add a footnote on page 2: *"Dollar figures use assumed recon and kick-loss costs (see README). They are a back-test on cars Carvana actually bought, not a forecast."*
- Publish to Tableau Public, then share the link and a PDF export.

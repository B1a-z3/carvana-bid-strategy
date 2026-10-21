# What drives a bad buy, and why

This page summarizes the output of `python drivers.py`; full numbers are in `reports/drivers.txt` and `reports/drivers.png`. The models are trained on Jan 2009 to Mar 2010 and scored on Aug to Dec 2010.

| Model | Purpose | Test AUC |
|---|---|---|
| Logistic regression (17 readable features) | Explaining the drivers | 0.750 |
| XGBoost (all 26 pre-bid features) | Setting bids | 0.766 |

The simple model reaches about 98% of XGBoost's ranking power. So the risk is mostly carried by a few clear drivers, not by obscure interactions. That's good news, because a buyer on the auction floor can actually act on it.

## The drivers

Odds ratios come from the logistic regression. Holding everything else fixed, 1.29 per year means each extra year multiplies the odds of a kick by 1.29. The SQL references point to `sql/02_analysis.sql`.

**1. Missing wheel type: odds × 18.8. This is the biggest driver by far.**
- Cars with no wheel type recorded kick 70% of the time, against 10% otherwise. At ADESA the figure is 90% (SQL Q6).
- **Why it matters:** wheel type is filled in during the auction's condition write-up. When it's blank, the car usually got a rushed or partial inspection, and the problems a full inspection would have priced in come out after purchase.
- **Caveat to resolve before production:** confirm with Carvana's data team *when* this field is filled in. If it gets blanked or edited after a car is kicked, it leaks the label. If so, the model and the back-test are both overstated.

**2. Vehicle age: odds × 1.29 per year.**
- Kick rates climb from about 4% at 1 year old to about 30% at 8 to 9 years (SQL Q2).
- **Why it matters:** older cars have more wear components near the end of their life (transmission, suspension, electronics). The auction price only partly reflects this, because the price guides assume "average condition", and average condition worsens unevenly with age.

**3. Odometer: odds × 1.13 per 10K miles, on top of age.**
- The age × mileage grid shows the two compounding. A 7-year-old car has an 8.5% kick rate under 50K miles but 24% above 85K.
- **Why it matters:** mileage measures *use*, and age measures *time*. Cars that are both old and high-mileage are where the expensive failures cluster.

**4. Make and model: Nissan, Kia, Chrysler and Ford have 1.2 to 1.3× the odds of Chevrolet.**
- At the model level the spread is much wider (SQL Q4). The Ford Windstar kicks 39% of the time and the Dodge Neon 23%, against make averages of 16% and 11%.
- **Why it matters:** these models have known failure patterns (transmissions, head gaskets) that a general price guide doesn't fully discount. Buyers should treat them as "inspect or pass" lists rather than relying on the make.

**5. Market price level: odds × 0.97 per $1K of auction price (MMR).**
- Within the same age and mileage, cheaper cars kick more. In XGBoost, a wider gap between retail and auction price also lowers risk.
- **Why it matters:** a low price guide for a car's age means the market already sees it as less desirable. A big retail premium means retail demand is strong, so marginal issues get absorbed rather than becoming kicks.

**6. Auction house: ADESA has 1.13× the odds of Manheim.**
- This partly reflects ADESA's higher rate of missing wheel types, and partly differences in arbitration and guarantee policy.
- **Why it matters:** the channel itself carries risk, and how much varies over time (SQL Q3 shows rolling 3-month rates). That makes it a good thing to monitor.

**7. Not significant once the factors above are controlled for:** warranty cost, manual transmission and online sale.
- Warranty cost looks like it should matter, but it's priced almost entirely from age, mileage and make, all of which are already in the model.

## Price paid: a driver we deliberately leave out

Kick rates rise with what Carvana paid relative to market price. The top fifth by price-to-MMR ratio kicks 17.6% of the time, against 8.6% for the second fifth (SQL Q5).

That looks like a "winner's curse", but it's confounded by age. Older cars sell further above their market price: the average price-to-MMR ratio is 0.93 at 1–2 years and 1.68 at 8 years. Older cars also kick more. Compare cars of the same age and the pattern disappears or even reverses: at 6 years old, cars bought furthest below market kick 33% of the time, against 16% for those bought furthest above.

Price paid is kept out of the risk model anyway, because it's the decision being made. Using it would make the bid depend on itself.

## Reading the XGBoost ranking

The XGBoost ranking agrees with the logistic regression on the top drivers: wheel type, age, odometer, then price and vehicle identity.

State (`VNST`) ranks fourth in XGBoost. It likely stands in for regional auction practices and climate (rust, heat). It has many levels, so treat that ranking as a lead to investigate, not a finding.

Correlated inputs share credit in SHAP. For example, `VehYear` and `VehicleAge` are near duplicates, and so are the clean and average price guides. So look at related inputs as a group rather than reading each one's rank on its own.

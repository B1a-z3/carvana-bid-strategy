"""Power calculation and simulated A/B test for the bid policy (plan: docs/ab_test_plan.md).

Design: randomize buyer-weeks (each buyer flips between policies week to week, stratified
within buyer). Primary metric: profit per buyer-week. Data: the out-of-time back-test cars
written by bid_strategy.py, so control = what Carvana bought, treatment = policy-kept cars.

Run:  python ab_test.py   (after bid_strategy.py)
Out:  reports/ab_test.txt
"""
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats import norm

from bid_strategy import OUT

ALPHA, POWER, SIMS = 0.05, 0.80, 400
rng = np.random.default_rng(0)


def buyer_weeks(cars):
    c = cars.assign(week=pd.to_datetime(cars.PurchDate).dt.to_period("W").astype(str),
                    kept_profit=cars.profit_if_bought * cars.keep,
                    kept_kicks=cars.IsBadBuy * cars.keep)
    return c.groupby(["BYRNO", "week"]).agg(
        ctrl_profit=("profit_if_bought", "sum"), trt_profit=("kept_profit", "sum"),
        ctrl_cars=("RefId", "size"), trt_cars=("keep", "sum"),
        ctrl_kicks=("IsBadBuy", "sum"), trt_kicks=("kept_kicks", "sum")).reset_index()


def simulate(bw, effect_share, weeks):
    """Share of p-values < ALPHA when the true lift is `effect_share` x the back-test lift."""
    bw = bw[bw.week.isin(sorted(bw.week.unique())[:weeks])]
    lift = bw.trt_profit - bw.ctrl_profit
    hits = 0
    for _ in range(SIMS):
        # Within each buyer, a random half of their weeks get the new policy.
        t = bw.groupby("BYRNO").week.transform(lambda w: rng.permutation(len(w)) < len(w) / 2)
        y = bw.ctrl_profit + t * effect_share * lift
        fit = smf.ols("y ~ t + C(BYRNO) + C(week)", data=bw.assign(y=y, t=t.astype(int))).fit(
            cov_type="cluster", cov_kwds={"groups": bw.BYRNO})
        hits += fit.pvalues["t"] < ALPHA
    return hits / SIMS


def main():
    bw = buyer_weeks(pd.read_csv(OUT / "policy_backtest.csv"))
    n_weeks, n_buyers = bw.week.nunique(), bw.BYRNO.nunique()
    lift = bw.trt_profit - bw.ctrl_profit

    # Analytic sample size on the primary metric. Within-buyer design, so use the
    # SD of buyer-week profit after removing each buyer's own average.
    resid_sd = (bw.ctrl_profit - bw.groupby("BYRNO").ctrl_profit.transform("mean")).std()
    z = norm.ppf(1 - ALPHA / 2) + norm.ppf(POWER)
    rows = []
    for share in [1.0, 0.5, 0.25]:
        mde = share * lift.mean()
        n_arm = int(np.ceil(2 * (z * resid_sd / mde) ** 2))
        rows.append(dict(true_lift=f"{share:.0%} of back-test", mde_per_buyer_week=mde,
                         buyer_weeks_per_arm=n_arm, weeks_needed=np.ceil(2 * n_arm / (len(bw) / n_weeks))))
    sizing = pd.DataFrame(rows).set_index("true_lift")

    sim = pd.DataFrame({w: {f"{s:.0%}": simulate(bw, s, w) for s in [0, 0.25, 0.5, 1.0]}
                        for w in [2, 4, 8, n_weeks]})
    sim.index.name, sim.columns.name = "true lift (share of back-test)", "weeks run"
    assert sim.loc["0%"].max() <= 0.12, "A/A false-positive rate far above alpha"

    g = bw[["ctrl_cars", "trt_cars", "ctrl_kicks", "trt_kicks"]].sum()
    report = "\n".join([
        f"Back-test window: {n_buyers} buyers, {n_weeks} weeks, {len(bw)} active buyer-weeks "
        f"(~{len(bw) / n_weeks:.0f} per week)",
        f"Primary metric, profit per buyer-week: control ${bw.ctrl_profit.mean():,.0f}, "
        f"policy ${bw.trt_profit.mean():,.0f} (lift ${lift.mean():,.0f}); within-buyer SD ${resid_sd:,.0f}",
        f"Guardrails if fully rolled out: cars bought {g.trt_cars / g.ctrl_cars - 1:+.1%}, "
        f"kick rate {g.ctrl_kicks / g.ctrl_cars:.1%} -> {g.trt_kicks / g.trt_cars:.1%}",
        "", f"Analytic sample size (alpha {ALPHA}, power {POWER:.0%}, two-sided):",
        sizing.to_string(float_format="{:,.0f}".format),
        "", f"Simulated power ({SIMS} random assignments each; OLS with buyer + week fixed effects, "
        "SEs clustered by buyer). The 0% row is the A/A false-positive rate:",
        sim.to_string(float_format="{:.2f}".format),
    ])
    (OUT / "ab_test.txt").write_text(report)
    print(report)


if __name__ == "__main__":
    main()

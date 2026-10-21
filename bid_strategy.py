"""Auction bid strategy on Carvana's "Don't Get Kicked!" data.

1. Model P(kick) from what is known *before* bidding.
2. Turn P(kick) into a break-even max bid with a simple unit-economics model.
3. Back-test on the latest 20% of purchases (out of time): we keep a car only if
   our max bid >= the price Carvana actually paid, and book realized profit.

Run:  python bid_strategy.py      (expects data/training.csv and data/test.csv)
Out:  reports/metrics.txt, reports/*.png, reports/bid_sheet.csv, reports/policy_backtest.csv
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OrdinalEncoder
from xgboost import XGBClassifier

# --- Unit economics (assumptions, not in the data; edit to match real costs) ---
GOOD_VALUE = "MMRAcquisitionRetailAveragePrice"   # what a good car sells for
ECON = dict(
    overhead=1000,     # $ recon + transport + selling cost per car, good or bad
    recovery=0.70,     # a kicked car is dumped at 70% of MMR auction average
    kick_extra=500,    # $ extra handling/arbitration cost for a kick
)

CAT = ["Auction", "Make", "Model", "Trim", "SubModel", "Color", "Transmission",
       "WheelType", "Nationality", "Size", "TopThreeAmericanName",
       "PRIMEUNIT", "AUCGUART", "VNST"]
NUM = ["VehicleAge", "VehYear", "VehOdo", "IsOnlineSale", "WarrantyCost",
       "MMRAcquisitionAuctionAveragePrice", "MMRAcquisitionAuctionCleanPrice",
       "MMRAcquisitionRetailAveragePrice", "MMRAcquisitonRetailCleanPrice",
       "odo_per_year", "clean_premium", "retail_spread"]
# Deliberately excluded: VehBCost (that's our bid, the decision variable),
# MMRCurrent* (priced "as of current day" = after purchase, leaks the future),
# BYRNO (which Carvana buyer won it), RefId, PurchDate.

OUT = Path("reports")


def load(path):
    d = pd.read_csv(path, na_values=["NULL"])
    d["PurchDate"] = pd.to_datetime(d.PurchDate)
    mmr = [c for c in d if c.startswith("MMR")]
    d[mmr] = d[mmr].replace(0, np.nan)   # 0 means "no price", not a free car
    d["odo_per_year"] = d.VehOdo / (d.VehicleAge + 1)
    d["clean_premium"] = d.MMRAcquisitionAuctionCleanPrice - d.MMRAcquisitionAuctionAveragePrice
    d["retail_spread"] = d.MMRAcquisitionRetailAveragePrice - d.MMRAcquisitionAuctionAveragePrice
    return d


def make_model():
    enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan,
                         encoded_missing_value=np.nan, max_categories=250)
    pre = ColumnTransformer([("cat", enc, CAT)], remainder="passthrough")
    clf = XGBClassifier(
        # shallow + heavy min_child_weight: picked on the tune window for calibration (bid uses p directly)
        n_estimators=500, learning_rate=0.03, max_depth=3, min_child_weight=20,
        subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0, random_state=0,
        enable_categorical=True, feature_types=["c"] * len(CAT) + ["q"] * len(NUM))
    return make_pipeline(pre, clf)


def max_bid(p, d, e=ECON):
    """Expected resale minus risk-adjusted loss = price where expected profit is 0.
    Good car nets V - OH; a kick nets R*A - OH - K, i.e. loses (V - R*A + K) vs good.
    b = (V - OH) - p * (V - R*A + K)"""
    v, a = d[GOOD_VALUE], d.MMRAcquisitionAuctionAveragePrice
    return (v - e["overhead"]) - p * (v - e["recovery"] * a + e["kick_extra"])


def profit(d, price, e=ECON):
    """Realized profit of owning each car at `price`, using the actual kick label."""
    good = d[GOOD_VALUE] - price - e["overhead"]
    bad = e["recovery"] * d.MMRAcquisitionAuctionAveragePrice - price - e["overhead"] - e["kick_extra"]
    return np.where(d.IsBadBuy == 1, bad, good)


def backtest(d, p, margin, e=ECON):
    """Keep a car iff (max bid - margin) >= what was actually paid; pay that price."""
    keep = (max_bid(p, d, e) - margin) >= d.VehBCost
    pr = profit(d, d.VehBCost, e)
    return dict(cars=int(keep.sum()), kick_rate=d.IsBadBuy[keep].mean(),
                profit=pr[keep].sum(), per_car=pr[keep].mean() if keep.any() else 0.0)


def split(df):
    """Out-of-time windows: first 60% train, next 20% tune, last 20% test."""
    df, n = df.sort_values("PurchDate", kind="stable"), len(df)
    return df[: int(.6 * n)], df[int(.6 * n): int(.8 * n)], df[int(.8 * n):]


def main():
    OUT.mkdir(exist_ok=True)
    df = load("data/training.csv")
    train, tune, test = split(df)

    model = make_model().fit(train[CAT + NUM], train.IsBadBuy)
    p_tune = model.predict_proba(tune[CAT + NUM])[:, 1]
    p_test = model.predict_proba(test[CAT + NUM])[:, 1]

    # Economics need a market price; the few cars with no MMR get no bid.
    tune, p_tune = tune[tune[GOOD_VALUE].notna().values], p_tune[tune[GOOD_VALUE].notna().values]
    priced = test[GOOD_VALUE].notna().values
    test, p_test = test[priced], p_test[priced]

    # Self-check: at the break-even bid, expected profit is ~0.
    b = max_bid(p_test, test)
    ev = (1 - p_test) * profit(test.assign(IsBadBuy=0), b) + p_test * profit(test.assign(IsBadBuy=1), b)
    assert np.allclose(ev, 0, atol=0.01), "max_bid formula is not break-even"  # cents; XGB p is float32

    # Pick the required margin on the tune window, report on the untouched test window.
    margins = np.arange(0, 2001, 100)   # never bid above break-even
    tune_curve = [backtest(tune, p_tune, m)["profit"] for m in margins]
    best_m = margins[int(np.argmax(tune_curve))]

    base = train.IsBadBuy.mean()
    rows = {
        "Historical (bought all)": backtest(test, np.zeros(len(test)), -1e9),
        "Flat-risk bid (no model)": backtest(test, np.full(len(test), base), best_m),
        f"Model bid, margin ${best_m}": backtest(test, p_test, best_m),
    }
    table = pd.DataFrame(rows).T
    hist, pol = table.iloc[0], table.iloc[-1]

    # How much of the saving survives if the cost assumptions are wrong (one at a time).
    sens = []
    for k, v in [("default", None), ("recovery", 0.5), ("recovery", 0.85), ("kick_extra", 0),
                 ("kick_extra", 1500), ("overhead", 500), ("overhead", 1500)]:
        e = {**ECON, k: v} if v is not None else ECON
        h, m = backtest(test, p_test * 0, -1e9, e), backtest(test, p_test, best_m, e)
        sens.append(dict(scenario=k if v is None else f"{k}={v}", saving=m["profit"] - h["profit"],
                         hist_per_car=h["per_car"], policy_per_car=m["per_car"]))
    sens = pd.DataFrame(sens).set_index("scenario")
    auc = roc_auc_score(test.IsBadBuy, p_test)
    calib = (pd.DataFrame({"p": p_test, "y": test.IsBadBuy.values})
             .assign(decile=lambda x: pd.qcut(x.p, 10, labels=False, duplicates="drop"))
             .groupby("decile").agg(predicted=("p", "mean"), actual=("y", "mean"), n=("y", "size")))

    report = "\n".join([
        f"Windows: train {train.PurchDate.min():%Y-%m-%d}..{train.PurchDate.max():%Y-%m-%d} ({len(train)}), "
        f"tune ..{tune.PurchDate.max():%Y-%m-%d} ({len(tune)}), "
        f"test {test.PurchDate.min():%Y-%m-%d}..{test.PurchDate.max():%Y-%m-%d} ({len(test)} priced cars)",
        f"Test AUC {auc:.3f}  Gini {2 * auc - 1:.3f}  Brier {brier_score_loss(test.IsBadBuy, p_test):.4f} "
        f"(base-rate Brier {brier_score_loss(test.IsBadBuy, np.full(len(test), base)):.4f})",
        f"Margin chosen on tune window: ${best_m}",
        "", "Back-test on test window (realized profit under the stated assumptions):",
        table.to_string(float_format=lambda x: f"{x:,.3f}" if abs(x) < 1 else f"{x:,.0f}"),
        "", f"SAVING vs historical purchases: ${pol.profit - hist.profit:,.0f} "
        f"({pol.profit / hist.profit - 1:+.1%}) while buying {pol.cars / hist.cars:.0%} of the cars; "
        f"kicks avoided: {hist.cars * hist.kick_rate - pol.cars * pol.kick_rate:,.0f}",
        "", "Sensitivity of the saving to each cost assumption (others at default):",
        sens.to_string(float_format="{:,.0f}".format),
        "", "Calibration by predicted-risk decile:", calib.to_string(float_format="{:.3f}".format),
    ])
    (OUT / "metrics.txt").write_text(report)
    print(report)

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    ax[0].plot(margins, np.array(tune_curve) / 1e3, label="tune")
    ax[0].plot(margins, [backtest(test, p_test, m)["profit"] / 1e3 for m in margins], label="test")
    ax[0].axvline(best_m, ls="--", c="grey")
    ax[0].set(xlabel="Required margin below break-even bid ($)", ylabel="Total profit ($K)",
              title="Profit vs. bid margin")
    ax[0].legend()
    ax[1].plot(calib.predicted, calib.actual, "o-")
    ax[1].plot([0, 1], [0, 1], ls=":", c="grey")
    ax[1].set(xlabel="Predicted kick rate", ylabel="Actual kick rate", title="Calibration (test)")
    fig.tight_layout()
    fig.savefig(OUT / "strategy.png", dpi=120)

    # Per-car back-test for the dashboard and the A/B simulation.
    test.assign(p_kick=p_test, max_bid=b.round(-1), keep=(b - best_m) >= test.VehBCost,
                profit_if_bought=profit(test, test.VehBCost).round())[
        ["RefId", "PurchDate", "BYRNO", "Auction", "Make", "VehicleAge", "VehOdo", "VehBCost",
         "p_kick", "max_bid", "keep", "IsBadBuy", "profit_if_bought"]
    ].to_csv(OUT / "policy_backtest.csv", index=False)

    # Bid sheet for the unlabeled Kaggle test cars, model refit on all labeled data.
    model = make_model().fit(df[CAT + NUM], df.IsBadBuy)
    new = load("data/test.csv")
    new["p_kick"] = model.predict_proba(new[CAT + NUM])[:, 1]
    new["max_bid"] = (max_bid(new.p_kick, new) - best_m).round(-1)
    new[["RefId", "Make", "Model", "VehYear", "VehOdo", "MMRAcquisitionAuctionAveragePrice",
         "p_kick", "max_bid", "VehBCost"]].to_csv(OUT / "bid_sheet.csv", index=False)


if __name__ == "__main__":
    main()

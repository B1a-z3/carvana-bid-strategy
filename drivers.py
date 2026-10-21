"""Risk drivers: interpretable logistic regression next to the XGBoost performance model.

Same out-of-time windows as bid_strategy.py. Logistic regression gives odds ratios in
business units (per year, per 10K miles, ...); XGBoost SHAP values show which inputs move
the production model's predictions and in which direction.

Run:  python drivers.py
Out:  reports/drivers.txt, reports/drivers.png
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import xgboost as xgb
from sklearn.metrics import roc_auc_score

from bid_strategy import CAT, NUM, OUT, load, make_model, split

BIG_MAKES = ["FORD", "DODGE", "CHRYSLER", "PONTIAC", "KIA", "SATURN", "NISSAN"]  # ref: CHEVROLET + rest


def design(d, mmr_median):
    """Readable logistic-regression features, each in a unit a buyer thinks in."""
    x = pd.DataFrame(index=d.index)
    x["wheel_type_missing"] = d.WheelType.isna().astype(int)
    x["age_years"] = d.VehicleAge
    x["odometer_per_10k_mi"] = d.VehOdo / 1e4
    x["mmr_auction_price_per_1k"] = d.MMRAcquisitionAuctionAveragePrice.fillna(mmr_median) / 1e3
    x["mmr_price_missing"] = d.MMRAcquisitionAuctionAveragePrice.isna().astype(int)
    x["clean_vs_avg_gap_per_1k"] = d.clean_premium.fillna(0) / 1e3
    x["warranty_cost_per_100"] = d.WarrantyCost / 100
    x["manual_transmission"] = d.Transmission.str.upper().eq("MANUAL").astype(int)
    x["online_sale"] = d.IsOnlineSale
    for a in ["ADESA", "OTHER"]:                       # ref: MANHEIM
        x[f"auction_{a}"] = d.Auction.eq(a).astype(int)
    for m in BIG_MAKES:
        x[f"make_{m}"] = d.Make.eq(m).astype(int)
    return sm.add_constant(x.astype(float))


def main():
    train, _, test = split(load("data/training.csv"))
    med = train.MMRAcquisitionAuctionAveragePrice.median()

    # --- Logistic regression ---
    xt, xs = design(train, med), design(test, med)
    lr = sm.Logit(train.IsBadBuy, xt).fit(disp=0)
    ci = np.exp(lr.conf_int())
    odds = pd.DataFrame({"odds_ratio": np.exp(lr.params), "ci_low": ci[0], "ci_high": ci[1],
                         "p_value": lr.pvalues}).drop("const")
    odds = odds.reindex(odds.odds_ratio.sub(1).abs().sort_values(ascending=False).index)
    auc_lr = roc_auc_score(test.IsBadBuy, lr.predict(xs))

    # --- XGBoost + SHAP (xgboost's built-in TreeSHAP; no extra dependency) ---
    model = make_model().fit(train[CAT + NUM], train.IsBadBuy)
    auc_xgb = roc_auc_score(test.IsBadBuy, model.predict_proba(test[CAT + NUM])[:, 1])
    xm = model[:-1].transform(test[CAT + NUM])
    names = CAT + NUM
    dm = xgb.DMatrix(xm, feature_names=names, feature_types=model[-1].feature_types,
                     enable_categorical=True)
    shap = model[-1].get_booster().predict(dm, pred_contribs=True)[:, :-1]  # drop bias column
    imp = pd.DataFrame({"mean_abs_shap": np.abs(shap).mean(0)}, index=names)
    # Direction for numeric inputs: does a higher value push risk up (+) or down (-)?
    for i, f in enumerate(names):
        if f in NUM:
            ok = ~np.isnan(xm[:, i].astype(float))
            imp.loc[f, "direction"] = np.sign(np.corrcoef(xm[ok, i].astype(float), shap[ok, i])[0, 1])
    imp = imp.sort_values("mean_abs_shap", ascending=False)

    report = "\n".join([
        f"Test-window AUC  logistic regression {auc_lr:.3f}   XGBoost {auc_xgb:.3f}",
        "", "Logistic regression odds ratios (train window; >1 = raises kick odds):",
        odds.to_string(float_format="{:.3f}".format),
        "", "XGBoost mean |SHAP| on test window (log-odds units; direction +1 = higher value -> riskier):",
        imp.head(15).to_string(float_format="{:.3f}".format),
    ])
    (OUT / "drivers.txt").write_text(report)
    print(report)

    fig, ax = plt.subplots(1, 2, figsize=(13, 5.5))
    o = odds.iloc[::-1]
    ax[0].errorbar(o.odds_ratio, range(len(o)), xerr=[o.odds_ratio - o.ci_low, o.ci_high - o.odds_ratio],
                   fmt="o", capsize=3)
    ax[0].axvline(1, ls=":", c="grey")
    ax[0].set_xscale("log")
    ax[0].set(yticks=range(len(o)), yticklabels=o.index, xlabel="Odds ratio (log scale, 95% CI)",
              title=f"Logistic regression (AUC {auc_lr:.3f})")
    top = imp.head(12).iloc[::-1]
    ax[1].barh(top.index, top.mean_abs_shap)
    ax[1].set(xlabel="Mean |SHAP| (log-odds)", title=f"XGBoost drivers (AUC {auc_xgb:.3f})")
    fig.tight_layout()
    fig.savefig(OUT / "drivers.png", dpi=120)


if __name__ == "__main__":
    main()

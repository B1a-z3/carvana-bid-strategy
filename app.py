"""
Carvana auction bid strategy — Streamlit version of the two Tableau dashboards.

Reads the same four CSVs the Tableau workbook uses:
    tableau/segment_risk.csv
    tableau/age_mileage_grid.csv
    tableau/auction_monthly.csv
    reports/policy_backtest.csv

Run locally:  streamlit run app.py
"""

import re
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
ROOT = Path(__file__).parent
FILES = {
    "segment": ROOT / "tableau" / "segment_risk.csv",
    "grid": ROOT / "tableau" / "age_mileage_grid.csv",
    "auction": ROOT / "tableau" / "auction_monthly.csv",
    "policy": ROOT / "reports" / "policy_backtest.csv",
}

# Optional: paste your Tableau Public link here to add an "Original Tableau" tab.
TABLEAU_PUBLIC_URL = ""

INK = "#1F2A36"
MUTED = "#7A8591"
RISK = "#C8553D"      # one accent for risk
SAVING = "#3A7D5C"    # one accent for savings
LOSS = "#B23A3A"
GRID = "#E6E2D9"
PASS_COLORS = {
    "Bought": "#B9C4CF",
    "Passed: kick avoided": RISK,
    "Passed: good car, but overpriced": "#E0A43A",
    "Passed: profitable car given up": "#4F8FA8",
}

st.set_page_config(
    page_title="Auction bid strategy",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1400px;}
      [data-testid="stMetricValue"] {font-size: 2.4rem; font-weight: 600;}
      [data-testid="stMetricLabel"] p {font-size: 0.95rem; color: #5B6672;}
      h1 {font-weight: 600; letter-spacing: -0.02em;}
      h3 {font-weight: 500; margin-bottom: 0.2rem;}
      .footnote {color: #7A8591; font-size: 0.85rem; font-style: italic;}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------
def _key(name: str) -> str:
    """Normalise a column name: 'Kick Rate', 'kick_rate', 'KickRate' -> 'kickrate'."""
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


REQUIRED = {
    "segment": ["dimension", "segment", "cars", "kickrate"],
    "grid": ["vehicleage", "mileageband", "cars", "kickrate"],
    "auction": ["auction", "month", "kickrate"],
    "policy": ["purchdate", "auction", "vehbcost", "isbadbuy", "keep",
               "maxbid", "profitifbought"],
}


@st.cache_data
def load(name: str) -> pd.DataFrame:
    path = FILES[name]
    if not path.exists():
        st.error(f"Missing file: `{path.relative_to(ROOT)}`. "
                 "Export it from the SQL / Python pipeline (see README).")
        st.stop()
    df = pd.read_csv(path)
    df.columns = [_key(c) for c in df.columns]
    missing = [c for c in REQUIRED[name] if c not in df.columns]
    if missing:
        st.error(f"`{path.name}` is missing columns: {', '.join(missing)}. "
                 f"Found: {', '.join(df.columns)}")
        st.stop()
    return df


def as_bool(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "yes", "t"])


def pct(x: float) -> str:
    return f"{x:.1%}"


def money(x: float) -> str:
    sign = "−" if x < 0 else ""
    x = abs(x)
    return f"{sign}${x/1e6:.2f}M" if x >= 1e6 else f"{sign}${x/1e3:.0f}K"


def story(title: str, *points: str) -> None:
    """Boxed 'how to read this chart' bullets, so the dashboard explains itself."""
    with st.container(border=True):
        md = f"**{title}**\n\n" + "\n".join(f"- {p}" for p in points)
        st.markdown(md.replace("$", r"\$"))  # bare $...$ would render as LaTeX


# Bullets for the segment chart, keyed by the dropdown value. Numbers come from
# tableau/segment_risk.csv; update them if the pipeline is re-run.
SEGMENT_STORY = {
    "Make": [
        "**Brand matters, but less than you'd think.** Mercury tops the list at **17%**, while Chevrolet, "
        "the biggest seller, sits at just **9.7%**.",
        "The worst offenders are *specific models*, not whole brands. The Ford Windstar goes bad **39%** of the "
        "time, the Dodge Neon **23%**. Think *watch-list*, not *blacklist*.",
    ],
    "Vehicle age": [
        "**The clock is the strongest dial.** Risk climbs every single year, from **4%** at 1 year old to **31%** at 9.",
        "A 9-year-old car is **2.5× as likely** to go bad as the average purchase.",
    ],
    "Mileage band": [
        "**Every mile leaves a mark.** Cars under 50K miles go bad **7.9%** of the time, and cars over 85K "
        "**16.5%**, more than double.",
        "Mileage hits hardest on *older* cars. See the heatmap →",
    ],
    "Auction house": [
        "**Not all auctions are equal.** ADESA's bad-buy rate is **15.2%**, against **11.5%** at Manheim.",
        "The gap holds even for cars of the same age, so it's the *channel*, not just the inventory.",
    ],
    "Size": [
        "**Sports cars are the riskiest buys (18.5%)**, followed by large SUVs and compacts.",
        "Plain large sedans and specialty vehicles are the safest at about **9%**. Boring cars are good business.",
    ],
    "Wheel type": [
        "**The blank box that costs millions.** When the wheel type is *missing* from the listing, "
        "**70%** of cars turn out bad, **5.7× the average**.",
        "A blank field usually means a rushed or partial inspection. What wasn't written down shows up after the sale.",
    ],
}


def style(fig: go.Figure, height: int = 420) -> go.Figure:
    fig.update_layout(
        template="simple_white",
        height=height,
        margin=dict(l=10, r=20, t=10, b=10),
        font=dict(color=INK, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        hoverlabel=dict(bgcolor="white"),
    )
    fig.update_xaxes(gridcolor=GRID, showgrid=True)
    fig.update_yaxes(gridcolor=GRID)
    return fig


segment = load("segment")
grid = load("grid")
auction = load("auction")
policy = load("policy")

# ---- derived policy fields (mirror the Tableau calculated fields) ----------
policy["keep"] = as_bool(policy["keep"])
policy["purchdate"] = pd.to_datetime(policy["purchdate"])
policy["policy_profit"] = policy["profitifbought"].where(policy["keep"], 0)
policy["saving"] = policy["policy_profit"] - policy["profitifbought"]
policy["pass_reason"] = "Bought"
passed = ~policy["keep"]
policy.loc[passed & (policy["isbadbuy"] == 1), "pass_reason"] = "Passed: kick avoided"
policy.loc[passed & (policy["isbadbuy"] == 0) & (policy["profitifbought"] < 0),
           "pass_reason"] = "Passed: good car, but overpriced"
policy.loc[passed & (policy["isbadbuy"] == 0) & (policy["profitifbought"] >= 0),
           "pass_reason"] = "Passed: profitable car given up"

# --------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------
st.title("Auction bid strategy")
st.caption("Which used cars turn out to be bad buys, and what a risk-adjusted "
           "bid policy would have saved. " )
st.caption("Data: Carvana “Don’t Get Kicked!” (Kaggle).")           

st.markdown(
    "### 1 in 8 cars Carvana bought at auction was a dud. Most of them were *predictable*.\n"
    "Every bad buy (a **“kick”**) means paying for a car, paying to fix or return it, and then "
    "selling it at a loss. This dashboard tells the story in two acts:\n"
    "1. **Where is the risk?** Four red flags that spot a bad buy *before* the hammer falls.\n"
    "2. **What should we bid?** A simple rule, *“never pay more than the car is worth after risk”*, "
    "tested on 14,470 real purchases. It would have added **\\$4.4M (+27%)** in profit."
)

f1, f2, f3, f4 = st.columns(4)
f1.metric("Missing wheel-type record", "70% go bad", help="vs. 12.3% fleet average")
f2.metric("9-year-old cars", "31% go bad", help="vs. 4% for 1-year-old cars")
f3.metric("85K+ miles", "2× the risk", help="16.5% vs. 7.9% under 50K miles")
f4.metric("ADESA auctions", "+3–4 pts", help="vs. Manheim, even for cars of the same age")

tab_names = ["Where is the risk?", "What would the new bid policy have done?"]
if TABLEAU_PUBLIC_URL:
    tab_names.append("Original Tableau")
tabs = st.tabs(tab_names)

# ==========================================================================
# Page 1 — Where is the risk?
# ==========================================================================
with tabs[0]:
    dims = list(segment["dimension"].dropna().unique())
    first_dim = segment[segment["dimension"] == dims[0]]
    total_cars = first_dim["cars"].sum()
    if "kicks" in segment.columns:
        fleet_rate = first_dim["kicks"].sum() / total_cars
    else:
        fleet_rate = (first_dim["kickrate"] * first_dim["cars"]).sum() / total_cars

    k1, k2, k3 = st.columns(3)
    k1.metric("cars bought", f"{total_cars:,.0f}")
    k2.metric("turned out bad", pct(fleet_rate))
    k3.metric("purchases was a bad buy", f"1 in {round(1 / fleet_rate)}")

    left, right = st.columns([1, 1.15], gap="large")

    # ---- Which segments go bad most often? ------------------------------
    with left:
        st.subheader("Which segments go bad most often?")
        c1, c2 = st.columns([2, 1])
        default = dims.index("Make") if "Make" in dims else 0
        dim = c1.selectbox("Break down by", dims, index=default)
        min_cars = c2.number_input("Min. cars per segment", 0, 5000, 300, step=50)

        seg = (segment[(segment["dimension"] == dim) & (segment["cars"] >= min_cars)]
               .sort_values("kickrate"))
        seg["lift"] = seg["kickrate"] / fleet_rate
        fig = px.bar(
            seg, x="kickrate", y="segment", orientation="h",
            custom_data=["cars", "lift"],
        )
        fig.update_traces(
            marker_color=RISK,
            hovertemplate="<b>%{y}</b><br>%{x:.1%} of these cars were bad buys"
                          "<br>%{customdata[1]:.1f}× the average"
                          "<br>%{customdata[0]:,} cars<extra></extra>",
        )
        fig.add_vline(x=fleet_rate, line_dash="dot", line_color=INK,
                      annotation_text=f"Fleet avg {fleet_rate:.1%}",
                      annotation_position="top right")
        fig.update_xaxes(tickformat=".0%", title="% of cars that were bad buys")
        fig.update_yaxes(title=None)
        st.plotly_chart(style(fig, height=max(380, 26 * len(seg) + 80)),
                        width="stretch")
        st.markdown(f'<p class="footnote">Segments with fewer than {min_cars:,} '
                    'cars hidden.</p>', unsafe_allow_html=True)
        story(
            "How to read it",
            "Bars past the dotted line are **riskier than average**.",
            *SEGMENT_STORY.get(dim, ["Switch the dropdown to compare other ways of slicing the fleet."]),
        )

    with right:
        # ---- Older + higher-mileage = riskier ----------------------------
        st.subheader("Older + higher-mileage = riskier")
        g = grid[grid["cars"] >= 50]
        heat = g.pivot_table(index="mileageband", columns="vehicleage",
                             values="kickrate").sort_index()
        heat = heat[sorted(heat.columns)]
        fig = go.Figure(go.Heatmap(
            z=heat.values,
            x=[str(c) for c in heat.columns],
            y=heat.index.astype(str),
            colorscale=[[0, "#FBE9D7"], [0.5, "#E8894A"], [1, "#8C2D1A"]],
            text=[[("" if pd.isna(v) else f"{v:.1%}") for v in row] for row in heat.values],
            texttemplate="%{text}",
            hovertemplate="Age %{x} yrs · %{y}<br>%{z:.1%} bad buys<extra></extra>",
            colorbar=dict(title="Bad-buy rate", tickformat=".0%"),
            xgap=2, ygap=2,
        ))
        fig.update_xaxes(title="Vehicle age (years)", showgrid=False)
        fig.update_yaxes(title=None, autorange="reversed", showgrid=False)
        st.plotly_chart(style(fig, height=300), width="stretch")
        story(
            "Time and miles: the double whammy",
            "Each cell is the bad-buy rate for one age and mileage band. **Darker = riskier.**",
            "**Young cars forgive miles.** At 1 year old, risk stays around **3–5%** no matter how far the car has been driven.",
            "**Old cars don't.** A 7-year-old car goes from **8.5%** under 50K miles to **24%** over 85K.",
            "The danger zone is the **bottom-right corner**: 9-year-old cars with 85K+ miles go bad "
            "**34%** of the time, about *one in three*.",
        )

        # ---- Is any auction getting worse? -------------------------------
        st.subheader("Is any auction getting worse?")
        a = auction.copy()
        a["month"] = pd.to_datetime(a["month"])
        a = a.sort_values(["auction", "month"])
        a["ma3"] = a.groupby("auction")["kickrate"].transform(
            lambda s: s.rolling(3, min_periods=1).mean())
        fig = px.line(a, x="month", y="ma3", color="auction",
                      color_discrete_sequence=[RISK, "#4F8FA8", "#9AA5B1"])
        fig.update_traces(line_width=2.5,
                          hovertemplate="%{x|%b %Y}: %{y:.1%}<extra></extra>")
        fig.update_yaxes(tickformat=".0%", title="Bad-buy rate (3-mo avg)",
                         rangemode="tozero")
        fig.update_xaxes(title=None)
        st.plotly_chart(style(fig, height=320), width="stretch")
        story(
            "Where you buy matters as much as what you buy",
            "Each line is one auction house's bad-buy rate, smoothed over 3 months.",
            "**ADESA runs hottest almost every month**, at about **15%** in both 2009 and 2010.",
            "Manheim and the smaller auctions crept up by about **2 points** in 2010, so the gap is closing "
            "from the *wrong* direction.",
            "**Takeaway:** auction house belongs in the bid, and a rising line is an early warning to tighten up.",
        )

    st.divider()
    st.markdown(
        "#### Act 1 in one breath\n"
        "- **A blank wheel-type field is the loudest alarm in the data.** 70% of those cars go bad.\n"
        "- **Age and mileage compound.** Each one is bad on its own; together they're toxic.\n"
        "- **The auction house carries its own risk**, and ADESA is consistently the riskiest.\n"
        "- **What about overpaying?** Paying above market *looks* risky, but that's because older cars "
        "sell further above book value. Compare cars of the same age and the effect disappears.\n"
        "- These are *knowable before you bid*, so the next tab turns them into a price."
    )

# ==========================================================================
# Page 2 — What would the new bid policy have done?
# ==========================================================================
with tabs[1]:
    st.markdown(
        "### Don't just win the auction. Win the *deal*.\n"
        "**The rule:** for every car, estimate its chance of going bad. Then set a **maximum bid** "
        "equal to what it's worth when good, minus the expected cost of it going bad. "
        "If the auction price goes over that number, **walk away.**\n\n"
        "We replayed this rule on Carvana's **last 5 months of real purchases** (Aug–Dec 2010), "
        "cars the model had *never seen*."
    )
    hist_profit = policy["profitifbought"].sum()
    saving = policy["saving"].sum()
    rate_before = policy["isbadbuy"].mean()
    rate_after = policy.loc[policy["keep"], "isbadbuy"].mean()
    volume_change = policy["keep"].mean() - 1

    k1, k2, k3 = st.columns(3)
    k1.metric("profit vs. what we actually bought", "+" + money(saving),
              f"{saving / abs(hist_profit):+.0%} profit" if hist_profit else None)
    k2.metric("bad-buy rate", f"{rate_before:.1%} → {rate_after:.1%}")
    k3.metric("cars bought", f"{volume_change:+.0%}".replace("-", "−"),
              help="Showing the volume drop next to the saving — "
                   "the trade-off is part of the story.")

    left, right = st.columns(2, gap="large")

    # ---- Where does the saving come from? (waterfall) -------------------
    with left:
        st.subheader(f"Where does the {money(saving)} come from?")
        parts = (policy[policy["pass_reason"] != "Bought"]
                 .groupby("pass_reason")
                 .agg(impact=("profitifbought", lambda s: -s.sum()),
                      cars=("profitifbought", "size")))
        order = ["Passed: kick avoided", "Passed: good car, but overpriced",
                 "Passed: profitable car given up"]
        parts = parts.reindex([o for o in order if o in parts.index])
        labels = [f"{r.replace('Passed: ', '').capitalize()}<br>"
                  f"<span style='font-size:11px;color:{MUTED}'>{int(c):,} cars</span>"
                  for r, c in zip(parts.index, parts["cars"])]
        fig = go.Figure(go.Waterfall(
            orientation="v",
            x=labels + ["Net saving"],
            measure=["relative"] * len(parts) + ["total"],
            y=list(parts["impact"]) + [0],
            text=[money(v) for v in parts["impact"]] + [money(saving)],
            textposition="outside",
            increasing=dict(marker=dict(color=SAVING)),
            decreasing=dict(marker=dict(color=LOSS)),
            totals=dict(marker=dict(color=INK)),
            connector=dict(line=dict(color=GRID)),
            hovertemplate="%{x}<br>%{text}<extra></extra>",
        ))
        fig.update_yaxes(tickprefix="$", tickformat="~s", title="Profit impact")
        fig.update_layout(showlegend=False)
        st.plotly_chart(style(fig, height=400), width="stretch")
        story(
            "Walk away from 4,095 cars, pocket $4.4M",
            "Each bar is one *type* of car the rule told us to skip, and what skipping it did to profit.",
            "**The big win: dodging the duds.** We skip **1,028 cars that went bad**, avoiding "
            "**$4.5M** in losses.",
            "**The quiet win: refusing to overpay.** We also skip **1,362 good cars** that were priced "
            "too high to make money, saving another **$0.8M**.",
            "**The honest cost.** We'd also miss **1,705 profitable cars**, giving up **$0.9M**. "
            "No rule is perfect, but the trade is about **6 to 1** in our favor.",
        )

        # ---- Savings build up every week ---------------------------------
        st.subheader("Savings build up every week")
        wk = (policy.set_index("purchdate")["saving"]
              .resample("W").sum().cumsum().reset_index())
        fig = px.area(wk, x="purchdate", y="saving")
        fig.update_traces(line_color=SAVING, fillcolor="rgba(58,125,92,0.15)",
                          hovertemplate="Week of %{x|%b %d}: %{y:$,.0f}<extra></extra>")
        fig.update_yaxes(tickprefix="$", tickformat="~s", title="Cumulative saving")
        fig.update_xaxes(title=None)
        st.plotly_chart(style(fig, height=340), width="stretch")
        story(
            "Steady, not lucky",
            "The line adds up the extra profit week by week across the 5-month test.",
            "**It climbs every single week.** None of the 20 weeks lost money, and even the weakest added about **$32K**.",
            "An average week adds about **$220K**. That's a *repeatable process*, not one lucky auction.",
        )

    with right:
        # ---- Price paid vs what we'd bid ----------------------------------
        st.subheader("Price paid vs. what we’d bid")
        reasons = st.multiselect(
            "Show", list(PASS_COLORS), default=list(PASS_COLORS),
            label_visibility="collapsed")
        sc = policy[policy["pass_reason"].isin(reasons)]
        fig = px.scatter(
            sc, x="maxbid", y="vehbcost", color="pass_reason",
            color_discrete_map=PASS_COLORS, opacity=0.45, render_mode="webgl",
            category_orders={"pass_reason": list(PASS_COLORS)},
            hover_data={"auction": True, "maxbid": ":$,.0f", "vehbcost": ":$,.0f",
                        "pass_reason": False},
        )
        fig.update_traces(marker_size=4)
        hi = float(max(policy["maxbid"].max(), policy["vehbcost"].max()))
        fig.add_trace(go.Scatter(x=[0, hi], y=[0, hi], mode="lines",
                                 line=dict(color=MUTED, width=1.5, dash="dash"),
                                 name="Paid = max bid", hoverinfo="skip"))
        fig.update_xaxes(tickprefix="$", tickformat="~s", title="Our max bid")
        fig.update_yaxes(tickprefix="$", tickformat="~s", title="Price we paid")
        st.plotly_chart(style(fig, height=480), width="stretch")
        st.markdown('<p class="footnote">Dots above the dashed line: we paid more '
                    'than the car was worth to us.</p>', unsafe_allow_html=True)
        story(
            "Above the line = overpaid",
            "Each dot is one car. Across: the most our rule would have paid. Up: what Carvana actually paid.",
            "**Dots below the dashed line** were bought at or under their risk-adjusted value. Those are good deals, and we keep them.",
            "**Dots above the line** cost more than they were worth. That's **28% of all purchases**.",
            "The skipped cars went bad **25%** of the time; the cars we kept, just **8%**. "
            "*The rule finds the duds.*",
        )

        # ---- Saving by auction house --------------------------------------
        st.subheader("Saving by auction house")
        by_a = (policy.groupby("auction")
                .agg(saving=("saving", "sum"),
                     kicks_avoided=("pass_reason",
                                    lambda s: (s == "Passed: kick avoided").sum()))
                .sort_values("saving").reset_index())
        fig = px.bar(by_a, x="saving", y="auction", orientation="h",
                     text=[money(v) for v in by_a["saving"]],
                     custom_data=["kicks_avoided"])
        fig.update_traces(marker_color=SAVING, textposition="outside",
                          hovertemplate="<b>%{y}</b><br>%{text} saved"
                                        "<br>%{customdata[0]:,} kicks avoided"
                                        "<extra></extra>")
        fig.update_xaxes(tickprefix="$", tickformat="~s", title=None)
        fig.update_yaxes(title=None)
        st.plotly_chart(style(fig, height=220), width="stretch")
        story(
            "Every auction house wins",
            "Extra profit from the rule, split by where the car was bought.",
            "**Manheim brings in the most ($2.0M)** simply because most cars are bought there.",
            "**ADESA is where the rule works hardest.** It skips **31%** of ADESA cars, the most of any "
            "auction, which matches ADESA's higher bad-buy rate in Act 1.",
            "**Rollout idea:** start where the savings are biggest, then expand.",
        )

    st.divider()
    st.markdown(
        "#### The bottom line\n"
        "- **+\\$4.4M profit (+27%)** on the same 5 months of auctions, with the bad-buy rate cut from "
        "**12.8% to 8.0%**.\n"
        "- **The price: 28% fewer cars bought.** Fewer cars, but *better* cars. Whether that's worth it "
        "depends on how much inventory the business needs.\n"
        "- **The rule mostly says no to old cars.** It skips about **3 in 4 cars aged 6+ years** but only "
        "**2% of cars aged 3 or younger**.\n"
        "- **Next step: prove it live.** Run an A/B test where buyers alternate weeks between the old "
        "and new rule (full plan in the GitHub repo).\n\n"
        "*Read before quoting:* the data has no resale prices, so repair and kick-loss costs are "
        "assumptions. The saving stays positive across every cost scenario tested (**\\$2.6M–\\$6.6M**). "
        "We also only see cars Carvana actually won, so real-world gains will likely be smaller."
    )

    start, end = policy["purchdate"].min(), policy["purchdate"].max()
    st.markdown(
        f'<p class="footnote">Dollar figures use assumed recon and kick-loss costs '
        f'(see README). Back-test on {start:%b}–{end:%b %Y} purchases, not a forecast.</p>',
        unsafe_allow_html=True)

# ==========================================================================
# Optional — embedded Tableau Public version
# ==========================================================================
if TABLEAU_PUBLIC_URL:
    with tabs[2]:
        sep = "&" if "?" in TABLEAU_PUBLIC_URL else "?"
        st.iframe(f"{TABLEAU_PUBLIC_URL}{sep}:embed=y&:showVizHome=no",
                  height=1050)

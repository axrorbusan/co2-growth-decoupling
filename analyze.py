"""
Who got richer while cutting CO₂?  (Our World in Data, 2005 → 2022)

Questions
  1. Which countries grew GDP while their CO₂ emissions fell (absolute decoupling)?
  2. Does that still hold when emissions embedded in imports are counted (consumption-based CO₂)?

Input : data/raw/owid-co2-data.csv.gz, data/raw/ne_110m_admin_0_countries.geojson
Output: output/*.png, output/results.json, output/country_changes.csv
Run   : python analyze.py
"""
import json
import os

import geopandas as gpd
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

matplotlib.use("Agg")
HERE = os.path.dirname(os.path.abspath(__file__))
P = lambda *a: os.path.join(HERE, *a)
START, END = 2005, 2022            # GDP series ends in 2022
MIN_POP = 1_000_000

INK, MUTED = "#1F2933", "#6B7280"
COLORS = {"Absolute decoupling": "#15803D", "Relative decoupling": "#84CC16",
          "Coupled growth": "#F59E0B", "GDP fell": "#9CA3AF"}
FOCUS = {"USA": "United States", "GBR": "United Kingdom", "DEU": "Germany",
         "CHN": "China", "IND": "India", "BRA": "Brazil"}


def style():
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False,
                         "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.titleweight": "bold", "axes.titlesize": 13, "font.size": 10})


def pct(a, b):
    return 100 * (b / a - 1)


def category(g, c):
    if g <= 0:
        return "GDP fell"
    if c < 0:
        return "Absolute decoupling"
    if g > c:
        return "Relative decoupling"
    return "Coupled growth"


def main():
    style()
    os.makedirs(P("output"), exist_ok=True)
    raw = pd.read_csv(P("data", "raw", "owid-co2-data.csv.gz"))
    df = raw[raw["iso_code"].str.len() == 3]                    # drop OWID_* aggregates
    a = df[df.year == START].set_index("iso_code")
    b = df[df.year == END].set_index("iso_code")
    keep = (a.index.intersection(b.index))
    t = pd.DataFrame({
        "country": b.loc[keep, "country"],
        "population": b.loc[keep, "population"],
        "gdp_pct": pct(a.loc[keep, "gdp"], b.loc[keep, "gdp"]),
        "co2_pct": pct(a.loc[keep, "co2"], b.loc[keep, "co2"]),
        "cons_pct": pct(a.loc[keep, "consumption_co2"], b.loc[keep, "consumption_co2"]),
        "co2_end": b.loc[keep, "co2"],
        "trade_share_end": b.loc[keep, "trade_co2_share"],
    })
    n_all = len(t)
    t = t[(t.population >= MIN_POP)].dropna(subset=["gdp_pct", "co2_pct"])
    t["category"] = [category(g, c) for g, c in zip(t.gdp_pct, t.co2_pct)]
    t["category_cons"] = [category(g, c) if pd.notna(c) else None for g, c in zip(t.gdp_pct, t.cons_pct)]
    t.to_csv(P("output", "country_changes.csv"))

    abs_dec = t[t.category == "Absolute decoupling"]
    with_cons = abs_dec.dropna(subset=["cons_pct"])
    still = with_cons[with_cons.category_cons == "Absolute decoupling"]
    lost = with_cons[with_cons.category_cons != "Absolute decoupling"]

    world = raw[raw.country == "World"].set_index("year")
    res = {
        "window": [START, END],
        "n_countries_analyzed": int(len(t)),
        "n_country_rows_before_filters": int(n_all),
        "category_counts": t.category.value_counts().to_dict(),
        "absolute_decouplers": sorted(abs_dec.country.tolist()),
        "absolute_decouplers_share_of_world_co2_end": float(abs_dec.co2_end.sum() / world.loc[END, "co2"]),
        "consumption_check": {
            "decouplers_with_consumption_data": int(len(with_cons)),
            "still_decoupled_on_consumption_basis": int(len(still)),
            "lost_on_consumption_basis": sorted(lost.country.tolist()),
            "median_territorial_pct": float(with_cons.co2_pct.median()),
            "median_consumption_pct": float(with_cons.cons_pct.median()),
        },
        # OWID's "World" row has no GDP → sum countries that report GDP in both years
        "world": {"gdp_pct_sum_of_countries": float(pct(a.loc[keep, "gdp"].dropna().reindex(b.loc[keep, "gdp"].dropna().index).sum(),
                                                         b.loc[keep, "gdp"].dropna().reindex(a.loc[keep, "gdp"].dropna().index).sum())),
                  "co2_pct": float(pct(world.loc[START, "co2"], world.loc[END, "co2"]))},
        "focus": {iso: {"gdp_pct": float(t.loc[iso, "gdp_pct"]), "co2_pct": float(t.loc[iso, "co2_pct"]),
                        "cons_pct": None if pd.isna(t.loc[iso, "cons_pct"]) else float(t.loc[iso, "cons_pct"]),
                        "category": t.loc[iso, "category"]} for iso in FOCUS},
    }

    # ---------------------------------------------------------------- fig 1: scatter
    fig, ax = plt.subplots(figsize=(10, 7))
    for cat, col in COLORS.items():
        s = t[t.category == cat]
        ax.scatter(s.gdp_pct, s.co2_pct, s=np.clip(np.sqrt(s.population) / 120, 8, 400), color=col,
                   alpha=0.8, edgecolor="white", linewidth=0.5, label=f"{cat} ({len(s)})")
    lim = max(abs(t.gdp_pct).max(), 1)
    xs = np.linspace(0, 400, 50)
    ax.plot(xs, xs, color=MUTED, lw=0.8, ls="--")
    ax.text(325, 250, "GDP and CO₂\ngrow equally", color=MUTED, fontsize=8, ha="right")
    ax.axhline(0, color=INK, lw=0.8); ax.axvline(0, color=INK, lw=0.8)
    label = set(FOCUS) | set(t.nlargest(8, "population").index) | set(abs_dec.nlargest(6, "population").index)
    for iso in label:
        if iso in t.index:
            r = t.loc[iso]
            ax.annotate(r.country, (r.gdp_pct, r.co2_pct), xytext=(4, 3), textcoords="offset points",
                        fontsize=8, color=INK)
    ax.set_xlim(-60, 420); ax.set_ylim(-70, 330)
    off = t[t.co2_pct > 330]
    ax.scatter(off.gdp_pct, [324] * len(off), marker="^", s=28, color=COLORS["Coupled growth"], clip_on=False)
    top3 = ", ".join(off.nlargest(3, "co2_pct").country)
    ax.text(415, 312, f"▲ {len(off)} countries above the chart (CO₂ +{off.co2_pct.min():.0f}% to +{off.co2_pct.max():,.0f}%),\n"
            f"low emitters growing from a tiny base, e.g. {top3}", fontsize=7.8, color="#B45309", ha="right", va="top")
    ax.set_xlabel(f"GDP change {START}–{END} (%)"); ax.set_ylabel(f"CO₂ change {START}–{END} (%, territorial)")
    ax.set_title("Getting richer without emitting more: who managed it?", loc="left")
    ax.legend(frameon=False, fontsize=9, loc="upper left", title="Dot size = population", title_fontsize=8.5)
    ax.text(0, -0.1, "Source: Our World in Data CO₂ dataset (GCP, Maddison GDP). Countries with population ≥ 1 million.",
            transform=ax.transAxes, fontsize=8, color=MUTED, va="top")
    fig.savefig(P("output", "fig1_scatter.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)

    # ---------------------------------------------------------------- fig 2: map
    w = gpd.read_file(P("data", "raw", "ne_110m_admin_0_countries.geojson"))
    w["iso"] = np.where(w["ISO_A3"] == "-99", w["ADM0_A3"], w["ISO_A3"])
    w = w[w["iso"] != "ATA"].merge(t[["category"]], left_on="iso", right_index=True, how="left")
    res["map_join"] = {"map_countries": int(len(w)), "matched": int(w.category.notna().sum())}
    fig, ax = plt.subplots(figsize=(13, 6.4))
    w.plot(ax=ax, color="#E5E7EB", edgecolor="white", linewidth=0.3)
    for cat, col in COLORS.items():
        w[w.category == cat].plot(ax=ax, color=col, edgecolor="white", linewidth=0.3)
    ax.set_xticks([]); ax.set_yticks([]); ax.set_xlabel(""); ax.set_ylabel("")
    for s in ax.spines.values():
        s.set_visible(False)
    handles = [matplotlib.patches.Patch(color=c, label=k) for k, c in COLORS.items()]
    handles.append(matplotlib.patches.Patch(color="#E5E7EB", label="No data / < 1M people"))
    ax.legend(handles=handles, frameon=False, loc="lower left", fontsize=9)
    ax.set_title(f"GDP vs CO₂, {START}–{END}", loc="left")
    fig.savefig(P("output", "fig2_map.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    # ---------------------------------------------------------------- fig 3: dumbbell territorial vs consumption
    d = with_cons.sort_values("co2_pct")
    fig, ax = plt.subplots(figsize=(9, max(4, 0.32 * len(d) + 1)))
    y = np.arange(len(d))
    ax.hlines(y, d.co2_pct, d.cons_pct, color="#D1D5DB", lw=2)
    ax.scatter(d.co2_pct, y, color="#15803D", s=30, zorder=3, label="Territorial CO₂ (produced inside the country)")
    ax.scatter(d.cons_pct, y, color="#B91C1C", s=30, zorder=3, label="Consumption CO₂ (incl. emissions in imports)")
    for yi, (_, r) in zip(y, d.iterrows()):
        if r.category_cons != "Absolute decoupling":
            ax.text(max(r.cons_pct, r.co2_pct) + 1.5, yi, "↑ not decoupled on consumption basis",
                    va="center", fontsize=7.5, color="#B91C1C")
    ax.axvline(0, color=INK, lw=0.8)
    ax.set_yticks(y, d.country)
    ax.set_xlabel(f"CO₂ change {START}–{END} (%)")
    ax.set_title("Absolute decouplers: does the cut survive counting imports?", loc="left")
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    fig.savefig(P("output", "fig3_consumption_check.png"), dpi=160, bbox_inches="tight")
    plt.close(fig)

    # ---------------------------------------------------------------- fig 4: indexed lines
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.5), sharex=True)
    for ax, (iso, name) in zip(axes.flat, FOCUS.items()):
        s = df[(df.iso_code == iso) & df.year.between(START, END)].set_index("year")
        for col, c, lab in (("gdp", INK, "GDP"), ("co2", "#15803D", "CO₂ territorial"),
                            ("consumption_co2", "#B91C1C", "CO₂ consumption")):
            v = s[col]
            if v.notna().sum() > 2:
                ax.plot(v.index, 100 * v / v.loc[START], color=c, lw=2 if col == "gdp" else 1.6, label=lab)
        ax.axhline(100, color=MUTED, lw=0.6, ls=":")
        ax.set_title(name, loc="left", fontsize=11)
        ax.grid(axis="y", color="#E5E7EB")
        ax.set_xticks([2005, 2010, 2015, 2020])
    axes.flat[0].legend(frameon=False, fontsize=8)
    fig.suptitle(f"Indexed, {START} = 100", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(P("output", "fig4_focus_countries.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)

    with open(P("output", "results.json"), "w") as f:
        json.dump(res, f, indent=2, default=float)
    print(json.dumps(res, indent=2, default=float))


if __name__ == "__main__":
    main()

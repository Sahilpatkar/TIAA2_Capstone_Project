"""
Poster-ready Component IC bar chart — Option A from the poster review.

Shows LAS composite + 3 underlying factors at 90-day horizon,
with significance stars, sorted by magnitude, LAS composite highlighted.

Data source: data/backtest_results_full500/summary.json (n=1,925)

Usage:
    python scripts/poster_component_ic_chart.py
"""

import json
import os

import matplotlib.pyplot as plt
import numpy as np

OUTPUT_DIR = "data/poster_assets"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load full500 backtest summary
with open("data/backtest_results_full500/summary.json") as f:
    summary = json.load(f)

# Extract 90-day component IC
rows = [c for c in summary["component_ic"] if c["horizon"] == 90]
wanted = ["las", "change_intensity", "car", "attention_proxy"]
rows = [c for c in rows if c["factor"] in wanted]

label_map = {
    "las": "LAS Composite",
    "change_intensity": "Change Intensity",
    "car": "CAR (Contrarian)",
    "attention_proxy": "Attention Proxy",
}


def stars(p):
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


# Sort by absolute IC magnitude, LAS on top
rows.sort(key=lambda c: abs(c["ic"]), reverse=True)
# Force LAS Composite to the top for visual emphasis
rows.sort(key=lambda c: 0 if c["factor"] == "las" else 1)

labels = [label_map[c["factor"]] for c in rows]
ics = [c["ic"] for c in rows]
pvals = [c["p_value"] for c in rows]
n = rows[0]["n"]

# Colors
LAS_COLOR = "#1B4F72"
POS_COLOR = "#27AE60"
NEG_COLOR = "#C0392B"
ATTN_COLOR = "#9B59B6"
colors = []
for c in rows:
    if c["factor"] == "las":
        colors.append(LAS_COLOR)
    elif c["factor"] == "car":
        colors.append(NEG_COLOR)
    elif c["factor"] == "change_intensity":
        colors.append(POS_COLOR)
    else:
        colors.append(ATTN_COLOR)

# Build figure
fig, ax = plt.subplots(figsize=(11, 5.5))

y_pos = np.arange(len(labels))
bars = ax.barh(
    y_pos,
    ics,
    color=colors,
    edgecolor="white",
    linewidth=1.5,
    height=0.65,
)

# Highlight LAS Composite with a slight glow
for i, c in enumerate(rows):
    if c["factor"] == "las":
        bars[i].set_edgecolor("#F39C12")
        bars[i].set_linewidth(3)

# Benchmark lines at ±0.10 (commercially meaningful threshold)
ax.axvline(0.10, color="#27AE60", linestyle="--", alpha=0.4, linewidth=1.5)
ax.axvline(-0.10, color="#27AE60", linestyle="--", alpha=0.4, linewidth=1.5)
ax.axvline(0, color="black", linewidth=0.8)

# Value labels + significance stars
for i, (ic, p) in enumerate(zip(ics, pvals)):
    star_str = stars(p)
    if ic >= 0:
        # Label to the right of the bar
        ax.text(
            ic + 0.004,
            i,
            f"{ic:+.3f} {star_str}",
            va="center",
            ha="left",
            fontsize=13,
            fontweight="bold",
            color="black",
        )
    else:
        # Label to the left of the bar
        ax.text(
            ic - 0.004,
            i,
            f"{ic:+.3f} {star_str}",
            va="center",
            ha="right",
            fontsize=13,
            fontweight="bold",
            color="black",
        )

# Annotations on benchmark lines
ax.text(
    0.105,
    len(labels) - 0.35,
    "Commercially\nmeaningful\nthreshold",
    fontsize=9,
    color="#27AE60",
    alpha=0.8,
    style="italic",
)

# Ticks and labels
ax.set_yticks(y_pos)
ax.set_yticklabels(labels, fontsize=13, fontweight="bold")
ax.invert_yaxis()
ax.set_xlabel("Information Coefficient (IC)", fontsize=12, fontweight="bold")
ax.set_title(
    f"Signal Predictive Power at 90-Day Horizon  (n = {n:,})",
    fontsize=15,
    fontweight="bold",
    pad=15,
)

# Legend / footnote
legend_text = (
    "Significance:  *** p < 0.001    ** p < 0.01    * p < 0.05\n"
    "Data: 1,925 SEC filings across 369 S&P 500 companies, "
    "yearly-grouped Spearman IC."
)
fig.text(
    0.5,
    -0.02,
    legend_text,
    ha="center",
    fontsize=10,
    style="italic",
    color="#555",
)

# Clean styling
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_visible(False)
ax.grid(axis="x", alpha=0.3, linestyle=":")
ax.set_axisbelow(True)
ax.set_xlim(-0.16, 0.21)

plt.tight_layout()

# Save as high-DPI PNG for poster printing
out_png = os.path.join(OUTPUT_DIR, "component_ic_90d_poster.png")
plt.savefig(out_png, dpi=300, bbox_inches="tight", facecolor="white")
print(f"Saved: {out_png}")

# Also save a PDF (vector, best for printing)
out_pdf = os.path.join(OUTPUT_DIR, "component_ic_90d_poster.pdf")
plt.savefig(out_pdf, bbox_inches="tight", facecolor="white")
print(f"Saved: {out_pdf}")

plt.show()

"""
Backtest comparison: LazyPrices paper strategy vs our LAS system.

Paper strategy (baseline):
  - High text change → short (sell)
  - Low text change  → long (buy)
  - No attention or CAR factors

Our LAS system:
  - Multi-factor signals using change + attention + CAR
  - Confidence gating, key-section boost, contrarian buy logic

Usage:
    python backtest_comparison.py
"""

import json
import os

import numpy as np
import pandas as pd
from scipy import stats

from tiaa import config
from tiaa.backtest.core import (
    FORWARD_HORIZONS,
    load_backtest_data,
    enrich_with_forward_returns,
    assign_signals,
    compute_ic,
    quintile_analysis,
    portfolio_simulation,
    signal_hit_rate,
    _SIGNAL_DIRECTION,
)


# ---------------------------------------------------------------------------
# Paper baseline: signal based purely on change_intensity
# ---------------------------------------------------------------------------

def assign_paper_signals(df: pd.DataFrame, n_bins: int = 5) -> pd.DataFrame:
    """
    Replicate the LazyPrices paper strategy:
      - Top quintile change → sell (short)
      - Bottom quintile change → buy (long)
      - Middle quintiles → neutral (no trade)
    """
    df = df.copy()
    df["paper_quintile"] = pd.qcut(
        df["change_intensity"], n_bins, labels=False, duplicates="drop"
    ) + 1

    def _paper_signal(q, n=n_bins):
        if q == n:       # highest change → short
            return "sell"
        if q == n - 1:   # second highest → caution
            return "caution"
        if q == 1:       # lowest change → buy
            return "buy"
        return "neutral"

    df["paper_signal"] = df["paper_quintile"].apply(_paper_signal)
    return df


# ---------------------------------------------------------------------------
# Paper-style portfolio simulation
# ---------------------------------------------------------------------------

def paper_portfolio_simulation(df: pd.DataFrame, horizon: int = 90) -> dict:
    """Run portfolio sim using paper signals instead of LAS signals."""
    col = f"fwd_{horizon}d"
    if col not in df.columns or "paper_signal" not in df.columns:
        return {"error": "missing columns"}

    sub = df.dropna(subset=[col, "paper_signal"]).copy()
    sub["trade_return"] = 0.0

    for idx, row in sub.iterrows():
        direction = _SIGNAL_DIRECTION.get(row["paper_signal"], 0)
        sub.at[idx, "trade_return"] = direction * row[col]

    trades = sub[sub["trade_return"] != 0]
    if trades.empty:
        return {"horizon": horizon, "n_trades": 0, "mean_return": None,
                "sharpe": None, "hit_rate": None, "total_return": None,
                "max_drawdown": None}

    sorted_trades = trades.sort_values("filed_date")
    equity = (1 + sorted_trades["trade_return"]).cumprod()
    peak = equity.cummax()
    drawdown = (equity - peak) / peak

    mean_ret = sorted_trades["trade_return"].mean()
    std_ret = sorted_trades["trade_return"].std()
    sharpe = (mean_ret / std_ret) * np.sqrt(252 / horizon) if std_ret > 0 else None
    wins = (sorted_trades["trade_return"] > 0).sum()

    return {
        "horizon": horizon,
        "n_trades": len(sorted_trades),
        "mean_return": round(mean_ret, 6),
        "total_return": round(float(equity.iloc[-1]) - 1, 6),
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "hit_rate": round(wins / len(sorted_trades), 4),
        "max_drawdown": round(float(drawdown.min()), 6),
    }


# ---------------------------------------------------------------------------
# Paper-style hit rate
# ---------------------------------------------------------------------------

def paper_hit_rate(df: pd.DataFrame, horizons: list[int] | None = None) -> pd.DataFrame:
    """Signal hit rate using paper signals."""
    horizons = horizons or FORWARD_HORIZONS
    rows = []
    for h in horizons:
        col = f"fwd_{h}d"
        if col not in df.columns:
            continue
        sub = df.dropna(subset=[col, "paper_signal"]).copy()
        for sig, grp in sub.groupby("paper_signal"):
            expected_dir = _SIGNAL_DIRECTION.get(sig, 0)
            n = len(grp)
            if expected_dir == 0:
                correct = (grp[col].abs() < 0.03).sum()
            elif expected_dir > 0:
                correct = (grp[col] > 0).sum()
            else:
                correct = (grp[col] < 0).sum()
            mean_ret = grp[col].mean()
            rows.append({
                "horizon": h, "signal": sig, "count": n,
                "hit_rate": round(correct / n, 4) if n > 0 else None,
                "mean_fwd_return": round(mean_ret, 6),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Paper IC: just change_intensity vs forward returns
# ---------------------------------------------------------------------------

def paper_ic(df: pd.DataFrame, horizons: list[int] | None = None) -> pd.DataFrame:
    """
    Paper's core metric: Spearman correlation between change_intensity
    and forward returns. Paper expects NEGATIVE correlation (high change → bad).
    """
    horizons = horizons or FORWARD_HORIZONS
    rows = []
    for h in horizons:
        col = f"fwd_{h}d"
        if col not in df.columns:
            continue
        sub = df.dropna(subset=[col, "change_intensity"])
        if len(sub) < 5:
            rows.append({"horizon": h, "ic": None, "p_value": None, "n": len(sub)})
            continue
        rho, p = stats.spearmanr(sub["change_intensity"], sub[col])
        rows.append({
            "horizon": h,
            "ic": round(rho, 4) if not np.isnan(rho) else None,
            "p_value": round(p, 4) if not np.isnan(p) else None,
            "n": len(sub),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------

def run_comparison(output_dir: str | None = None) -> dict:
    output_dir = output_dir or os.path.join(config.DATA_DIR, "backtest_comparison")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 65)
    print("  BACKTEST COMPARISON: LazyPrices Paper vs Our LAS System")
    print("=" * 65)

    # Load and enrich data (shared between both strategies)
    print("\n[1/5] Loading filings...")
    df = load_backtest_data()
    print(f"  {len(df)} filings across {df['ticker'].nunique()} tickers")

    print("\n[2/5] Fetching forward returns...")
    df = enrich_with_forward_returns(df)

    # --- OUR LAS SYSTEM ---
    print("\n[3/5] Running OUR LAS system...")
    df_las = assign_signals(df.copy())

    las_ic = compute_ic(df_las)
    las_quint = quintile_analysis(df_las)
    las_hits = signal_hit_rate(df_las)
    las_sims = {h: portfolio_simulation(df_las, h) for h in FORWARD_HORIZONS}

    # --- PAPER BASELINE ---
    print("\n[4/5] Running PAPER baseline (change-only)...")
    df_paper = assign_paper_signals(df.copy())

    p_ic = paper_ic(df_paper)
    # Quintile analysis on change_intensity (paper's core approach)
    df_paper_q = df_paper.copy()
    df_paper_q["las"] = -df_paper_q["change_intensity"]  # invert: paper says high change = bad
    p_quint = quintile_analysis(df_paper_q)
    p_hits = paper_hit_rate(df_paper)
    p_sims = {h: paper_portfolio_simulation(df_paper, h) for h in FORWARD_HORIZONS}

    # --- COMPARISON OUTPUT ---
    print("\n[5/5] Generating comparison...\n")

    print("=" * 65)
    print("  1. INFORMATION COEFFICIENT (predictive power of score)")
    print("=" * 65)
    print("\n  PAPER (change_intensity vs returns — expects negative IC):")
    print(f"  {p_ic.to_string(index=False)}")
    print("\n  OUR LAS (composite LAS vs returns — expects positive IC):")
    print(f"  {las_ic.to_string(index=False)}")

    print("\n" + "=" * 65)
    print("  2. QUINTILE SPREAD (top vs bottom quintile return gap)")
    print("=" * 65)
    print("\n  PAPER (quintiles by -change_intensity):")
    spreads_paper = p_quint[p_quint["quintile"] == "L/S"][["horizon", "mean_return"]]
    if not spreads_paper.empty:
        print(f"  {spreads_paper.to_string(index=False)}")
    print("\n  OUR LAS (quintiles by LAS):")
    spreads_las = las_quint[las_quint["quintile"] == "L/S"][["horizon", "mean_return"]]
    if not spreads_las.empty:
        print(f"  {spreads_las.to_string(index=False)}")

    print("\n" + "=" * 65)
    print("  3. SIGNAL HIT RATES")
    print("=" * 65)
    print("\n  PAPER signals:")
    print(f"  {p_hits.to_string(index=False)}")
    print("\n  OUR LAS signals:")
    print(f"  {las_hits.to_string(index=False)}")

    print("\n" + "=" * 65)
    print("  4. PORTFOLIO SIMULATION (long/short based on signals)")
    print("=" * 65)

    sim_rows = []
    for h in FORWARD_HORIZONS:
        ps = p_sims[h]
        ls = las_sims[h]
        sim_rows.append({
            "horizon": h,
            "paper_trades": ps.get("n_trades", 0),
            "paper_mean_ret": ps.get("mean_return"),
            "paper_total_ret": ps.get("total_return"),
            "paper_sharpe": ps.get("sharpe"),
            "paper_hit_rate": ps.get("hit_rate"),
            "paper_max_dd": ps.get("max_drawdown"),
            "las_trades": ls.get("n_trades", 0),
            "las_mean_ret": ls.get("mean_return"),
            "las_total_ret": ls.get("total_return"),
            "las_sharpe": ls.get("sharpe"),
            "las_hit_rate": ls.get("hit_rate"),
            "las_max_dd": ls.get("max_drawdown"),
        })

    sim_df = pd.DataFrame(sim_rows)
    print(f"\n{sim_df.to_string(index=False)}")

    print("\n" + "=" * 65)
    print("  5. SIGNAL DISTRIBUTION COMPARISON")
    print("=" * 65)
    print("\n  PAPER:")
    print(f"  {df_paper['paper_signal'].value_counts().to_string()}")
    print("\n  OUR LAS:")
    print(f"  {df_las['signal'].value_counts().to_string()}")

    # --- WINNER SUMMARY ---
    print("\n" + "=" * 65)
    print("  SUMMARY: Which approach wins at each horizon?")
    print("=" * 65)
    for h in FORWARD_HORIZONS:
        ps = p_sims[h]
        ls = las_sims[h]
        p_sharpe = ps.get("sharpe") or -999
        l_sharpe = ls.get("sharpe") or -999
        winner = "OUR LAS" if l_sharpe > p_sharpe else "PAPER" if p_sharpe > l_sharpe else "TIE"
        print(f"  {h:>3}d — Paper Sharpe: {ps.get('sharpe')}, LAS Sharpe: {ls.get('sharpe')} → Winner: {winner}")

    # Save results
    results = {
        "paper_ic": p_ic.to_dict("records"),
        "las_ic": las_ic.to_dict("records"),
        "paper_simulations": {str(k): v for k, v in p_sims.items()},
        "las_simulations": {str(k): {kk: vv for kk, vv in v.items() if kk != "equity_curve"} for k, v in las_sims.items()},
        "paper_hit_rates": p_hits.to_dict("records"),
        "las_hit_rates": las_hits.to_dict("records"),
        "paper_signal_dist": df_paper["paper_signal"].value_counts().to_dict(),
        "las_signal_dist": df_las["signal"].value_counts().to_dict(),
    }

    with open(os.path.join(output_dir, "comparison_summary.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    sim_df.to_csv(os.path.join(output_dir, "portfolio_comparison.csv"), index=False)

    print(f"\nResults saved to {output_dir}/")
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="LazyPrices Paper vs LAS comparison")
    parser.add_argument(
        "--output", default=None,
        help="Output directory for comparison results (default: data/backtest_comparison/)",
    )
    args = parser.parse_args()
    run_comparison(output_dir=args.output)


if __name__ == "__main__":
    main()

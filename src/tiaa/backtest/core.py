"""
Backtesting and validation framework for LAS and signals.

Measures whether LAS and signal classifications predict real-world
forward stock returns.  Forward returns are computed starting AFTER the
CAR event window ends (day +6) to avoid circularity, since CAR is an
input to the LAS formula.

Usage:
    python backtest.py --output results/
"""

import argparse
import contextlib
import io
import json
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

from tiaa import config
from tiaa.analysis.signals import compute_signal, _compute_z_scores_for_group, _z_confidence
from tiaa.storage.store import LASStore


FORWARD_HORIZONS = [30, 60, 90, 180]

_SIGNAL_DIRECTION = {
    "sell": -1,
    "caution": -1,
    "hold": 0,
    "neutral": 0,
    "buy": 1,
}


# ---------------------------------------------------------------------------
# Forward return computation
# ---------------------------------------------------------------------------

def _fetch_prices(ticker: str, start: str, end: str, max_retries: int = 3) -> pd.Series:
    """Fetch adjusted close prices from Yahoo Finance with retry on transient failure."""
    import time as _time
    for attempt in range(max_retries):
        with contextlib.redirect_stderr(io.StringIO()):
            data = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if not data.empty:
            break
        if attempt < max_retries - 1:
            _time.sleep(1.5 * (attempt + 1))
    if data.empty:
        return pd.Series(dtype=float)
    close = data["Close"].squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = close.index.tz_localize(None) if close.index.tz else close.index
    return close


def compute_forward_returns(
    ticker: str,
    filed_date: str,
    horizons: list[int] | None = None,
    market_ticker: str | None = None,
) -> dict:
    """
    Compute market-adjusted forward returns starting after the CAR event
    window for multiple horizons.

    Returns dict mapping horizon (int) -> forward abnormal return (float | None).
    """
    horizons = horizons or FORWARD_HORIZONS
    market_ticker = market_ticker or config.MARKET_TICKER
    car_end_offset = config.CAR_WINDOW[1]
    start_offset = car_end_offset + 1

    dt = datetime.strptime(filed_date, "%Y-%m-%d")
    fetch_start = (dt - timedelta(days=10)).strftime("%Y-%m-%d")
    max_horizon = max(horizons)
    fetch_end = (dt + timedelta(days=int(max_horizon * 1.8) + 30)).strftime("%Y-%m-%d")

    stock_close = _fetch_prices(ticker, fetch_start, fetch_end)
    market_close = _fetch_prices(market_ticker, fetch_start, fetch_end)

    if stock_close.empty or market_close.empty:
        return {h: None for h in horizons}

    common = stock_close.index.intersection(market_close.index)
    stock_close = stock_close.loc[common]
    market_close = market_close.loc[common]

    filed_dt = pd.Timestamp(filed_date)
    idx_after = common[common >= filed_dt]
    if idx_after.empty:
        return {h: None for h in horizons}
    event_loc = common.get_loc(idx_after[0])

    base_loc = min(event_loc + start_offset, len(common) - 1)

    results = {}
    for h in horizons:
        end_loc = event_loc + h
        if end_loc >= len(common) or base_loc >= len(common):
            results[h] = None
            continue
        stock_ret = (stock_close.iloc[end_loc] / stock_close.iloc[base_loc]) - 1
        market_ret = (market_close.iloc[end_loc] / market_close.iloc[base_loc]) - 1
        results[h] = round(float(stock_ret - market_ret), 6)
    return results


# ---------------------------------------------------------------------------
# Load and prepare backtest universe
# ---------------------------------------------------------------------------

def load_backtest_data(db: LASStore | None = None) -> pd.DataFrame:
    """Load all scored filings and attach forward returns.

    Respects config.UNIVERSE_MODE — only loads filings for tickers in the
    active universe (50 demo tickers or full 500 S&P).
    """
    own_db = db is None
    if own_db:
        db = LASStore()
    try:
        df = db.get_all_filings()
    finally:
        if own_db:
            db.close()

    universe_tickers = set(config.CIK_TO_TICKER.values())
    df = df[df["ticker"].isin(universe_tickers)]

    required = ["ticker", "filed_date", "las", "change_intensity", "attention_proxy", "car"]
    df = df.dropna(subset=required)

    if df.empty:
        return df

    for col in ["las", "change_intensity", "attention_proxy", "car",
                 "norm_change", "norm_attention", "norm_car"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def enrich_with_forward_returns(
    df: pd.DataFrame,
    horizons: list[int] | None = None,
    cache_path: str | None = None,
) -> pd.DataFrame:
    """
    Fetch forward returns for every filing row.  Results are cached to a
    CSV so repeated runs don't re-download from Yahoo Finance.
    """
    horizons = horizons or FORWARD_HORIZONS
    cache_path = cache_path or os.path.join(config.DATA_DIR, "forward_returns_cache.csv")

    fwd_cols = [f"fwd_{h}d" for h in horizons]

    if os.path.exists(cache_path):
        cached = pd.read_csv(cache_path)
        if set(fwd_cols).issubset(cached.columns) and "accession" in cached.columns:
            cached["accession"] = cached["accession"].astype(str)
            df["accession"] = df["accession"].astype(str)
            merged = df.merge(
                cached[["accession"] + fwd_cols],
                on="accession",
                how="left",
                suffixes=("", "_cached"),
            )
            missing = merged[fwd_cols[0]].isna()
            if not missing.any():
                return merged

    results = []
    total = len(df)
    for i, (_, row) in enumerate(df.iterrows()):
        ticker = row["ticker"]
        filed = row["filed_date"]
        print(f"  [{i+1}/{total}] Fetching forward returns for {ticker} ({filed})")
        fwd = compute_forward_returns(ticker, filed, horizons)
        entry = {"accession": row["accession"]}
        for h in horizons:
            entry[f"fwd_{h}d"] = fwd.get(h)
        results.append(entry)

    fwd_df = pd.DataFrame(results)

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    fwd_df.to_csv(cache_path, index=False)

    df = df.merge(fwd_df, on="accession", how="left")
    return df


# ---------------------------------------------------------------------------
# Assign historical signals to each filing
# ---------------------------------------------------------------------------

def assign_signals(df: pd.DataFrame, risk_tolerance: str = "moderate") -> pd.DataFrame:
    """Replay signal classification for every filing in the DataFrame."""
    holdings = df.to_dict("records")
    z_scores = _compute_z_scores_for_group(holdings)

    signals = []
    for h in holdings:
        ticker = h.get("ticker", "")
        conf = _z_confidence(z_scores, ticker)
        sig = compute_signal(h, conf, risk_tolerance)
        signals.append(sig["signal"])

    df = df.copy()
    df["signal"] = signals
    return df


# ---------------------------------------------------------------------------
# Validation metrics
# ---------------------------------------------------------------------------

def compute_ic(df: pd.DataFrame, horizons: list[int] | None = None) -> pd.DataFrame:
    """
    Cross-sectional Information Coefficient: Spearman rank correlation
    between LAS and forward returns, grouped by filing year.
    """
    horizons = horizons or FORWARD_HORIZONS
    df = df.copy()
    df["year"] = pd.to_datetime(df["filed_date"]).dt.year

    rows = []
    for h in horizons:
        col = f"fwd_{h}d"
        if col not in df.columns:
            continue
        sub = df.dropna(subset=[col, "las"])
        if len(sub) < 5:
            rows.append({"horizon": h, "ic_mean": None, "ic_std": None,
                         "t_stat": None, "p_value": None, "n": len(sub)})
            continue

        yearly_ics = []
        for _, grp in sub.groupby("year"):
            if len(grp) < 3:
                continue
            rho, _ = stats.spearmanr(grp["las"], grp[col])
            if not np.isnan(rho):
                yearly_ics.append(rho)

        if not yearly_ics:
            pooled_rho, pooled_p = stats.spearmanr(sub["las"], sub[col])
            rows.append({
                "horizon": h,
                "ic_mean": round(pooled_rho, 4) if not np.isnan(pooled_rho) else None,
                "ic_std": None,
                "t_stat": None,
                "p_value": round(pooled_p, 4) if not np.isnan(pooled_p) else None,
                "n": len(sub),
            })
            continue

        ic_arr = np.array(yearly_ics)
        ic_mean = float(ic_arr.mean())
        ic_std = float(ic_arr.std(ddof=1)) if len(ic_arr) > 1 else 0.0
        if ic_std > 0 and len(ic_arr) > 1:
            t = ic_mean / (ic_std / np.sqrt(len(ic_arr)))
            p = 2 * (1 - stats.t.cdf(abs(t), df=len(ic_arr) - 1))
        else:
            t, p = None, None

        rows.append({
            "horizon": h,
            "ic_mean": round(ic_mean, 4),
            "ic_std": round(ic_std, 4),
            "t_stat": round(t, 3) if t is not None else None,
            "p_value": round(p, 4) if p is not None else None,
            "n": len(sub),
        })

    return pd.DataFrame(rows)


def compute_component_ic(
    df: pd.DataFrame,
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    """IC for each LAS component individually plus an ex-CAR LAS variant."""
    horizons = horizons or FORWARD_HORIZONS
    df = df.copy()

    df["las_ex_car"] = (
        0.67 * df["norm_change"].rank(pct=True)
        - 0.33 * df["norm_attention"].rank(pct=True)
    )

    factors = {
        "change_intensity": "change_intensity",
        "attention_proxy": "attention_proxy",
        "car": "car",
        "las": "las",
        "las_ex_car": "las_ex_car",
    }

    rows = []
    for h in horizons:
        col = f"fwd_{h}d"
        if col not in df.columns:
            continue
        sub = df.dropna(subset=[col])
        for name, fcol in factors.items():
            valid = sub.dropna(subset=[fcol])
            if len(valid) < 5:
                rows.append({"factor": name, "horizon": h, "ic": None, "p_value": None, "n": 0})
                continue
            rho, p = stats.spearmanr(valid[fcol], valid[col])
            rows.append({
                "factor": name,
                "horizon": h,
                "ic": round(rho, 4) if not np.isnan(rho) else None,
                "p_value": round(p, 4) if not np.isnan(p) else None,
                "n": len(valid),
            })

    return pd.DataFrame(rows)


def quintile_analysis(
    df: pd.DataFrame,
    horizons: list[int] | None = None,
    n_bins: int = 5,
) -> pd.DataFrame:
    """
    Sort filings into LAS quintiles and compute mean forward return
    per bin at each horizon.
    """
    horizons = horizons or FORWARD_HORIZONS
    rows = []
    for h in horizons:
        col = f"fwd_{h}d"
        if col not in df.columns:
            continue
        sub = df.dropna(subset=[col, "las"]).copy()
        if len(sub) < n_bins:
            continue
        sub["quintile"] = pd.qcut(sub["las"], n_bins, labels=False, duplicates="drop") + 1
        for q, grp in sub.groupby("quintile"):
            rows.append({
                "horizon": h,
                "quintile": int(q),
                "mean_return": round(grp[col].mean(), 6),
                "median_return": round(grp[col].median(), 6),
                "count": len(grp),
                "std": round(grp[col].std(), 6) if len(grp) > 1 else None,
            })

    result = pd.DataFrame(rows)

    if not result.empty:
        spreads = []
        for h in horizons:
            h_data = result[result["horizon"] == h]
            if h_data.empty:
                continue
            q_max = h_data["quintile"].max()
            q_min = h_data["quintile"].min()
            top = h_data[h_data["quintile"] == q_max]["mean_return"].values
            bot = h_data[h_data["quintile"] == q_min]["mean_return"].values
            if len(top) and len(bot):
                spreads.append({
                    "horizon": h,
                    "quintile": "L/S",
                    "mean_return": round(top[0] - bot[0], 6),
                    "median_return": None,
                    "count": None,
                    "std": None,
                })
        if spreads:
            result = pd.concat([result, pd.DataFrame(spreads)], ignore_index=True)

    return result


def signal_hit_rate(
    df: pd.DataFrame,
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    """
    For each signal label, compute the fraction of times the predicted
    direction matched the realized forward return direction.
    """
    horizons = horizons or FORWARD_HORIZONS

    if "signal" not in df.columns:
        df = assign_signals(df)

    rows = []
    for h in horizons:
        col = f"fwd_{h}d"
        if col not in df.columns:
            continue
        sub = df.dropna(subset=[col, "signal"]).copy()
        for sig, grp in sub.groupby("signal"):
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
                "horizon": h,
                "signal": sig,
                "count": n,
                "hit_rate": round(correct / n, 4) if n > 0 else None,
                "mean_fwd_return": round(mean_ret, 6),
                "expected_direction": "negative" if expected_dir < 0 else (
                    "positive" if expected_dir > 0 else "flat"
                ),
            })

    return pd.DataFrame(rows)


def signal_confusion_matrix(
    df: pd.DataFrame,
    horizon: int = 90,
) -> pd.DataFrame:
    """
    Build a cross-tabulation of signal vs realised outcome bucket
    (negative / flat / positive) at the given horizon.
    """
    col = f"fwd_{horizon}d"
    if col not in df.columns:
        return pd.DataFrame()

    if "signal" not in df.columns:
        df = assign_signals(df)

    sub = df.dropna(subset=[col, "signal"]).copy()

    def _bucket(r):
        if r < -0.02:
            return "negative"
        if r > 0.02:
            return "positive"
        return "flat"

    sub["outcome"] = sub[col].apply(_bucket)
    ct = pd.crosstab(sub["signal"], sub["outcome"], margins=True)
    return ct


# ---------------------------------------------------------------------------
# Portfolio simulation
# ---------------------------------------------------------------------------

def portfolio_simulation(
    df: pd.DataFrame,
    horizon: int = 90,
) -> dict:
    """
    Simulate a simple long/short strategy based on signals.

    For each filing event, go long (buy signal), short (sell/caution),
    or skip (hold/neutral).  Returns summary statistics and an equity
    series.
    """
    col = f"fwd_{horizon}d"
    if col not in df.columns or "signal" not in df.columns:
        return {"error": "missing columns"}

    sub = df.dropna(subset=[col, "signal"]).copy()
    sub["trade_return"] = 0.0

    for idx, row in sub.iterrows():
        direction = _SIGNAL_DIRECTION.get(row["signal"], 0)
        sub.at[idx, "trade_return"] = direction * row[col]

    trades = sub[sub["trade_return"] != 0]
    if trades.empty:
        return {
            "horizon": horizon,
            "n_trades": 0,
            "mean_return": None,
            "sharpe": None,
            "hit_rate": None,
            "max_drawdown": None,
            "equity_curve": [],
        }

    sorted_trades = trades.sort_values("filed_date")
    equity = (1 + sorted_trades["trade_return"]).cumprod()
    peak = equity.cummax()
    drawdown = (equity - peak) / peak

    mean_ret = sorted_trades["trade_return"].mean()
    std_ret = sorted_trades["trade_return"].std()
    sharpe = (mean_ret / std_ret) * np.sqrt(252 / horizon) if std_ret > 0 else None

    wins = (sorted_trades["trade_return"] > 0).sum()

    curve = [
        {"date": str(row["filed_date"]), "equity": round(eq, 6)}
        for (_, row), eq in zip(sorted_trades.iterrows(), equity)
    ]

    return {
        "horizon": horizon,
        "n_trades": len(sorted_trades),
        "mean_return": round(mean_ret, 6),
        "total_return": round(float(equity.iloc[-1]) - 1, 6) if len(equity) else None,
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "hit_rate": round(wins / len(sorted_trades), 4),
        "max_drawdown": round(float(drawdown.min()), 6),
        "equity_curve": curve,
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_backtest(
    db: LASStore | None = None,
    horizons: list[int] | None = None,
    output_dir: str | None = None,
    risk_tolerance: str = "moderate",
) -> dict:
    """
    Run the full validation suite and return a results dict.
    Optionally writes CSV/JSON outputs to *output_dir*.
    """
    horizons = horizons or FORWARD_HORIZONS
    output_dir = output_dir or os.path.join(config.DATA_DIR, "backtest_results")

    print("=== LAS/Signal Backtest ===")
    print(f"Horizons: {horizons}")

    print("\n[1/6] Loading filings from DB...")
    df = load_backtest_data(db)
    print(f"  Loaded {len(df)} scored filings across {df['ticker'].nunique()} tickers")

    if df.empty:
        print("  No scored filings found. Run the pipeline first.")
        return {"error": "no data"}

    print("\n[2/6] Fetching forward returns (cached if available)...")
    df = enrich_with_forward_returns(df, horizons)

    print("\n[3/6] Assigning signals...")
    df = assign_signals(df, risk_tolerance)
    print(f"  Signal distribution:\n{df['signal'].value_counts().to_string()}")

    print("\n[4/6] Computing Information Coefficient...")
    ic_df = compute_ic(df, horizons)
    print(ic_df.to_string(index=False))

    print("\n[4b/6] Component-level IC...")
    comp_ic_df = compute_component_ic(df, horizons)
    print(comp_ic_df.to_string(index=False))

    print("\n[5/6] Quintile analysis...")
    quint_df = quintile_analysis(df, horizons)
    print(quint_df.to_string(index=False))

    print("\n[6/6] Signal hit rates...")
    hit_df = signal_hit_rate(df, horizons)
    print(hit_df.to_string(index=False))

    sim_results = {}
    for h in horizons:
        sim = portfolio_simulation(df, h)
        sim_results[h] = sim
        if sim.get("n_trades"):
            print(f"\n  Portfolio sim ({h}d): trades={sim['n_trades']}, "
                  f"mean={sim['mean_return']}, sharpe={sim['sharpe']}, "
                  f"hit={sim['hit_rate']}, max_dd={sim['max_drawdown']}")

    confusion = signal_confusion_matrix(df, horizon=90)

    os.makedirs(output_dir, exist_ok=True)
    df.to_csv(os.path.join(output_dir, "backtest_data.csv"), index=False)
    ic_df.to_csv(os.path.join(output_dir, "ic_results.csv"), index=False)
    comp_ic_df.to_csv(os.path.join(output_dir, "component_ic.csv"), index=False)
    quint_df.to_csv(os.path.join(output_dir, "quintile_results.csv"), index=False)
    hit_df.to_csv(os.path.join(output_dir, "signal_hit_rates.csv"), index=False)
    if not confusion.empty:
        confusion.to_csv(os.path.join(output_dir, "confusion_matrix.csv"))

    summary = {
        "n_filings": len(df),
        "n_tickers": int(df["ticker"].nunique()),
        "horizons": horizons,
        "ic": ic_df.to_dict("records"),
        "component_ic": comp_ic_df.to_dict("records"),
        "quintiles": quint_df.to_dict("records"),
        "signal_hit_rates": hit_df.to_dict("records"),
        "portfolio_simulations": {
            str(k): {kk: vv for kk, vv in v.items() if kk != "equity_curve"}
            for k, v in sim_results.items()
        },
        "signal_distribution": df["signal"].value_counts().to_dict(),
    }
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"\nResults written to {output_dir}/")
    return {
        "df": df,
        "ic": ic_df,
        "component_ic": comp_ic_df,
        "quintiles": quint_df,
        "hit_rates": hit_df,
        "simulations": sim_results,
        "confusion": confusion,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LAS/Signal backtest validation")
    parser.add_argument(
        "--output", default=None,
        help="Output directory for CSV/JSON results (default: data/backtest_results/)",
    )
    parser.add_argument(
        "--risk-tolerance", default="moderate",
        choices=["conservative", "moderate", "aggressive"],
    )
    args = parser.parse_args()
    run_backtest(output_dir=args.output, risk_tolerance=args.risk_tolerance)


if __name__ == "__main__":
    main()

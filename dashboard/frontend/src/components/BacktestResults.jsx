import React, { useState, useEffect, useMemo } from 'react';
import { fetchBacktestResults } from '../api';

const SIGNAL_COLORS = {
  sell: '#d63d5e',
  caution: '#b88b00',
  hold: '#3a6ccc',
  neutral: '#718096',
  buy: '#06a77d',
};

function IcBar({ value, maxAbs = 0.3 }) {
  if (value == null) return <span className="bt-na">N/A</span>;
  const pct = Math.min(Math.abs(value) / maxAbs, 1) * 100;
  const color = value > 0 ? '#06a77d' : '#d63d5e';
  return (
    <div className="bt-bar-wrap">
      <div
        className="bt-bar"
        style={{ width: `${pct}%`, background: color }}
      />
      <span className="bt-bar-label">{value > 0 ? '+' : ''}{value.toFixed(4)}</span>
    </div>
  );
}

function BacktestResults() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(false);

  const load = (force = false) => {
    setLoading(true);
    setError(null);
    fetchBacktestResults(force)
      .then(d => {
        if (d.error) {
          setError(d.error);
          setData(null);
        } else {
          setData(d);
        }
      })
      .catch(e => setError(e.message || 'Failed to load backtest results'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const horizons = useMemo(() => {
    if (!data?.ic) return [];
    return [...new Set(data.ic.map(r => r.horizon))].sort((a, b) => a - b);
  }, [data]);

  const quintilesByHorizon = useMemo(() => {
    if (!data?.quintiles) return {};
    const m = {};
    data.quintiles.forEach(r => {
      if (!m[r.horizon]) m[r.horizon] = [];
      m[r.horizon].push(r);
    });
    return m;
  }, [data]);

  const hitsByHorizon = useMemo(() => {
    if (!data?.signal_hit_rates) return {};
    const m = {};
    data.signal_hit_rates.forEach(r => {
      if (!m[r.horizon]) m[r.horizon] = {};
      m[r.horizon][r.signal] = r;
    });
    return m;
  }, [data]);

  if (loading) {
    return (
      <div className="card bt-card">
        <h3 className="card-title">Model Validation</h3>
        <p className="bt-loading">Loading backtest results...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card bt-card">
        <h3 className="card-title">Model Validation</h3>
        <p className="bt-error">{error}</p>
        <button className="bt-btn" onClick={() => load(true)}>Retry</button>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="card bt-card">
      <div className="bt-header">
        <h3 className="card-title">Model Validation</h3>
        <div className="bt-header-right">
          <span className="bt-meta">
            {data.n_filings} filings / {data.n_tickers} tickers
          </span>
          <button
            className="bt-toggle"
            onClick={() => setExpanded(e => !e)}
          >
            {expanded ? 'Collapse' : 'Show Details'}
          </button>
          <button className="bt-btn-sm" onClick={() => load(true)} title="Refresh">
            &#x21bb;
          </button>
        </div>
      </div>

      {/* Always-visible: IC summary row */}
      <div className="bt-section">
        <h4 className="bt-section-title">Information Coefficient (LAS vs Forward Returns)</h4>
        <table className="bt-table">
          <thead>
            <tr>
              <th>Horizon</th>
              <th>Mean IC</th>
              <th>p-value</th>
              <th>n</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {data.ic.map(row => (
              <tr key={row.horizon}>
                <td>{row.horizon}d</td>
                <td><IcBar value={row.ic_mean} /></td>
                <td>{row.p_value != null ? row.p_value.toFixed(4) : '—'}</td>
                <td>{row.n}</td>
                <td>
                  {row.p_value != null && row.p_value < 0.05 ? '✓ sig' :
                   row.p_value != null && row.p_value < 0.10 ? '~ marginal' : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {expanded && (
        <>
          {/* Signal Hit Rates */}
          <div className="bt-section">
            <h4 className="bt-section-title">Signal Hit Rates</h4>
            {horizons.map(h => {
              const signals = hitsByHorizon[h];
              if (!signals) return null;
              return (
                <div key={h} className="bt-subsection">
                  <h5 className="bt-sub-title">{h}-day horizon</h5>
                  <div className="bt-signal-grid">
                    {['sell', 'caution', 'hold', 'neutral', 'buy'].map(sig => {
                      const r = signals[sig];
                      if (!r) return null;
                      return (
                        <div className="bt-signal-card" key={sig}>
                          <span className="bt-signal-label" style={{ color: SIGNAL_COLORS[sig] }}>
                            {sig.toUpperCase()}
                          </span>
                          <span className="bt-hit-rate">
                            {r.hit_rate != null ? `${(r.hit_rate * 100).toFixed(0)}%` : '—'}
                          </span>
                          <span className="bt-detail">
                            n={r.count}, ret={r.mean_fwd_return != null ? `${(r.mean_fwd_return * 100).toFixed(1)}%` : '—'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Quintile Spreads */}
          <div className="bt-section">
            <h4 className="bt-section-title">Quintile Spread (LAS sorted)</h4>
            {horizons.map(h => {
              const rows = quintilesByHorizon[h];
              if (!rows) return null;
              return (
                <div key={h} className="bt-subsection">
                  <h5 className="bt-sub-title">{h}-day horizon</h5>
                  <table className="bt-table bt-table-sm">
                    <thead>
                      <tr>
                        <th>Quintile</th>
                        <th>Mean Return</th>
                        <th>Count</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(r => (
                        <tr key={r.quintile} className={r.quintile === 'L/S' ? 'bt-row-highlight' : ''}>
                          <td>{r.quintile === 'L/S' ? 'Long/Short' : `Q${r.quintile}`}</td>
                          <td style={{ color: r.mean_return > 0 ? '#06a77d' : r.mean_return < 0 ? '#d63d5e' : 'inherit' }}>
                            {r.mean_return != null ? `${(r.mean_return * 100).toFixed(2)}%` : '—'}
                          </td>
                          <td>{r.count ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })}
          </div>

          {/* Portfolio Simulation */}
          <div className="bt-section">
            <h4 className="bt-section-title">Portfolio Simulation</h4>
            <table className="bt-table">
              <thead>
                <tr>
                  <th>Horizon</th>
                  <th>Trades</th>
                  <th>Total Return</th>
                  <th>Sharpe</th>
                  <th>Hit Rate</th>
                  <th>Max DD</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(data.portfolio_simulations || {}).map(([h, sim]) => (
                  <tr key={h}>
                    <td>{h}d</td>
                    <td>{sim.n_trades ?? 0}</td>
                    <td style={{ color: (sim.total_return || 0) > 0 ? '#06a77d' : '#d63d5e' }}>
                      {sim.total_return != null ? `${(sim.total_return * 100).toFixed(2)}%` : 'N/A'}
                    </td>
                    <td>{sim.sharpe ?? 'N/A'}</td>
                    <td>{sim.hit_rate != null ? `${(sim.hit_rate * 100).toFixed(0)}%` : 'N/A'}</td>
                    <td style={{ color: '#d63d5e' }}>
                      {sim.max_drawdown != null ? `${(sim.max_drawdown * 100).toFixed(1)}%` : 'N/A'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Component IC */}
          <div className="bt-section">
            <h4 className="bt-section-title">Component Attribution (IC per Factor)</h4>
            <table className="bt-table bt-table-sm">
              <thead>
                <tr>
                  <th>Factor</th>
                  {horizons.map(h => <th key={h}>{h}d</th>)}
                </tr>
              </thead>
              <tbody>
                {['change_intensity', 'attention_proxy', 'car', 'las', 'las_ex_car'].map(factor => (
                  <tr key={factor}>
                    <td className="bt-factor-name">{factor}</td>
                    {horizons.map(h => {
                      const match = (data.component_ic || []).find(
                        r => r.factor === factor && r.horizon === h
                      );
                      const ic = match?.ic;
                      return (
                        <td key={h}>
                          <IcBar value={ic} />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="bt-disclaimer">
            Results are based on historical filings of DJIA constituents (~120-150 observations).
            Small sample size limits statistical confidence.
            Not investment advice.
          </div>
        </>
      )}
    </div>
  );
}

export default BacktestResults;

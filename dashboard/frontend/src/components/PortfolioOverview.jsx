import React, { useState, useRef, useCallback } from 'react';
import { runPipeline, getPipelineStatus } from '../api';

const W_CHANGE = 0.50;
const W_ATTENTION = 0.25;
const W_CAR = 0.25;

function fmt(val, decimals = 4) {
  if (val == null || isNaN(val)) return 'N/A';
  return Number(val).toFixed(decimals);
}

function lasClass(val) {
  if (val == null) return 'neutral';
  if (val >= 0.5) return 'positive';
  if (val >= 0.25) return 'neutral';
  return 'negative';
}

function badgeClass(las) {
  if (las == null) return 'badge-na';
  if (las >= 0.5) return 'badge-high';
  if (las >= 0.25) return 'badge-medium';
  return 'badge-low';
}

const SIGNAL_CONFIG = {
  sell:    { label: 'SELL',    cls: 'signal-sell',    tip: 'Large disclosure changes with low investor attention — risk of negative drift.' },
  caution: { label: 'CAUTION', cls: 'signal-caution', tip: 'Material changes detected with negative market reaction — reassess position.' },
  hold:   { label: 'HOLD',    cls: 'signal-hold',    tip: 'Disclosure impact appears priced in — no action needed.' },
  neutral: { label: 'NEUTRAL', cls: 'signal-neutral', tip: 'No strong signal — maintain current position.' },
  buy:    { label: 'BUY',     cls: 'signal-buy',     tip: 'Stable filings with no negative signal or underreaction opportunity.' },
};

function SignalBadge({ signal, confidence, confidenceLevel, reasons }) {
  const cfg = SIGNAL_CONFIG[signal] || SIGNAL_CONFIG.neutral;
  const solidClass = confidenceLevel === 'strong' ? 'signal-strong' : '';
  const lines = reasons?.length ? reasons : [cfg.tip];
  const tip = lines.join('\n') + `\nConfidence: ${(confidence ?? 0).toFixed(2)} (${confidenceLevel || 'weak'})`;

  return (
    <span className="col-tip tip-right" data-tip={tip}>
      <span className={`signal-badge ${cfg.cls} ${solidClass}`}>
        {cfg.label}
      </span>
    </span>
  );
}

const POLL_INTERVAL = 3000;

function PortfolioOverview({ portfolio, filings, onRefresh }) {
  const [processing, setProcessing] = useState({});
  const [errors, setErrors] = useState({});
  const pollTimers = useRef({});

  const missingTickers = (portfolio?.holdings || [])
    .filter(h => h.las == null)
    .map(h => h.ticker);

  const pollJob = useCallback((jobId, tickerKeys) => {
    const poll = () => {
      getPipelineStatus(jobId)
        .then(status => {
          if (status.status === 'completed') {
            clearInterval(pollTimers.current[jobId]);
            delete pollTimers.current[jobId];
            setProcessing(prev => {
              const next = { ...prev };
              tickerKeys.forEach(t => delete next[t]);
              return next;
            });
            if (onRefresh) onRefresh();
          } else if (status.status === 'failed') {
            clearInterval(pollTimers.current[jobId]);
            delete pollTimers.current[jobId];
            setProcessing(prev => {
              const next = { ...prev };
              tickerKeys.forEach(t => delete next[t]);
              return next;
            });
            setErrors(prev => {
              const next = { ...prev };
              tickerKeys.forEach(t => { next[t] = status.error || 'Processing failed'; });
              return next;
            });
          }
        })
        .catch(() => {});
    };
    pollTimers.current[jobId] = setInterval(poll, POLL_INTERVAL);
  }, [onRefresh]);

  const handleProcess = useCallback((tickers) => {
    const tickerList = Array.isArray(tickers) ? tickers : [tickers];
    setErrors(prev => {
      const next = { ...prev };
      tickerList.forEach(t => delete next[t]);
      return next;
    });
    setProcessing(prev => {
      const next = { ...prev };
      tickerList.forEach(t => { next[t] = true; });
      return next;
    });

    runPipeline(tickerList)
      .then(data => {
        pollJob(data.job_id, tickerList);
      })
      .catch(err => {
        setProcessing(prev => {
          const next = { ...prev };
          tickerList.forEach(t => delete next[t]);
          return next;
        });
        const msg = err.response?.data?.error || 'Failed to start pipeline';
        setErrors(prev => {
          const next = { ...prev };
          tickerList.forEach(t => { next[t] = msg; });
          return next;
        });
      });
  }, [pollJob]);

  if (!portfolio) return null;

  const scored = (portfolio.holdings || []).filter(h => h.las != null);
  const avgChange = scored.length
    ? scored.reduce((s, h) => s + (h.change_intensity || 0), 0) / scored.length
    : null;
  const avgCar = scored.length
    ? scored.reduce((s, h) => s + (h.car || 0), 0) / scored.length
    : null;

  const anyProcessing = Object.keys(processing).length > 0;

  return (
    <>
      <div className="kpi-row">
        <div className="kpi-card">
          <div className="kpi-label">Portfolio LAS</div>
          <div className={`kpi-value ${lasClass(portfolio.portfolio_las)}`}>
            {fmt(portfolio.portfolio_las)}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Avg Change Intensity</div>
          <div className={`kpi-value ${avgChange > 0.01 ? 'negative' : 'positive'}`}>
            {fmt(avgChange)}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Avg CAR</div>
          <div className={`kpi-value ${avgCar >= 0 ? 'positive' : 'negative'}`}>
            {fmt(avgCar)}
          </div>
        </div>
      </div>

      <div className="card holdings-card">
        <div className="holdings-header">
          <h3>Holdings by LAS</h3>
          {missingTickers.length > 1 && (
            <button
              className="process-all-btn"
              onClick={() => handleProcess(missingTickers)}
              disabled={anyProcessing}
            >
              {anyProcessing ? 'Processing...' : `Process All Missing (${missingTickers.length})`}
            </button>
          )}
        </div>
        <table className="holdings-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Company</th>
              <th className="ht-num">
                <span className="col-tip" data-tip="Weighted contribution from year-over-year 10-K language changes. Positive means large disclosure changes increase the LAS score. Weight: 50%">
                  Change
                </span>
              </th>
              <th className="ht-num">
                <span className="col-tip" data-tip="Weighted contribution from abnormal trading volume around the filing date. Negative because high investor attention lowers the LAS score (lazy prices = inattention). Weight: -25%">
                  Attention
                </span>
              </th>
              <th className="ht-num">
                <span className="col-tip" data-tip={"Weighted contribution from cumulative abnormal return (stock vs S&P 500) around the filing date. Positive means a larger market reaction increases the LAS score. Weight: 25%"}>
                  CAR
                </span>
              </th>
              <th className="ht-num">
                <span className="col-tip" data-tip="Lazy Attention Score = Change - Attention + CAR. Higher means more material changes with less investor attention. Green ≥ 0.50, Yellow ≥ 0.25, Red < 0.25">
                  LAS
                </span>
              </th>
              <th className="ht-num">
                <span className="col-tip" data-tip="Buy/sell signal derived from LAS components. Based on filing change analysis — not investment advice.">
                  Signal
                </span>
              </th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {(portfolio.holdings || []).map((h, i) => {
              const hasBreakdown = h.las != null && h.norm_change != null;
              const changeC = hasBreakdown ? W_CHANGE * Number(h.norm_change) : null;
              const attnC = hasBreakdown ? -(W_ATTENTION * Number(h.norm_attention || 0)) : null;
              const carC = hasBreakdown ? W_CAR * Number(h.norm_car || 0) : null;

              return (
                <tr key={i}>
                  <td className="ht-ticker">{h.ticker}</td>
                  <td className="ht-name">{h.entity_name || ''}</td>
                  <td className="ht-num">
                    {changeC != null ? (
                      <span className="col-tip" data-tip={`+${changeC.toFixed(3)} added to LAS. Higher = more filing language changed year-over-year.`}>
                        +{changeC.toFixed(3)}
                      </span>
                    ) : '\u2014'}
                  </td>
                  <td className="ht-num">
                    {attnC != null ? (
                      <span className="col-tip" data-tip={`${attnC.toFixed(3)} subtracted from LAS. More negative = investors paid more attention (reduces mispricing opportunity).`}>
                        {attnC.toFixed(3)}
                      </span>
                    ) : '\u2014'}
                  </td>
                  <td className="ht-num">
                    {carC != null ? (
                      <span className="col-tip" data-tip={`+${carC.toFixed(3)} added to LAS. Higher = larger abnormal market reaction around the filing.`}>
                        +{carC.toFixed(3)}
                      </span>
                    ) : '\u2014'}
                  </td>
                  <td className="ht-num">
                    {h.las != null ? (
                      <span className="col-tip" data-tip={h.las >= 0.5
                        ? 'High LAS: Large disclosure changes + low investor attention. Potential mispricing opportunity.'
                        : h.las >= 0.25
                          ? 'Moderate LAS: Some notable changes. Worth monitoring for potential mispricing.'
                          : 'Low LAS: Minor changes or high investor attention. Market likely priced in.'}>
                        <span className={`holding-badge ${badgeClass(h.las)}`}>
                          {fmt(h.las)}
                        </span>
                      </span>
                    ) : '\u2014'}
                  </td>
                  <td className="ht-num">
                    {h.signal ? (
                      <SignalBadge
                        signal={h.signal}
                        confidence={h.signal_confidence}
                        confidenceLevel={h.signal_confidence_level}
                        reasons={h.signal_reasons}
                      />
                    ) : '\u2014'}
                  </td>
                  <td>
                    {h.las == null && (
                      <span className="holding-actions">
                        {errors[h.ticker] && (
                          <span className="holding-error" title={errors[h.ticker]}>Error</span>
                        )}
                        {processing[h.ticker] ? (
                          <span className="holding-badge holding-processing">Processing...</span>
                        ) : (
                          <button
                            className="holding-process-btn"
                            onClick={() => handleProcess(h.ticker)}
                            disabled={anyProcessing}
                          >
                            Process
                          </button>
                        )}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="signal-disclaimer">
          Signals are derived from SEC 10-K filing change analysis and are not investment advice.
          Always conduct independent due diligence before making investment decisions.
        </div>
      </div>
    </>
  );
}

export default PortfolioOverview;

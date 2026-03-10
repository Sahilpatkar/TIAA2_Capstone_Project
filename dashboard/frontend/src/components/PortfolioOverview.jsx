import React, { useState, useRef, useCallback } from 'react';
import { runPipeline, getPipelineStatus } from '../api';

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
        {(portfolio.holdings || []).map((h, i) => (
          <div className="holding-row" key={i}>
            <span className="holding-ticker">{h.ticker}</span>
            <span className="holding-name">{h.entity_name || ''}</span>
            {h.las != null ? (
              <span className={`holding-badge ${badgeClass(h.las)}`}>
                {fmt(h.las)}
              </span>
            ) : (
              <span className="holding-actions">
                {errors[h.ticker] && (
                  <span className="holding-error" title={errors[h.ticker]}>Error</span>
                )}
                {processing[h.ticker] ? (
                  <span className="holding-badge holding-processing">Processing...</span>
                ) : (
                  <>
                    <span className="holding-badge badge-na">Not processed</span>
                    <button
                      className="holding-process-btn"
                      onClick={() => handleProcess(h.ticker)}
                      disabled={anyProcessing}
                    >
                      Process
                    </button>
                  </>
                )}
              </span>
            )}
          </div>
        ))}
      </div>
    </>
  );
}

export default PortfolioOverview;

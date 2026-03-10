import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { fetchRiskNarrative } from '../api';

function fmt(val) {
  if (val == null || isNaN(val)) return '—';
  return Number(val).toFixed(4);
}

function prettySection(key) {
  return (key || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

const TOP_N = 5;

function RiskInsights({ sections, tickers }) {
  const [narrative, setNarrative] = useState(null);
  const [isTemplate, setIsTemplate] = useState(false);
  const [loadingNarrative, setLoadingNarrative] = useState(false);

  useEffect(() => {
    if (!tickers || tickers.length === 0) return;
    setNarrative(null);
    setLoadingNarrative(true);

    fetchRiskNarrative(tickers)
      .then(data => {
        setNarrative(data.narrative);
        setIsTemplate(data.is_template);
      })
      .catch(() => setNarrative(null))
      .finally(() => setLoadingNarrative(false));
  }, [tickers]);

  if (!sections || sections.length === 0) return null;

  const topSections = sections.slice(0, TOP_N);
  const maxCi = Math.max(...topSections.map(s => s.change_intensity || 0), 0.01);

  return (
    <div className="card risk-insights-card">
      <h3>Key Risk Insights</h3>

      <div className="risk-bullets">
        {topSections.map((s, i) => {
          const barWidth = ((s.change_intensity || 0) / maxCi) * 100;
          return (
            <div className="risk-bullet" key={i}>
              <span className="risk-bullet-ticker">{s.ticker}</span>
              <span className="risk-bullet-section">{prettySection(s.section)}</span>
              <div className="risk-bullet-bar-wrap">
                <div className="risk-bullet-bar" style={{ width: `${barWidth}%` }} />
              </div>
              <span className="risk-bullet-ci">{fmt(s.change_intensity)}</span>
            </div>
          );
        })}
      </div>

      <div className="risk-narrative-wrap">
        {loadingNarrative && (
          <div className="risk-narrative-loading">Generating risk insights...</div>
        )}
        {narrative && !loadingNarrative && (
          <div className="risk-narrative">
            {isTemplate && <span className="template-badge">Template</span>}
            <ReactMarkdown>{narrative}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}

export default RiskInsights;

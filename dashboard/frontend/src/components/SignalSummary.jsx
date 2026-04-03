import React from 'react';

const SIGNAL_ORDER = [
  { key: 'sell',    label: 'SELL',    color: '#d63d5e' },
  { key: 'caution', label: 'CAUTION', color: '#b88b00' },
  { key: 'hold',   label: 'HOLD',    color: '#3a6ccc' },
  { key: 'neutral', label: 'NEUTRAL', color: '#718096' },
  { key: 'buy',    label: 'BUY',     color: '#06a77d' },
];

function SignalSummary({ portfolio }) {
  const summary = portfolio?.signal_summary;
  if (!summary) return null;

  const total = Object.values(summary).reduce((a, b) => a + b, 0);
  if (total === 0) return null;

  const actionable = (summary.sell || 0) + (summary.caution || 0);
  const actionableText = actionable > 0
    ? `${actionable} holding${actionable > 1 ? 's' : ''} flagged for review due to material disclosure changes`
    : 'No holdings currently flagged for action';

  return (
    <div style={{ marginBottom: 16 }}>
      <div className="signal-summary-row">
        {SIGNAL_ORDER.map(({ key, label, color }) => {
          const count = summary[key] || 0;
          return (
            <div className="signal-summary-card" key={key}>
              <span className="signal-summary-count" style={{ color }}>
                {count}
              </span>
              <span className="signal-summary-label" style={{ color }}>
                {label}
              </span>
            </div>
          );
        })}
      </div>
      <div className="signal-disclaimer">
        {actionableText}
      </div>
    </div>
  );
}

export default SignalSummary;

import React, { useState } from 'react';

function fmt(val) {
  if (val == null || isNaN(val)) return '—';
  return Number(val).toFixed(4);
}

function prettySection(key) {
  return (key || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

function SectionChanges({ sections }) {
  const [expanded, setExpanded] = useState({});

  if (!sections || sections.length === 0) return null;

  const toggleExpand = (idx) => {
    setExpanded(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  const maxCi = Math.max(...sections.map(s => s.change_intensity || 0), 0.01);

  return (
    <div className="sections-card">
      <h3>Top Changed Sections</h3>
      {sections.map((s, i) => {
        const barWidth = ((s.change_intensity || 0) / maxCi) * 100;
        return (
          <div className="section-item" key={i}>
            <div className="section-header" onClick={() => toggleExpand(i)}>
              <div className="section-meta">
                <span className="section-ticker">{s.ticker}</span>
                <span className="section-name">{prettySection(s.section)}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div className="section-bar-wrap">
                  <div className="section-bar" style={{ width: `${barWidth}%` }} />
                </div>
                <span className="section-ci">{fmt(s.change_intensity)}</span>
                <span className="section-toggle">{expanded[i] ? '▾' : '▸'}</span>
              </div>
            </div>
            {expanded[i] && s.snippet && (
              <div className="section-body">{s.snippet}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default SectionChanges;

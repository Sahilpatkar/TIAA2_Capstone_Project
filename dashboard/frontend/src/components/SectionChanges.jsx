import React, { useState, useCallback, useRef } from 'react';
import { fetchSectionChangeSummary } from '../api';

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
  const [summaries, setSummaries] = useState({});
  const [loadingSummary, setLoadingSummary] = useState({});
  const summaryCache = useRef({});

  const toggleExpand = useCallback((idx, section) => {
    setExpanded(prev => {
      const opening = !prev[idx];
      if (opening && !summaryCache.current[idx] && section.snippet_old) {
        setLoadingSummary(ls => ({ ...ls, [idx]: true }));
        fetchSectionChangeSummary({
          ticker: section.ticker,
          section: section.section,
          snippet_old: section.snippet_old || '',
          snippet_new: section.snippet_new || section.snippet || '',
        })
          .then(data => {
            summaryCache.current[idx] = data;
            setSummaries(s => ({ ...s, [idx]: data }));
          })
          .catch(() => {
            const fallback = { summary: 'Unable to load summary.', is_template: true };
            summaryCache.current[idx] = fallback;
            setSummaries(s => ({ ...s, [idx]: fallback }));
          })
          .finally(() => setLoadingSummary(ls => ({ ...ls, [idx]: false })));
      }
      return { ...prev, [idx]: opening };
    });
  }, []);

  if (!sections || sections.length === 0) return null;

  const maxCi = Math.max(...sections.map(s => s.change_intensity || 0), 0.01);

  return (
    <div className="sections-card">
      <h3>Top Changed Sections</h3>
      {sections.map((s, i) => {
        const barWidth = ((s.change_intensity || 0) / maxCi) * 100;
        const isOpen = expanded[i];
        const hasOld = !!(s.snippet_old);
        const hasNew = !!(s.snippet_new || s.snippet);
        const summary = summaries[i] || summaryCache.current[i];

        return (
          <div className="section-item" key={i}>
            <div className="section-header" onClick={() => toggleExpand(i, s)}>
              <div className="section-meta">
                <span className="section-ticker">{s.ticker}</span>
                <span className="section-name">{prettySection(s.section)}</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div className="section-bar-wrap">
                  <div className="section-bar" style={{ width: `${barWidth}%` }} />
                </div>
                <span className="section-ci">{fmt(s.change_intensity)}</span>
                <span className="section-toggle">{isOpen ? '▾' : '▸'}</span>
              </div>
            </div>

            {isOpen && (
              <div className="section-expanded">
                {/* AI summary */}
                <div className="section-summary-wrap">
                  {loadingSummary[i] && (
                    <div className="section-summary-loading">Generating summary…</div>
                  )}
                  {summary && !loadingSummary[i] && (
                    <div className="section-summary">
                      <div>
                        {summary.sentiment && (
                          <span className={`sentiment-pill ${summary.sentiment}`}>
                            {summary.sentiment === 'unknown' ? 'Unscored' : summary.sentiment}
                          </span>
                        )}
                        {summary.is_template && <span className="template-badge">Template</span>}
                      </div>
                      <p>{summary.summary}</p>
                      {summary.sentiment_rationale && (
                        <div className="sentiment-rationale">{summary.sentiment_rationale}</div>
                      )}
                    </div>
                  )}
                  {!hasOld && !loadingSummary[i] && !summary && (
                    <div className="section-summary section-summary-unavailable">
                      Re-run the pipeline to capture prior-year text for comparison.
                    </div>
                  )}
                </div>

                {/* Side-by-side previews */}
                {(hasOld || hasNew) && (
                  <div className="section-diff-grid">
                    <div className="section-diff-pane">
                      <div className="section-diff-label">Prior Period</div>
                      <div className="section-diff-text">
                        {hasOld ? s.snippet_old : <span className="section-diff-na">Not available</span>}
                      </div>
                    </div>
                    <div className="section-diff-pane">
                      <div className="section-diff-label">Current Period</div>
                      <div className="section-diff-text">
                        {hasNew ? (s.snippet_new || s.snippet) : <span className="section-diff-na">Not available</span>}
                      </div>
                    </div>
                  </div>
                )}

                {/* Fallback: single snippet when no old/new split */}
                {!hasOld && !hasNew && s.snippet && (
                  <div className="section-body">{s.snippet}</div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default SectionChanges;

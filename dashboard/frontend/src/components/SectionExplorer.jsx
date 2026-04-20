import React, { useState, useEffect, useMemo } from 'react';
import { fetchFilings, fetchFilingSections, analyzeSection } from '../api';

function prettySection(key) {
  return (key || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

function SectionExplorer({ tickers }) {
  const [ticker, setTicker] = useState('');
  const [filings, setFilings] = useState([]);
  const [accession, setAccession] = useState('');
  const [sectionKeys, setSectionKeys] = useState([]);
  const [section, setSection] = useState('');
  const [loadingFilings, setLoadingFilings] = useState(false);
  const [loadingSections, setLoadingSections] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!ticker && tickers && tickers.length > 0) {
      setTicker(tickers[0]);
    }
  }, [tickers, ticker]);

  useEffect(() => {
    if (!ticker) return;
    setLoadingFilings(true);
    setFilings([]);
    setAccession('');
    setSectionKeys([]);
    setSection('');
    setResult(null);
    setError('');
    fetchFilings([ticker])
      .then(data => {
        const sorted = [...data].sort((a, b) =>
          String(b.report_date || '').localeCompare(String(a.report_date || ''))
        );
        setFilings(sorted);
        if (sorted.length > 0) {
          setAccession(sorted[0].accession);
        }
      })
      .catch(() => setError('Failed to load filings for ticker'))
      .finally(() => setLoadingFilings(false));
  }, [ticker]);

  const currentFiling = useMemo(
    () => filings.find(f => f.accession === accession),
    [filings, accession]
  );

  useEffect(() => {
    if (!currentFiling) return;
    setLoadingSections(true);
    setSectionKeys([]);
    setSection('');
    setResult(null);
    setError('');
    fetchFilingSections(currentFiling.cik, currentFiling.accession)
      .then(data => {
        const keys = Object.keys(data.sections || {}).filter(
          k => typeof data.sections[k] === 'string' && data.sections[k].trim()
        );
        setSectionKeys(keys);
        if (keys.length > 0) setSection(keys[0]);
      })
      .catch(() => setError('Failed to load section list for filing'))
      .finally(() => setLoadingSections(false));
  }, [currentFiling]);

  const handleAnalyze = () => {
    if (!ticker || !section || !accession) return;
    setAnalyzing(true);
    setError('');
    setResult(null);
    analyzeSection({ ticker, section, accession })
      .then(data => {
        if (data && data.error) {
          setError(data.error);
        } else {
          setResult(data);
        }
      })
      .catch(err => {
        const msg = err?.response?.data?.error || 'Analysis failed';
        setError(msg);
      })
      .finally(() => setAnalyzing(false));
  };

  const canAnalyze = ticker && accession && section && !analyzing;

  return (
    <div className="section-explorer">
      <h3>Section Explorer</h3>
      <p className="section-explorer-meta">
        Pick any ticker-section pair and get an AI summary with sentiment
        classification — not limited to the top-changed list above.
      </p>

      <div className="section-explorer-controls">
        <select
          value={ticker}
          onChange={e => setTicker(e.target.value)}
          disabled={!tickers || tickers.length === 0}
        >
          <option value="">Ticker…</option>
          {(tickers || []).map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>

        <select
          value={accession}
          onChange={e => setAccession(e.target.value)}
          disabled={loadingFilings || filings.length === 0}
        >
          <option value="">
            {loadingFilings ? 'Loading filings…' : 'Filing…'}
          </option>
          {filings.map(f => (
            <option key={f.accession} value={f.accession}>
              {(f.form || '10-K')} · {f.report_date || f.filed_date || f.accession}
            </option>
          ))}
        </select>

        <select
          value={section}
          onChange={e => setSection(e.target.value)}
          disabled={loadingSections || sectionKeys.length === 0}
        >
          <option value="">
            {loadingSections ? 'Loading sections…' : 'Section…'}
          </option>
          {sectionKeys.map(k => (
            <option key={k} value={k}>{prettySection(k)}</option>
          ))}
        </select>

        <button type="button" onClick={handleAnalyze} disabled={!canAnalyze}>
          {analyzing ? 'Analyzing…' : 'Analyze'}
        </button>
      </div>

      {error && <div className="section-explorer-error">{error}</div>}

      {result && (
        <div className="section-item" style={{ cursor: 'default' }}>
          <div className="section-expanded" style={{ display: 'block' }}>
            <div className="section-explorer-meta">
              Comparing <strong>{result.current?.form || ''} {result.current?.report_date}</strong>
              {' vs prior '}
              <strong>{result.prior?.form || ''} {result.prior?.report_date}</strong>
            </div>
            <div className="section-summary-wrap">
              <div className="section-summary">
                <div>
                  {result.sentiment && (
                    <span className={`sentiment-pill ${result.sentiment}`}>
                      {result.sentiment === 'unknown' ? 'Unscored' : result.sentiment}
                    </span>
                  )}
                  {result.is_template && <span className="template-badge">Template</span>}
                </div>
                <p>{result.summary}</p>
                {result.sentiment_rationale && (
                  <div className="sentiment-rationale">{result.sentiment_rationale}</div>
                )}
              </div>
            </div>

            <div className="section-diff-grid">
              <div className="section-diff-pane">
                <div className="section-diff-label">Prior Period</div>
                <div className="section-diff-text">
                  {result.snippet_old || <span className="section-diff-na">Not available</span>}
                </div>
              </div>
              <div className="section-diff-pane">
                <div className="section-diff-label">Current Period</div>
                <div className="section-diff-text">
                  {result.snippet_new || <span className="section-diff-na">Not available</span>}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SectionExplorer;

import React, { useState, useMemo } from 'react';

const COLUMNS = [
  { key: 'report_date',       label: 'Report Date' },
  { key: 'filed_date',        label: 'Filed Date' },
  { key: 'similarity_cosine', label: 'Cosine Sim', numeric: true },
  { key: 'similarity_jaccard',label: 'Jaccard Sim', numeric: true },
  { key: 'change_intensity',  label: 'Change Int.', numeric: true },
  { key: 'car',               label: 'CAR', numeric: true },
  { key: 'las',               label: 'LAS', numeric: true },
];

function fmt(val) {
  if (val == null || val === '' || isNaN(val)) return '\u2014';
  return Number(val).toFixed(4);
}

function lasBadgeClass(las) {
  if (las == null) return 'badge-na';
  if (las >= 0.5) return 'badge-high';
  if (las >= 0.25) return 'badge-medium';
  return 'badge-low';
}

function FilingsTable({ filings }) {
  const [latestOnly, setLatestOnly] = useState(true);
  const [expandedTickers, setExpandedTickers] = useState({});
  const [sortKey, setSortKey] = useState('report_date');
  const [sortAsc, setSortAsc] = useState(false);

  const unique = useMemo(() => {
    const seen = new Set();
    return filings.filter(f => {
      const key = `${f.ticker}-${f.report_date}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [filings]);

  const grouped = useMemo(() => {
    const groups = {};
    for (const f of unique) {
      const t = f.ticker || '?';
      if (!groups[t]) groups[t] = [];
      groups[t].push(f);
    }
    for (const t of Object.keys(groups)) {
      groups[t].sort((a, b) => (b.report_date || '').localeCompare(a.report_date || ''));
    }
    return groups;
  }, [unique]);

  const tickers = useMemo(() =>
    Object.keys(grouped).sort()
  , [grouped]);

  const sortRows = (rows) => {
    const arr = [...rows];
    arr.sort((a, b) => {
      let va = a[sortKey], vb = b[sortKey];
      if (va == null) va = '';
      if (vb == null) vb = '';
      const col = COLUMNS.find(c => c.key === sortKey);
      if (col?.numeric) {
        va = Number(va) || 0;
        vb = Number(vb) || 0;
      }
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });
    return arr;
  };

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const toggleTicker = (ticker) => {
    setExpandedTickers(prev => ({ ...prev, [ticker]: !prev[ticker] }));
  };

  if (!filings || filings.length === 0) return null;

  return (
    <div className="table-card">
      <div className="table-header-row">
        <h3>Filings</h3>
        <label className="toggle-label">
          <input
            type="checkbox"
            checked={latestOnly}
            onChange={() => setLatestOnly(!latestOnly)}
          />
          <span>Latest Only</span>
        </label>
      </div>

      {tickers.map(ticker => {
        const allRows = grouped[ticker];
        const latest = allRows[0];
        const isExpanded = !latestOnly && expandedTickers[ticker];
        const displayRows = latestOnly ? [latest] : (isExpanded ? sortRows(allRows) : [latest]);
        const hasHistory = allRows.length > 1;

        return (
          <div key={ticker} className="ticker-group">
            <div
              className={`ticker-group-header ${!latestOnly && hasHistory ? 'clickable' : ''}`}
              onClick={() => !latestOnly && hasHistory && toggleTicker(ticker)}
            >
              <div className="ticker-group-left">
                <span className="ticker-group-name">{ticker}</span>
                <span className="ticker-group-entity">{latest.entity_name || ''}</span>
              </div>
              <div className="ticker-group-right">
                <span className={`holding-badge ${lasBadgeClass(latest.las)}`}>
                  LAS {fmt(latest.las)}
                </span>
                {!latestOnly && hasHistory && (
                  <span className="ticker-group-count">
                    {allRows.length} filings {isExpanded ? '\u25B2' : '\u25BC'}
                  </span>
                )}
              </div>
            </div>

            <table className="filings-table">
              <thead>
                <tr>
                  {COLUMNS.map(col => (
                    <th key={col.key} onClick={() => handleSort(col.key)}>
                      {col.label}
                      {sortKey === col.key && (
                        <span className="sort-arrow">{sortAsc ? '\u25B2' : '\u25BC'}</span>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {displayRows.map((f, i) => (
                  <tr key={i}>
                    <td>{f.report_date || '\u2014'}</td>
                    <td>{f.filed_date || '\u2014'}</td>
                    <td>{fmt(f.similarity_cosine)}</td>
                    <td>{fmt(f.similarity_jaccard)}</td>
                    <td>{fmt(f.change_intensity)}</td>
                    <td style={{ color: f.car != null && f.car >= 0 ? '#06a77d' : f.car != null ? '#d63d5e' : 'inherit' }}>
                      {fmt(f.car)}
                    </td>
                    <td><strong>{fmt(f.las)}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}

export default FilingsTable;

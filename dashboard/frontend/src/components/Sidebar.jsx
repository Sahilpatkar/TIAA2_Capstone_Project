import React, { useState, useEffect, useMemo } from 'react';

const RISK_COLORS = {
  conservative: '#06d6a0',
  moderate: '#ffd166',
  aggressive: '#ef476f',
};

function Sidebar({
  tickerMeta,
  selected,
  onAnalyze,
  portfolioLas,
  clients,
  activeClient,
  onSelectClient,
  onNewClient,
  onEditClient,
}) {
  const tickers = useMemo(() => tickerMeta.map(t => t.ticker), [tickerMeta]);

  const sectorGroups = useMemo(() => {
    const groups = {};
    for (const item of tickerMeta) {
      const sector = item.sector || 'Other';
      if (!groups[sector]) groups[sector] = [];
      groups[sector].push(item.ticker);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [tickerMeta]);

  const [localSelected, setLocalSelected] = useState(selected);
  const [collapsedSectors, setCollapsedSectors] = useState({});

  useEffect(() => {
    if (activeClient) {
      setLocalSelected(activeClient.tickers || []);
    }
  }, [activeClient]);

  const toggle = (ticker) => {
    if (activeClient) {
      onSelectClient(null);
    }
    setLocalSelected(prev =>
      prev.includes(ticker) ? prev.filter(t => t !== ticker) : [...prev, ticker]
    );
  };

  const toggleSector = (sector, sectorTickers) => {
    if (activeClient) onSelectClient(null);
    const allSelected = sectorTickers.every(t => localSelected.includes(t));
    if (allSelected) {
      setLocalSelected(prev => prev.filter(t => !sectorTickers.includes(t)));
    } else {
      setLocalSelected(prev => [...new Set([...prev, ...sectorTickers])]);
    }
  };

  const toggleCollapse = (sector) => {
    setCollapsedSectors(prev => ({ ...prev, [sector]: !prev[sector] }));
  };

  const selectAll = () => {
    if (activeClient) onSelectClient(null);
    setLocalSelected([...tickers]);
  };
  const clearAll = () => {
    if (activeClient) onSelectClient(null);
    setLocalSelected([]);
  };

  const handleClientChange = (e) => {
    const val = e.target.value;
    if (val === '__custom__') {
      onSelectClient(null);
      return;
    }
    if (val === '__new__') {
      onNewClient();
      return;
    }
    const client = clients.find(c => c.id === Number(val));
    if (client) {
      onSelectClient(client);
      setLocalSelected(client.tickers || []);
    }
  };

  const presets = clients.filter(c => c.is_preset);
  const custom = clients.filter(c => !c.is_preset);

  return (
    <nav className="sidebar">
      <h2>LazyPrices</h2>
      <p className="brand-sub">Advisor Dashboard</p>

      <label>Client Profile</label>
      <div className="profile-selector-wrap">
        <select
          className="profile-select"
          value={activeClient ? activeClient.id : '__custom__'}
          onChange={handleClientChange}
        >
          <option value="__custom__">Custom Selection</option>
          {presets.length > 0 && (
            <optgroup label="Preset Profiles">
              {presets.map(c => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.risk_tolerance})
                </option>
              ))}
            </optgroup>
          )}
          {custom.length > 0 && (
            <optgroup label="My Clients">
              {custom.map(c => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.risk_tolerance})
                </option>
              ))}
            </optgroup>
          )}
          <option value="__new__">+ New Client...</option>
        </select>

        {activeClient && (
          <div className="profile-info">
            <span
              className="risk-badge"
              style={{ background: RISK_COLORS[activeClient.risk_tolerance] || '#718096' }}
            >
              {activeClient.risk_tolerance}
            </span>
            {activeClient.investment_goal && (
              <span className="goal-tag">{activeClient.investment_goal}</span>
            )}
            <button
              className="profile-edit-btn"
              onClick={() => onEditClient(activeClient)}
              title="Edit profile"
            >
              Edit
            </button>
          </div>
        )}
      </div>

      <label>Portfolio Tickers</label>

      <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
        <button
          onClick={selectAll}
          style={{
            fontSize: 11, background: 'rgba(255,255,255,0.1)', border: 'none',
            color: '#c1c7d0', padding: '4px 10px', borderRadius: 4, cursor: 'pointer'
          }}
        >
          All
        </button>
        <button
          onClick={clearAll}
          style={{
            fontSize: 11, background: 'rgba(255,255,255,0.1)', border: 'none',
            color: '#c1c7d0', padding: '4px 10px', borderRadius: 4, cursor: 'pointer'
          }}
        >
          Clear
        </button>
      </div>

      <div className="ticker-list">
        {sectorGroups.map(([sector, sectorTickers]) => {
          const collapsed = collapsedSectors[sector];
          const selectedCount = sectorTickers.filter(t => localSelected.includes(t)).length;
          const allSelected = selectedCount === sectorTickers.length;
          const someSelected = selectedCount > 0 && !allSelected;

          return (
            <div key={sector} className="sector-group">
              <div
                className="sector-header"
                onClick={() => toggleCollapse(sector)}
              >
                <span className="sector-arrow">{collapsed ? '\u25B6' : '\u25BC'}</span>
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={el => { if (el) el.indeterminate = someSelected; }}
                  onChange={() => toggleSector(sector, sectorTickers)}
                  onClick={e => e.stopPropagation()}
                />
                <span className="sector-name">{sector}</span>
                <span className="sector-count">{selectedCount}/{sectorTickers.length}</span>
              </div>
              {!collapsed && sectorTickers.map(ticker => (
                <div
                  key={ticker}
                  className={`ticker-item ${localSelected.includes(ticker) ? 'selected' : ''}`}
                  onClick={() => toggle(ticker)}
                >
                  <input
                    type="checkbox"
                    checked={localSelected.includes(ticker)}
                    onChange={() => toggle(ticker)}
                    onClick={e => e.stopPropagation()}
                  />
                  {ticker}
                </div>
              ))}
            </div>
          );
        })}
        {tickers.length === 0 && (
          <p style={{ fontSize: 12, color: '#718096', padding: 8 }}>
            No tickers in database. Run the pipeline first.
          </p>
        )}
      </div>

      <button
        className="sidebar-btn"
        disabled={localSelected.length === 0}
        onClick={() => onAnalyze(localSelected)}
      >
        Analyze ({localSelected.length})
      </button>

      {portfolioLas != null && (
        <div className="sidebar-las">
          <div className="las-label">Portfolio LAS</div>
          <div className="las-value">{portfolioLas.toFixed(4)}</div>
        </div>
      )}
    </nav>
  );
}

export default Sidebar;

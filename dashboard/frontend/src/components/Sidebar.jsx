import React, { useState, useEffect } from 'react';

const RISK_COLORS = {
  conservative: '#06d6a0',
  moderate: '#ffd166',
  aggressive: '#ef476f',
};

function Sidebar({
  tickers,
  selected,
  onAnalyze,
  portfolioLas,
  clients,
  activeClient,
  onSelectClient,
  onNewClient,
  onEditClient,
}) {
  const [localSelected, setLocalSelected] = useState(selected);

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
        {tickers.map(ticker => (
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

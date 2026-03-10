import React, { useState, useEffect } from 'react';

const RISK_OPTIONS = ['conservative', 'moderate', 'aggressive'];
const GOAL_OPTIONS = ['retirement', 'growth', 'income', 'preservation'];

function ClientModal({ isOpen, onClose, onSave, onDelete, client, availableTickers }) {
  const isEdit = !!client;

  const [name, setName] = useState('');
  const [riskTolerance, setRiskTolerance] = useState('moderate');
  const [investmentGoal, setInvestmentGoal] = useState('');
  const [notes, setNotes] = useState('');
  const [selectedTickers, setSelectedTickers] = useState([]);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (client) {
      setName(client.name || '');
      setRiskTolerance(client.risk_tolerance || 'moderate');
      setInvestmentGoal(client.investment_goal || '');
      setNotes(client.notes || '');
      setSelectedTickers(client.tickers || []);
    } else {
      setName('');
      setRiskTolerance('moderate');
      setInvestmentGoal('');
      setNotes('');
      setSelectedTickers([]);
    }
    setConfirmDelete(false);
  }, [client, isOpen]);

  if (!isOpen) return null;

  const toggleTicker = (ticker) => {
    setSelectedTickers(prev =>
      prev.includes(ticker) ? prev.filter(t => t !== ticker) : [...prev, ticker]
    );
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    onSave({
      name: name.trim(),
      risk_tolerance: riskTolerance,
      investment_goal: investmentGoal || null,
      notes: notes.trim() || null,
      tickers: selectedTickers,
      weights: selectedTickers.map(() => 1.0),
    });
  };

  const handleDelete = () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    onDelete(client.id);
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{isEdit ? 'Edit Client Profile' : 'New Client Profile'}</h3>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="modal-body">
          <div className="modal-field">
            <label>Client Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. John Smith"
              required
            />
          </div>

          <div className="modal-row">
            <div className="modal-field">
              <label>Risk Tolerance</label>
              <select value={riskTolerance} onChange={e => setRiskTolerance(e.target.value)}>
                {RISK_OPTIONS.map(r => (
                  <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
                ))}
              </select>
            </div>
            <div className="modal-field">
              <label>Investment Goal</label>
              <select value={investmentGoal} onChange={e => setInvestmentGoal(e.target.value)}>
                <option value="">-- Select --</option>
                {GOAL_OPTIONS.map(g => (
                  <option key={g} value={g}>{g.charAt(0).toUpperCase() + g.slice(1)}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="modal-field">
            <label>Notes</label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder="Optional notes about this client..."
              rows={2}
            />
          </div>

          <div className="modal-field">
            <label>Portfolio Tickers ({selectedTickers.length} selected)</label>
            <div className="modal-ticker-grid">
              {availableTickers.map(ticker => (
                <div
                  key={ticker}
                  className={`modal-ticker-chip ${selectedTickers.includes(ticker) ? 'active' : ''}`}
                  onClick={() => toggleTicker(ticker)}
                >
                  {ticker}
                </div>
              ))}
            </div>
          </div>

          <div className="modal-actions">
            {isEdit && onDelete && (
              <button
                type="button"
                className={`modal-btn danger ${confirmDelete ? 'confirm' : ''}`}
                onClick={handleDelete}
              >
                {confirmDelete ? 'Confirm Delete' : 'Delete'}
              </button>
            )}
            <div style={{ flex: 1 }} />
            <button type="button" className="modal-btn secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="modal-btn primary"
              disabled={!name.trim() || selectedTickers.length === 0}
            >
              {isEdit ? 'Save Changes' : 'Create Client'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default ClientModal;

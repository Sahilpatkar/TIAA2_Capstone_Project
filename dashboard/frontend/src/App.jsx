import React, { useState, useEffect, useCallback, Component } from 'react';
import './App.css';
import {
  fetchTickers, fetchFilings, fetchPortfolio, fetchSections,
  fetchClients, createClient, updateClient, deleteClient,
} from './api';
import Sidebar from './components/Sidebar';
import PortfolioOverview from './components/PortfolioOverview';
import FilingsTable from './components/FilingsTable';
import SectionChanges from './components/SectionChanges';
import LASChart from './components/LASChart';
import SimilarityChart from './components/SimilarityChart';
import LASvsCAR from './components/LASvsCAR';
import ChatPanel from './components/ChatPanel';
import RiskInsights from './components/RiskInsights';
import ClientModal from './components/ClientModal';

class ErrorBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, color: '#d63d5e' }}>
          <h2>Something went wrong</h2>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{this.state.error.message}</pre>
          <button onClick={() => this.setState({ error: null })}>Try again</button>
        </div>
      );
    }
    return this.props.children;
  }
}

const RISK_COLORS = {
  conservative: '#06d6a0',
  moderate: '#ffd166',
  aggressive: '#ef476f',
};

function App() {
  const [availableTickers, setAvailableTickers] = useState([]);
  const [selectedTickers, setSelectedTickers] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [filings, setFilings] = useState([]);
  const [sections, setSections] = useState([]);
  const [loading, setLoading] = useState(false);

  const [clients, setClients] = useState([]);
  const [activeClient, setActiveClient] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingClient, setEditingClient] = useState(null);

  useEffect(() => {
    fetchTickers()
      .then(setAvailableTickers)
      .catch(() => setAvailableTickers([]));
    fetchClients()
      .then(setClients)
      .catch(() => setClients([]));
  }, []);

  const refreshClients = useCallback(() => {
    fetchClients().then(setClients).catch(() => {});
  }, []);

  const loadAnalysis = useCallback((tickers) => {
    if (!tickers.length) return;
    setLoading(true);

    Promise.all([
      fetchPortfolio(tickers),
      fetchFilings(tickers),
      fetchSections(tickers, 10),
    ])
      .then(([portfolioData, filingsData, sectionsData]) => {
        setPortfolio(portfolioData);
        setFilings(Array.isArray(filingsData) ? filingsData : []);
        setSections(Array.isArray(sectionsData) ? sectionsData : []);
      })
      .catch(err => {
        console.error('Analysis error:', err);
        setPortfolio(null);
        setFilings([]);
        setSections([]);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleAnalyze = useCallback((tickers) => {
    if (!tickers.length) return;
    setSelectedTickers(tickers);
    loadAnalysis(tickers);
  }, [loadAnalysis]);

  const handleRefreshAfterPipeline = useCallback(() => {
    fetchTickers()
      .then(setAvailableTickers)
      .catch(() => {});
    if (selectedTickers.length) {
      loadAnalysis(selectedTickers);
    }
  }, [selectedTickers, loadAnalysis]);

  const handleSelectClient = useCallback((client) => {
    setActiveClient(client);
  }, []);

  const handleNewClient = useCallback(() => {
    setEditingClient(null);
    setModalOpen(true);
  }, []);

  const handleEditClient = useCallback((client) => {
    setEditingClient(client);
    setModalOpen(true);
  }, []);

  const handleModalSave = useCallback(async (data) => {
    if (editingClient) {
      const updated = await updateClient(editingClient.id, data);
      refreshClients();
      if (activeClient?.id === editingClient.id) {
        setActiveClient(updated);
      }
    } else {
      const created = await createClient(data);
      refreshClients();
      setActiveClient(created);
    }
    setModalOpen(false);
    setEditingClient(null);
  }, [editingClient, activeClient, refreshClients]);

  const handleModalDelete = useCallback(async (clientId) => {
    await deleteClient(clientId);
    refreshClients();
    if (activeClient?.id === clientId) {
      setActiveClient(null);
    }
    setModalOpen(false);
    setEditingClient(null);
  }, [activeClient, refreshClients]);

  return (
    <ErrorBoundary>
    <div className="app">
      <Sidebar
        tickers={availableTickers}
        selected={selectedTickers}
        onAnalyze={handleAnalyze}
        portfolioLas={portfolio?.portfolio_las}
        clients={clients}
        activeClient={activeClient}
        onSelectClient={handleSelectClient}
        onNewClient={handleNewClient}
        onEditClient={handleEditClient}
      />

      <main className="main-content">
        <header className="main-header">
          <h1>LazyPrices Advisor Dashboard</h1>
          <p className="subtitle">SEC 10-K Filing Change Detection &amp; Lazy Attention Scoring</p>
          {activeClient && (
            <div className="client-banner">
              <span className="client-banner-name">{activeClient.name}</span>
              <span
                className="risk-badge"
                style={{ background: RISK_COLORS[activeClient.risk_tolerance] || '#718096' }}
              >
                {activeClient.risk_tolerance}
              </span>
              {activeClient.investment_goal && (
                <span className="goal-tag">{activeClient.investment_goal}</span>
              )}
            </div>
          )}
        </header>

        {loading && <div className="loading-bar">Analyzing portfolio...</div>}

        {portfolio && !loading && (
          <>
            <PortfolioOverview portfolio={portfolio} filings={filings} onRefresh={handleRefreshAfterPipeline} />

            <div className="charts-row">
              <LASChart filings={filings} />
              <SimilarityChart filings={filings} />
            </div>

            <LASvsCAR filings={filings} />

            <RiskInsights sections={sections} tickers={selectedTickers} />

            <FilingsTable filings={filings} />

            <SectionChanges sections={sections} />
          </>
        )}

        {!portfolio && !loading && (
          <div className="empty-state">
            <div className="empty-icon">&#x1F4CA;</div>
            <h2>Select tickers to get started</h2>
            <p>Choose a client profile or select tickers from the sidebar and click Analyze to view the LazyPrices analysis.</p>
          </div>
        )}
      </main>

      <ChatPanel tickers={selectedTickers} activeClient={activeClient} />

      <ClientModal
        isOpen={modalOpen}
        onClose={() => { setModalOpen(false); setEditingClient(null); }}
        onSave={handleModalSave}
        onDelete={handleModalDelete}
        client={editingClient}
        availableTickers={availableTickers}
      />
    </div>
    </ErrorBoundary>
  );
}

export default App;

import React, { useState, useEffect, useCallback, useMemo, useRef, Component } from 'react';
import './App.css';
import {
  fetchTickers, fetchAllTickers, fetchFilings, fetchPortfolio, fetchSections,
  fetchClients, createClient, updateClient, deleteClient,
  runPipeline, subscribePipelineLogs,
} from './api';
import Sidebar from './components/Sidebar';
import PortfolioOverview from './components/PortfolioOverview';
import FilingsTable from './components/FilingsTable';
import SectionChanges from './components/SectionChanges';
import SectionExplorer from './components/SectionExplorer';
import LASChart from './components/LASChart';
import SimilarityChart from './components/SimilarityChart';
import LASvsCAR from './components/LASvsCAR';
import ChatPanel from './components/ChatPanel';
import RiskInsights from './components/RiskInsights';
import ClientModal from './components/ClientModal';
import SignalSummary from './components/SignalSummary';
import PipelineLogPanel from './components/PipelineLogPanel';

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
  const [tickerMeta, setTickerMeta] = useState([]);
  const [allTickerMeta, setAllTickerMeta] = useState([]);
  const [selectedTickers, setSelectedTickers] = useState([]);
  const [pipelineJobs, setPipelineJobs] = useState([]);
  const [logPanelMinimized, setLogPanelMinimized] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const closeSidebar = useCallback(() => setSidebarOpen(false), []);

  const availableTickers = useMemo(
    () => tickerMeta.map(t => t.ticker),
    [tickerMeta],
  );
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
      .then(setTickerMeta)
      .catch(() => setTickerMeta([]));
    fetchAllTickers()
      .then(setAllTickerMeta)
      .catch(() => setAllTickerMeta([]));
    fetchClients()
      .then(setClients)
      .catch(() => setClients([]));
  }, []);

  const refreshClients = useCallback(() => {
    fetchClients().then(setClients).catch(() => {});
  }, []);

  const loadAnalysis = useCallback((tickers, riskTolerance) => {
    if (!tickers.length) return;
    setLoading(true);

    Promise.all([
      fetchPortfolio(tickers, riskTolerance),
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
    loadAnalysis(tickers, activeClient?.risk_tolerance);
    setSidebarOpen(false);
  }, [loadAnalysis, activeClient]);

  const handleRefreshAfterPipeline = useCallback(() => {
    fetchTickers().then(setTickerMeta).catch(() => {});
    fetchAllTickers().then(setAllTickerMeta).catch(() => {});
    if (selectedTickers.length) {
      loadAnalysis(selectedTickers, activeClient?.risk_tolerance);
    }
  }, [selectedTickers, loadAnalysis, activeClient]);

  const eventSourcesRef = useRef({});

  const handleProcessTicker = useCallback((ticker) => {
    const tickerList = Array.isArray(ticker) ? ticker : [ticker];
    runPipeline(tickerList)
      .then(data => {
        const validTickers = data.tickers || tickerList;
        const jobEntry = {
          jobId: data.job_id,
          tickers: validTickers,
          skipped: data.skipped || [],
          status: 'running',
          logs: [],
          currentStage: '',
        };
        setPipelineJobs(prev => [...prev, jobEntry]);
        setLogPanelMinimized(false);

        const es = subscribePipelineLogs(
          data.job_id,
          // onLog
          (logData) => {
            setPipelineJobs(prev => prev.map(j =>
              j.jobId === data.job_id
                ? { ...j, logs: [...j.logs, logData], currentStage: logData.stage || j.currentStage }
                : j
            ));
          },
          // onDone
          (doneData) => {
            setPipelineJobs(prev => prev.map(j =>
              j.jobId === data.job_id
                ? { ...j, status: doneData.status }
                : j
            ));
            delete eventSourcesRef.current[data.job_id];
            handleRefreshAfterPipeline();
          },
          // onError
          () => {
            setPipelineJobs(prev => prev.map(j =>
              j.jobId === data.job_id
                ? { ...j, status: 'failed' }
                : j
            ));
            delete eventSourcesRef.current[data.job_id];
          },
        );
        eventSourcesRef.current[data.job_id] = es;
      })
      .catch(err => {
        console.error('Pipeline start failed:', err);
      });
  }, [handleRefreshAfterPipeline]);

  const handleCloseLogPanel = useCallback(() => {
    // Close all active SSE connections
    Object.values(eventSourcesRef.current).forEach(es => es.close());
    eventSourcesRef.current = {};
    setPipelineJobs([]);
  }, []);

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
    <div className={`app${sidebarOpen ? ' sidebar-open' : ''}`}>
      <button
        className="sidebar-toggle"
        aria-label={sidebarOpen ? 'Close menu' : 'Open menu'}
        onClick={() => setSidebarOpen(prev => !prev)}
      >
        {sidebarOpen ? '\u2715' : '\u2630'}
      </button>
      <div
        className="sidebar-backdrop"
        onClick={closeSidebar}
        aria-hidden="true"
      />
      <Sidebar
        tickerMeta={tickerMeta}
        allTickerMeta={allTickerMeta}
        selected={selectedTickers}
        onAnalyze={handleAnalyze}
        onProcessTicker={handleProcessTicker}
        pipelineJobs={pipelineJobs}
        portfolioLas={portfolio?.portfolio_las}
        clients={clients}
        activeClient={activeClient}
        onSelectClient={handleSelectClient}
        onNewClient={handleNewClient}
        onEditClient={handleEditClient}
        onCloseMobile={closeSidebar}
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
            <SignalSummary portfolio={portfolio} />
            <PortfolioOverview
              portfolio={portfolio}
              filings={filings}
              onRefresh={handleRefreshAfterPipeline}
              onProcessWithLogs={handleProcessTicker}
              pipelineJobs={pipelineJobs}
            />

            <div className="charts-row">
              <LASChart filings={filings} />
              <SimilarityChart filings={filings} />
            </div>

            <LASvsCAR filings={filings} portfolio={portfolio} />

            <RiskInsights sections={sections} tickers={selectedTickers} />

            <FilingsTable filings={filings} />

            <SectionChanges sections={sections} />

            <SectionExplorer tickers={selectedTickers} />
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

      <PipelineLogPanel
        jobs={pipelineJobs}
        onClose={handleCloseLogPanel}
        minimized={logPanelMinimized}
        onToggleMinimize={() => setLogPanelMinimized(prev => !prev)}
      />

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

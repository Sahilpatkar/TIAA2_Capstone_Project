import axios from 'axios';

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
});

export function fetchTickers() {
  return API.get('/tickers').then(r => r.data);
}

export function fetchAllTickers() {
  return API.get('/tickers/all').then(r => r.data);
}

export function fetchFilings(tickers) {
  const params = tickers && tickers.length > 0
    ? { tickers: tickers.join(',') }
    : {};
  return API.get('/filings', { params }).then(r => r.data);
}

export function fetchPortfolio(tickers, riskTolerance) {
  const params = { tickers: tickers.join(',') };
  if (riskTolerance) params.risk_tolerance = riskTolerance;
  return API.get('/portfolio', { params }).then(r => r.data);
}

export function fetchSections(tickers, top = 10) {
  return API.get('/sections', {
    params: { tickers: tickers.join(','), top },
  }).then(r => r.data);
}

export function fetchFilingSections(cik, accession) {
  return API.get(`/filing/${cik}/${accession}/sections`).then(r => r.data);
}

export function sendChat(message, tickers, history, { clientName, riskTolerance } = {}) {
  return API.post('/chat', {
    message,
    tickers,
    history,
    client_name: clientName || null,
    risk_tolerance: riskTolerance || null,
  }).then(r => r.data);
}

export function fetchClients() {
  return API.get('/clients').then(r => r.data);
}

export function createClient(data) {
  return API.post('/clients', data).then(r => r.data);
}

export function updateClient(id, data) {
  return API.put(`/clients/${id}`, data).then(r => r.data);
}

export function deleteClient(id) {
  return API.delete(`/clients/${id}`).then(r => r.data);
}

export function runPipeline(tickers, { force = false } = {}) {
  return API.post('/pipeline/run', { tickers, force }).then(r => r.data);
}

export function getPipelineStatus(jobId) {
  return API.get(`/pipeline/status/${jobId}`).then(r => r.data);
}

export function fetchRiskNarrative(tickers) {
  return API.get('/risk-narrative', {
    params: { tickers: tickers.join(',') },
  }).then(r => r.data);
}

export function subscribePipelineLogs(jobId, onLog, onDone, onError) {
  const baseUrl = import.meta.env.VITE_API_URL || '/api';
  const es = new EventSource(`${baseUrl}/pipeline/logs/${jobId}`);

  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'log') onLog(data);
      else if (data.type === 'done') { onDone(data); es.close(); }
      else if (data.type === 'error') { onError(data); es.close(); }
    } catch { /* ignore parse errors */ }
  };

  es.onerror = () => {
    onError({ msg: 'Connection lost' });
    es.close();
  };

  return es;
}

export function fetchSectionChangeSummary({ ticker, section, snippet_old, snippet_new }) {
  return API.post('/sections/summarize', {
    ticker,
    section,
    snippet_old,
    snippet_new,
  }).then(r => r.data);
}

export function analyzeSection({ ticker, section, accession }) {
  return API.post('/sections/analyze', {
    ticker,
    section,
    accession: accession || null,
  }).then(r => r.data);
}

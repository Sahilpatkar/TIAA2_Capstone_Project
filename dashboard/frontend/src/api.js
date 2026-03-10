import axios from 'axios';

const API = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
});

export function fetchTickers() {
  return API.get('/tickers').then(r => r.data);
}

export function fetchFilings(tickers) {
  const params = tickers && tickers.length > 0
    ? { tickers: tickers.join(',') }
    : {};
  return API.get('/filings', { params }).then(r => r.data);
}

export function fetchPortfolio(tickers) {
  return API.get('/portfolio', {
    params: { tickers: tickers.join(',') },
  }).then(r => r.data);
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

export function runPipeline(tickers) {
  return API.post('/pipeline/run', { tickers }).then(r => r.data);
}

export function getPipelineStatus(jobId) {
  return API.get(`/pipeline/status/${jobId}`).then(r => r.data);
}

export function fetchRiskNarrative(tickers) {
  return API.get('/risk-narrative', {
    params: { tickers: tickers.join(',') },
  }).then(r => r.data);
}

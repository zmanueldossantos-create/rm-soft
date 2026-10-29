// API calls for DocumentSeries (Video 4/8, company-scoped).
import apiClient from './client';

export async function listDocumentSeries() {
  const res = await apiClient.get('/document-series');
  return res.data;
}

export async function createDocumentSeries(payload) {
  const res = await apiClient.post('/document-series', payload);
  return res.data;
}

export async function toggleDocumentSeriesStatus(seriesId) {
  const res = await apiClient.patch('/document-series/' + seriesId + '/toggle-status');
  return res.data;
}

export async function updateDocumentSeries(seriesId, payload) {
  const res = await apiClient.patch('/document-series/' + seriesId, payload);
  return res.data;
}

// The years a series can be created for (AGT: the next year too after 15 December).
export async function getAllowedSeriesYears() {
  const res = await apiClient.get('/document-series/allowed-years');
  return res.data;
}

// «Sincronizar com a AGT» (Faturação Eletrónica): the AGT's status, range and period of each series, and the series
// the AGT knows that this server does not - {updated, added, unknown, series}
export async function syncDocumentSeriesWithAgt() {
  const res = await apiClient.post('/document-series/sync-agt');
  return res.data;
}

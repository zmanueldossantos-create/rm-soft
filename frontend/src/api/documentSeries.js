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

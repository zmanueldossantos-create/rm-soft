import apiClient from './client';

export async function createMovementDocument(payload) {
  const res = await apiClient.post('/movements', payload);
  return res.data;
}

export async function listMovementDocuments() {
  const res = await apiClient.get('/movements');
  return res.data;
}

export async function getMovementDocumentDetail(id) {
  const res = await apiClient.get('/movements/' + id);
  return res.data;
}

export async function downloadMovementExcelTemplate() {
  const res = await apiClient.get('/movements/excel-template', { responseType: 'blob' });
  const blobUrl = URL.createObjectURL(res.data);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = 'modelo_movimento.xlsx';
  a.click();
  URL.revokeObjectURL(blobUrl);
}

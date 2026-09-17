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

export async function importMovementDocument({ movementTypeId, warehouseId, movementDate, description, file }) {
  const formData = new FormData();
  formData.append('movement_type_id', movementTypeId);
  formData.append('warehouse_id', warehouseId);
  if (movementDate) formData.append('movement_date', movementDate);
  if (description) formData.append('description', description);
  formData.append('file', file);
  const res = await apiClient.post('/movements/import', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

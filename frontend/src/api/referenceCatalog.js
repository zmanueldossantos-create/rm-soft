// Catálogo de referência (SUPER_ADMIN): the platform's products by sector, typed or imported from Excel.
import apiClient from './client';

const MULTIPART = { headers: { 'Content-Type': 'multipart/form-data' } };

export async function getReferenceMeta() {
  const res = await apiClient.get('/admin/reference-catalog/meta');
  return res.data;
}

export async function listReferenceProducts({ q = '', sector = null, offset = 0, limit = 100 } = {}) {
  const res = await apiClient.get('/admin/reference-catalog', { params: { q, sector: sector || undefined, offset, limit } });
  return res.data;
}

export async function saveReferenceProduct(id, payload) {
  const res = id
    ? await apiClient.put(`/admin/reference-catalog/${id}`, payload)
    : await apiClient.post('/admin/reference-catalog', payload);
  return res.data;
}

export async function deleteReferenceProduct(id) {
  await apiClient.delete(`/admin/reference-catalog/${id}`);
}

export async function downloadReferenceTemplate() {
  const res = await apiClient.get('/admin/reference-catalog-template', { responseType: 'blob' });
  const url = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'catalogo_referencia_modelo.xlsx';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export async function importReferenceCatalog(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await apiClient.post('/admin/reference-catalog-import', form, MULTIPART);
  return res.data;
}

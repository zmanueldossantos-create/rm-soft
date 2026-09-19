import apiClient from './client';

export async function listSuppliers() {
  const res = await apiClient.get('/suppliers');
  return res.data;
}

export async function createSupplier(payload) {
  const res = await apiClient.post('/suppliers', payload);
  return res.data;
}

export async function updateSupplier(supplierId, payload) {
  const res = await apiClient.patch('/suppliers/' + supplierId, payload);
  return res.data;
}

export async function toggleSupplierStatus(supplierId) {
  const res = await apiClient.post('/suppliers/' + supplierId + '/toggle');
  return res.data;
}

// API calls for Service (Video 3, company-scoped, separate from Product).
import apiClient from './client';

export async function listServices() {
  const res = await apiClient.get('/services');
  return res.data;
}

export async function createService(payload) {
  const res = await apiClient.post('/services', payload);
  return res.data;
}

export async function updateService(serviceId, payload) {
  const res = await apiClient.patch('/services/' + serviceId, payload);
  return res.data;
}

export async function toggleServiceStatus(serviceId) {
  const res = await apiClient.patch('/services/' + serviceId + '/toggle-status');
  return res.data;
}

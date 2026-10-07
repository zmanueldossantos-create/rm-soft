// API calls for ServiceType (company-scoped, Video 3).
import apiClient from './client';

export async function listServiceTypes() {
  const res = await apiClient.get('/service-types');
  return res.data;
}

export async function createServiceType(payload) {
  const res = await apiClient.post('/service-types', payload);
  return res.data;
}

export async function updateServiceType(serviceTypeId, payload) {
  const res = await apiClient.patch('/service-types/' + serviceTypeId, payload);
  return res.data;
}

export async function toggleServiceTypeStatus(serviceTypeId) {
  const res = await apiClient.patch('/service-types/' + serviceTypeId + '/toggle-status');
  return res.data;
}

// API calls for Establishment (company-scoped, Video 8).
import apiClient from './client';

export async function listEstablishments() {
  const res = await apiClient.get('/establishments');
  return res.data;
}

export async function createEstablishment(payload) {
  const res = await apiClient.post('/establishments', payload);
  return res.data;
}

export async function updateEstablishment(establishmentId, payload) {
  const res = await apiClient.patch('/establishments/' + establishmentId, payload);
  return res.data;
}

export async function toggleEstablishmentStatus(establishmentId) {
  const res = await apiClient.patch('/establishments/' + establishmentId + '/toggle-status');
  return res.data;
}

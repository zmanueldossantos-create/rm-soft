// Guias (goods_movement_service): GR to a customer, GT between warehouses, GD back to a supplier.
import apiClient from './client';

export async function listGuias(filters = {}) {
  const params = {};
  if (filters.type) params.movement_type = filters.type;
  if (filters.status) params.guia_status = filters.status;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  return (await apiClient.get('/guias', { params })).data;
}

export async function getGuia(id) {
  return (await apiClient.get('/guias/' + id)).data;
}

export async function createGuia(payload) {
  return (await apiClient.post('/guias', payload)).data;
}

export async function cancelGuia(id, reason) {
  return (await apiClient.post('/guias/' + id + '/cancel', { reason })).data;
}

export async function fetchGuiaPdfBlob(id) {
  const res = await apiClient.get('/guias/' + id + '/pdf', { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

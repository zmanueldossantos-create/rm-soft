import apiClient from './client';

// ---------- Consumption reasons (managed catalog) ----------

export async function listConsumptionReasons() {
  const res = await apiClient.get('/consumption-reasons');
  return res.data;
}

export async function createConsumptionReason(name) {
  const res = await apiClient.post('/consumption-reasons', { name });
  return res.data;
}

export async function updateConsumptionReason(reasonId, name) {
  const res = await apiClient.patch('/consumption-reasons/' + reasonId, { name });
  return res.data;
}

export async function toggleConsumptionReasonStatus(reasonId) {
  const res = await apiClient.post('/consumption-reasons/' + reasonId + '/toggle');
  return res.data;
}

// ---------- Internal consumption records ----------

export async function recordConsumption(payload) {
  const res = await apiClient.post('/internal-consumption', payload);
  return res.data;
}

export async function listInternalConsumption(filters = {}) {
  const params = {};
  if (filters.activityId) params.activity_id = filters.activityId;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  const res = await apiClient.get('/internal-consumption', { params });
  return res.data;
}

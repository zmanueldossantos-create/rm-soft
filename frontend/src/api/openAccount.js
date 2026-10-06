import apiClient from './client';

export async function listOpenAccounts(activityId = null) {
  const params = {};
  if (activityId) params.activity_id = activityId;
  const res = await apiClient.get('/open-accounts', { params });
  return res.data;
}

export async function getOpenAccount(accountId) {
  const res = await apiClient.get('/open-accounts/' + accountId);
  return res.data;
}

export async function openAccount(payload) {
  const res = await apiClient.post('/open-accounts', payload);
  return res.data;
}

export async function listAccountLines(accountId) {
  const res = await apiClient.get('/open-accounts/' + accountId + '/lines');
  return res.data;
}

export async function addAccountLine(accountId, payload) {
  const res = await apiClient.post('/open-accounts/' + accountId + '/lines', payload);
  return res.data;
}

export async function updateAccountLineQuantity(accountId, lineId, quantity) {
  const res = await apiClient.patch('/open-accounts/' + accountId + '/lines/' + lineId, { quantity });
  return res.data;
}

export async function updateAccountLineUnit(accountId, lineId, saleUnitId) {
  const res = await apiClient.patch('/open-accounts/' + accountId + '/lines/' + lineId + '/unit', { sale_unit_id: saleUnitId });
  return res.data;
}

export async function removeAccountLine(accountId, lineId) {
  await apiClient.delete('/open-accounts/' + accountId + '/lines/' + lineId);
}

export async function closeAccount(accountId, payload) {
  const res = await apiClient.post('/open-accounts/' + accountId + '/close', payload);
  return res.data;
}

export async function transferAccountLines(accountId, payload) {
  const res = await apiClient.post('/open-accounts/' + accountId + '/transfer', payload);
  return res.data;
}

// Contabilidade - the chart of accounts (plano de contas).
import apiClient from './client';

export async function getChart() {
  const res = await apiClient.get('/accounting/chart');
  return res.data;
}

// The first choice: 'PGC' (the system's reference list), 'PROPRIO' (then imported) or 'VAZIO'
export async function startChart(source) {
  const res = await apiClient.post('/accounting/chart/start', { source });
  return res.data;
}

// The Excel model, saved by the browser
export async function downloadChartTemplate() {
  const res = await apiClient.get('/accounting/chart/template', { responseType: 'blob' });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'plano_de_contas_modelo.xlsx';
  a.click();
  URL.revokeObjectURL(url);
}

// The filled model: { created, renamed, unchanged } - or a 422 with { detail, errors: [every wrong row] }
export async function importChart(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await apiClient.post('/accounting/chart/import', form, { headers: { 'Content-Type': 'multipart/form-data' } });
  return res.data;
}

export async function createAccount(code, name) {
  const res = await apiClient.post('/accounting/accounts', { code, name });
  return res.data;
}

export async function updateAccount(accountId, name, isActive) {
  const res = await apiClient.put('/accounting/accounts/' + accountId, { name, is_active: isActive });
  return res.data;
}

export async function deleteAccount(accountId) {
  await apiClient.delete('/accounting/accounts/' + accountId);
}

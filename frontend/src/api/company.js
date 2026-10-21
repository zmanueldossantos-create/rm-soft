// API calls for the caller's own company settings (GESTOR self-service).
import apiClient from './client';

export async function getMyCompany() {
  const res = await apiClient.get('/company/me');
  return res.data;
}

export async function updateMyCompanyContact(payload) {
  const res = await apiClient.patch('/company/me', payload);
  return res.data;
}

export async function uploadMyCompanyLogo(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post('/company/me/logo', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function getMyCompanyBankAccounts() {
  const res = await apiClient.get('/company/me/bank-accounts');
  return res.data;
}

export async function addMyCompanyBankAccount(payload) {
  const res = await apiClient.post('/company/me/bank-accounts', payload);
  return res.data;
}

export async function updateMyCompanyBankAccount(accountId, payload) {
  const res = await apiClient.patch('/company/me/bank-accounts/' + accountId, payload);
  return res.data;
}

export async function toggleMyCompanyBankAccountStatus(accountId) {
  const res = await apiClient.patch('/company/me/bank-accounts/' + accountId + '/toggle-status');
  return res.data;
}

export async function removeMyCompanyLogo() {
  const res = await apiClient.delete('/company/me/logo');
  return res.data;
}

// Configuração inicial: the company's set-up steps, each ticked from the real data.
export async function getMyCompanySetup() {
  const res = await apiClient.get('/company/me/setup');
  return res.data;
}

// The RM SOFT support accesses to the company (who, when, why).
export async function getMySupportSessions() {
  const res = await apiClient.get('/company/me/support-sessions');
  return res.data;
}

// Cópias de segurança of the company: settings (automatic / manual), copies, «Fazer cópia agora», download.
export async function getMyBackups() {
  const res = await apiClient.get('/company/me/backups');
  return res.data;
}

export async function saveMyBackupSettings(mode, times) {
  const res = await apiClient.put('/company/me/backups/settings', { mode, times });
  return res.data;
}

export async function makeMyBackup() {
  const res = await apiClient.post('/company/me/backups');
  return res.data;
}

export async function downloadMyBackup(backupId, fileName) {
  const res = await apiClient.get(`/company/me/backups/${backupId}/download`, { responseType: 'blob' });
  saveBlob(res.data, fileName);
}

function saveBlob(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName || 'copia.zip';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

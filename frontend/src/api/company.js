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

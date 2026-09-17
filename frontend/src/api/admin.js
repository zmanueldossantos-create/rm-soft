// API calls for platform administration (SUPER_ADMIN only).
import apiClient from './client';

export async function listCompanies() {
  const res = await apiClient.get('/admin/companies');
  return res.data;
}

export async function createCompany(payload) {
  const res = await apiClient.post('/admin/companies', payload);
  return res.data;
}

export async function updateCompany(companyId, payload) {
  const res = await apiClient.patch('/admin/companies/' + companyId, payload);
  return res.data;
}

export async function listBankAccounts(companyId) {
  const res = await apiClient.get('/admin/companies/' + companyId + '/bank-accounts');
  return res.data;
}

export async function addBankAccount(companyId, payload) {
  const res = await apiClient.post('/admin/companies/' + companyId + '/bank-accounts', payload);
  return res.data;
}

export async function updateBankAccount(companyId, accountId, payload) {
  const res = await apiClient.patch('/admin/companies/' + companyId + '/bank-accounts/' + accountId, payload);
  return res.data;
}

export async function toggleBankAccountStatus(companyId, accountId) {
  const res = await apiClient.patch('/admin/companies/' + companyId + '/bank-accounts/' + accountId + '/toggle-status');
  return res.data;
}

export async function toggleCompanyStatus(companyId) {
  const res = await apiClient.patch('/admin/companies/' + companyId + '/toggle-status');
  return res.data;
}

export async function getPlatformSettings() {
  const res = await apiClient.get('/admin/settings');
  return res.data;
}

export async function updatePlatformSettings(softwareValidationNumber, vendorTaxId, productId, productVersion) {
  const res = await apiClient.patch('/admin/settings', {
    software_validation_number: softwareValidationNumber || null,
    vendor_tax_id: vendorTaxId || null,
    product_id: productId || null,
    product_version: productVersion || null,
  });
  return res.data;
}


export async function getCompanyGestor(companyId) {
  const res = await apiClient.get('/admin/companies/' + companyId + '/gestor');
  return res.data;
}

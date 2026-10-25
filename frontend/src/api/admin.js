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

// The contacts the public site shows (rmsystem.co.ao)
export async function getSiteSettings() {
  return (await apiClient.get('/admin/site-settings')).data;
}

export async function updateSiteSettings(siteWhatsapp, siteEmail) {
  return (await apiClient.put('/admin/site-settings', { site_whatsapp: siteWhatsapp || null, site_email: siteEmail || null })).data;
}


export async function getCompanyGestor(companyId) {
  const res = await apiClient.get('/admin/companies/' + companyId + '/gestor');
  return res.data;
}

// The company's fiscal regimes, most recent first, each with the day it took effect.
export async function getCompanyRegimeHistory(companyId) {
  const res = await apiClient.get(`/admin/companies/${companyId}/regime-history`);
  return res.data;
}

// Configuração inicial of a client company (read only for the platform).
export async function getCompanySetup(companyId) {
  const res = await apiClient.get(`/admin/companies/${companyId}/setup`);
  return res.data;
}

// Acesso de suporte: a one-time code opening the company with the gestor's screens (an hour at most).
export async function startSupport(companyId, reason) {
  const res = await apiClient.post(`/admin/companies/${companyId}/support`, { reason });
  return res.data;
}

export async function listSupportSessions(companyId) {
  const res = await apiClient.get(`/admin/companies/${companyId}/support`);
  return res.data;
}

// Cópia de segurança de uma empresa: «Exportar» downloads its file; «Restaurar» checks a file, then puts it back.
export async function downloadCompanyBackup(companyId) {
  const res = await apiClient.get(`/admin/companies/${companyId}/export`, { responseType: 'blob' });
  const match = /filename="([^"]+)"/.exec(res.headers['content-disposition'] || '');
  const blobUrl = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = match ? match[1] : 'rmsoft_copia.zip';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(blobUrl);
}

// the shared client sends JSON by default: a file goes as a form
const MULTIPART = { headers: { 'Content-Type': 'multipart/form-data' } };

function backupForm(file) {
  const form = new FormData();
  form.append('file', file);
  return form;
}

export async function inspectCompanyBackup(file) {
  const res = await apiClient.post('/admin/companies/restore/inspect', backupForm(file), MULTIPART);
  return res.data;
}

export async function restoreCompanyBackup(file) {
  const res = await apiClient.post('/admin/companies/restore', backupForm(file), MULTIPART);
  return res.data;
}

// «Nova empresa» > Base: what a backup file can give a new company; the file is kept under the returned token.
export async function inspectCompanyBase(file) {
  const res = await apiClient.post('/admin/company-base/inspect', backupForm(file), MULTIPART);
  return res.data;
}

// Cópias de segurança, the platform's side: every company's state, one company's copies, a copy now, download.
export async function getBackupsOverview() {
  const res = await apiClient.get('/admin/backups');
  return res.data;
}

export async function getCompanyBackups(companyId) {
  const res = await apiClient.get(`/admin/companies/${companyId}/backups`);
  return res.data;
}

export async function makeCompanyBackup(companyId) {
  const res = await apiClient.post(`/admin/companies/${companyId}/backups`);
  return res.data;
}

export async function downloadCompanyBackupCopy(backupId, fileName) {
  const res = await apiClient.get(`/admin/backups/${backupId}/download`, { responseType: 'blob' });
  const url = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName || 'copia.zip';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

// «Nova empresa» > Base: how many reference catalog products a company of these modules receives.
export async function getReferenceOffer(moduleIds) {
  const params = new URLSearchParams();
  (moduleIds || []).forEach((id) => params.append('module_ids', id));
  const res = await apiClient.get('/admin/reference-catalog/offer?' + params.toString());
  return res.data;
}

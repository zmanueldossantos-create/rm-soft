// API calls for VAT rates (read-only for GESTOR/ADMIN - see decision on fiscal compliance).
import apiClient from './client';

export async function listVatRates() {
  const res = await apiClient.get('/vat');
  return res.data;
}

// SUPER_ADMIN-only: manage a specific company's VAT rates.
export async function listCompanyVatRates(companyId) {
  const res = await apiClient.get(`/vat/companies/${companyId}`);
  return res.data;
}

export async function createCompanyVatRate(companyId, name, rate, taxCategory) {
  const res = await apiClient.post(`/vat/companies/${companyId}`, { name, rate, tax_category: taxCategory });
  return res.data;
}

export async function updateCompanyVatRate(companyId, vatId, name, rate, taxCategory) {
  const res = await apiClient.patch(`/vat/companies/${companyId}/${vatId}`, { name, rate, tax_category: taxCategory });
  return res.data;
}

export async function toggleCompanyVatRate(companyId, vatId) {
  const res = await apiClient.patch(`/vat/companies/${companyId}/${vatId}/toggle-status`);
  return res.data;
}

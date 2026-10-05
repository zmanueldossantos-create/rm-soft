// API calls for VAT rates (read-only for GESTOR/ADMIN - see decision on fiscal compliance).
import apiClient from './client';

export async function listVatRates() {
  const res = await apiClient.get('/vat');
  return res.data;
}

// What the company's regime imposes on a sold article's VAT (the exemption motive of its exempt articles).
export async function getArticleVatRule() {
  const res = await apiClient.get('/vat/article-rule');
  return res.data;
}

// SUPER_ADMIN-only: manage a specific company's VAT rates.
export async function listCompanyVatRates(companyId) {
  const res = await apiClient.get(`/vat/companies/${companyId}`);
  return res.data;
}

// Products and services to reclassify after a regime change (they cannot be sold until then).
export async function getReclassification() {
  const res = await apiClient.get('/vat/reclassification');
  return res.data;
}

// Gives several products and services one VAT rate (and motive).
export async function reclassifyArticles(payload) {
  const res = await apiClient.post('/vat/reclassify', payload);
  return res.data;
}

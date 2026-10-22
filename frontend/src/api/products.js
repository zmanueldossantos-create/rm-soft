// API calls for products, scoped to the caller's company.
import apiClient from './client';

export async function listProducts() {
  const res = await apiClient.get('/products');
  return res.data;
}

export async function createProduct(payload) {
  const res = await apiClient.post('/products', payload);
  return res.data;
}

export async function updateProduct(productId, payload) {
  const res = await apiClient.patch('/products/' + productId, payload);
  return res.data;
}

export async function toggleProductStatus(productId) {
  const res = await apiClient.patch('/products/' + productId + '/toggle-status');
  return res.data;
}

export async function uploadProductImage(productId, file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiClient.post('/products/' + productId + '/image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function deleteProductImage(productId) {
  const res = await apiClient.delete('/products/' + productId + '/image');
  return res.data;
}

// Sale units of a product (pallet / egg, box / blister): the product itself is the base unit.
export async function listSaleUnits(productId) {
  const res = await apiClient.get('/products/' + productId + '/sale-units');
  return res.data;
}

export async function createSaleUnit(productId, payload) {
  const res = await apiClient.post('/products/' + productId + '/sale-units', payload);
  return res.data;
}

export async function updateSaleUnit(productId, unitId, payload) {
  const res = await apiClient.patch('/products/' + productId + '/sale-units/' + unitId, payload);
  return res.data;
}

export async function toggleSaleUnit(productId, unitId) {
  const res = await apiClient.patch('/products/' + productId + '/sale-units/' + unitId + '/toggle-status');
  return res.data;
}

// Histórico do custo: each entry that moved the average cost (priced reception, production) - filters: { dateFrom, dateTo }
export async function getCostHistory(productId, filters = {}) {
  const params = {};
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  const res = await apiClient.get('/products/' + productId + '/cost-history', { params });
  return res.data;
}

// Catálogo de referência, from a company: a barcode's product, the list to pick from, and taking the chosen ones
export async function lookupReferenceBarcode(barcode) {
  const res = await apiClient.get('/products/reference-catalog/lookup', { params: { barcode } });
  return res.data;
}

export async function listCompanyReferenceCatalog({ q = '', sector = null, mine = true, offset = 0, limit = 100 } = {}) {
  const res = await apiClient.get('/products/reference-catalog', { params: { q, sector: sector || undefined, mine, offset, limit } });
  return res.data;
}

export async function takeReferenceProducts(ids) {
  const res = await apiClient.post('/products/reference-catalog/take', { ids });
  return res.data;
}

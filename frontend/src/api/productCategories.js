// API calls for ProductCategory (company-scoped, Video 3).
import apiClient from './client';

export async function listProductCategories() {
  const res = await apiClient.get('/product-categories');
  return res.data;
}

export async function createProductCategory(payload) {
  const res = await apiClient.post('/product-categories', payload);
  return res.data;
}

export async function updateProductCategory(categoryId, payload) {
  const res = await apiClient.patch('/product-categories/' + categoryId, payload);
  return res.data;
}

export async function toggleProductCategoryStatus(categoryId) {
  const res = await apiClient.patch('/product-categories/' + categoryId + '/toggle-status');
  return res.data;
}

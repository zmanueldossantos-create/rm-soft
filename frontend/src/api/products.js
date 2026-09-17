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

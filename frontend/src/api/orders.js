import apiClient from './client';

// Encomendas: the customers' orders (capability ORDERS)
export async function listOrders(params = {}) {
  const res = await apiClient.get('/orders', { params });
  return res.data;
}

export async function getOrderOptions() {
  const res = await apiClient.get('/orders/options');
  return res.data;
}

export async function createOrder(payload) {
  const res = await apiClient.post('/orders', payload);
  return res.data;
}

export async function updateOrder(orderId, payload) {
  const res = await apiClient.put('/orders/' + orderId, payload);
  return res.data;
}

export async function setOrderStatus(orderId, status) {
  const res = await apiClient.post('/orders/' + orderId + '/status', { status });
  return res.data;
}

export async function cancelOrder(orderId, reason) {
  const res = await apiClient.post('/orders/' + orderId + '/cancel', { reason });
  return res.data;
}

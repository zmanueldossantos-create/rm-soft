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

export async function cancelOrder(orderId, reason, deposit = null, refund = null) {
  const res = await apiClient.post('/orders/' + orderId + '/cancel', { reason, deposit, refund });
  return res.data;
}

export async function getOrderCancelInfo(orderId) {
  const res = await apiClient.get('/orders/' + orderId + '/cancel-info');
  return res.data;
}

// a deposit received at a till (the order's Fatura and a Recibo)
export async function payOrder(orderId, payload) {
  const res = await apiClient.post('/orders/' + orderId + '/pay', payload);
  return res.data;
}

// handed over at a till: the rest received (Recibo / Fatura-Recibo) or left owing (on_credit)
export async function deliverOrder(orderId, payload) {
  const res = await apiClient.post('/orders/' + orderId + '/deliver', payload);
  return res.data;
}

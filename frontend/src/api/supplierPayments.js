// Pagamentos a fornecedores (point 3): the payments of supplier invoices, the balances and the conta corrente.
import apiClient from './client';

// filters: { supplierId, status, dateFrom, dateTo }
export async function listSupplierPayments(filters = {}) {
  const params = {};
  if (filters.supplierId) params.supplier_id = filters.supplierId;
  if (filters.status) params.payment_status = filters.status;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  return (await apiClient.get('/supplier-payments', { params })).data;
}

export async function getSupplierPayment(id) {
  return (await apiClient.get('/supplier-payments/' + id)).data;
}

export async function createSupplierPayment(payload) {
  return (await apiClient.post('/supplier-payments', payload)).data;
}

export async function cancelSupplierPayment(id, reason) {
  return (await apiClient.post('/supplier-payments/' + id + '/cancel', { reason })).data;
}

export async function fetchSupplierPaymentPdfBlob(id) {
  const res = await apiClient.get('/supplier-payments/' + id + '/pdf', { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

// { supplier id: what the company owes it }
export async function getSupplierBalances() {
  return (await apiClient.get('/supplier-payments/balances')).data;
}

export async function getSupplierStatement(supplierId, dateFrom, dateTo) {
  const params = {};
  if (dateFrom) params.date_from = dateFrom;
  if (dateTo) params.date_to = dateTo;
  return (await apiClient.get('/supplier-payments/statement/' + supplierId, { params })).data;
}

export async function fetchSupplierStatementPdfBlob(supplierId, dateFrom, dateTo) {
  const params = {};
  if (dateFrom) params.date_from = dateFrom;
  if (dateTo) params.date_to = dateTo;
  const res = await apiClient.get('/supplier-payments/statement/' + supplierId + '/pdf', { params, responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

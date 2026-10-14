// Faturas de compra (point 12): the supplier invoices the company registers.
import apiClient from './client';

// filters: { supplierId, fiscalPeriodId, status, dateFrom, dateTo }
export async function listPurchaseInvoices(filters = {}) {
  const params = {};
  if (filters.supplierId) params.supplier_id = filters.supplierId;
  if (filters.fiscalPeriodId) params.fiscal_period_id = filters.fiscalPeriodId;
  if (filters.status) params.invoice_status = filters.status;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  const res = await apiClient.get('/purchases', { params });
  return res.data;
}

export async function getPurchaseInvoice(id) {
  const res = await apiClient.get('/purchases/' + id);
  return res.data;
}

export async function registerPurchaseInvoice(payload) {
  const res = await apiClient.post('/purchases', payload);
  return res.data;
}

export async function cancelPurchaseInvoice(id, reason) {
  const res = await apiClient.post('/purchases/' + id + '/cancel', { reason });
  return res.data;
}

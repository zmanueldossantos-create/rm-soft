// API calls for invoices, scoped to the caller's company.
import apiClient from './client';

export async function listInvoices(filters = {}) {
  const params = {};
  if (filters.year) params.year = filters.year;
  if (filters.month) params.month = filters.month;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  params.limit = filters.limit || 50;
  params.offset = filters.offset || 0;
  const res = await apiClient.get('/invoices', { params });
  return res.data;
}

export async function getInvoicePeriods() {
  const res = await apiClient.get('/invoices/available-periods');
  return res.data;
}

export async function getInvoiceDetail(invoiceId) {
  const res = await apiClient.get('/invoices/' + invoiceId);
  return res.data;
}

export async function createInvoice(payload) {
  const res = await apiClient.post('/invoices', payload);
  return res.data;
}

// Fetches the PDF as a blob and returns its object URL - the caller renders it inside an
// in-app modal (iframe) instead of a separate browser tab, so it stays part of the app's
// own navigation (see the Kiami reference: an embedded viewer with Fechar/Guardar buttons).
export async function fetchInvoicePdfBlob(invoiceId, format) {
  const res = await apiClient.get('/invoices/' + invoiceId + '/pdf', {
    params: { format },
    responseType: 'blob',
  });
  return URL.createObjectURL(res.data);
}

export async function resubmitInvoice(invoiceId) {
  const res = await apiClient.post('/invoices/' + invoiceId + '/resubmit');
  return res.data;
}

export async function createCreditNote(payload) {
  const res = await apiClient.post('/invoices/credit-note', payload);
  return res.data;
}

// What the NC screen needs: what is left to credit per line, collected / refunded / due and the open cash points.
export async function getCreditNoteInfo(invoiceId) {
  const res = await apiClient.get('/invoices/' + invoiceId + '/credit-note-info');
  return res.data;
}

// The cash points with an open session (and the cash they hold) - where cash enters or leaves from Faturas.
export async function getOpenCashPoints() {
  const res = await apiClient.get('/invoices/open-cash-points');
  return res.data;
}

export async function createDebitNote(payload) {
  const res = await apiClient.post('/invoices/debit-note', payload);
  return res.data;
}

export async function createReceipt(payload) {
  const res = await apiClient.post('/invoices/receipt', payload);
  return res.data;
}

export async function createProForma(payload) {
  const res = await apiClient.post('/invoices/pro-forma', payload);
  return res.data;
}

export async function convertProForma(itemId, payload) {
  const res = await apiClient.post(`/invoices/pro-forma/${itemId}/convert`, payload);
  return res.data;
}


export async function listPendingProFormas() {
  const res = await apiClient.get('/invoices', { params: { invoice_type: 'PRO_FORMA', pending_only: true, limit: 50 } });
  return res.data;
}

// Documents shown by the Caixa: those of this cash point plus the invoices still awaiting a payment (filtered server side).
export async function listRecentIssuedInvoices(posId) {
  const res = await apiClient.get('/pos/documents/' + posId, { params: { limit: 30 } });
  return res.data;
}

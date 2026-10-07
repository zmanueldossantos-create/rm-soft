// API calls for the POS/Caixa module (cash sessions + checkout).
import apiClient from './client';

export async function openCashSession(posId, openingAmount = null) {
  const res = await apiClient.post('/pos/sessions/open', { pos_id: posId, opening_amount: openingAmount });
  return res.data;
}

export async function getOpenCashSession(posId) {
  const res = await apiClient.get('/pos/sessions/open', { params: { pos_id: posId } });
  return res.data;
}

// The balance of the open session, justified: cash in the drawer (balance), received by payment method,
// movements and receptions pending - see cash_session_service.get_session_summary.
export async function getSessionSummary(posId) {
  const res = await apiClient.get('/pos/sessions/balance', { params: { pos_id: posId } });
  return res.data;
}

export async function getCarryForwardAmount(posId) {
  const res = await apiClient.get('/pos/sessions/carry-forward', { params: { pos_id: posId } });
  return res.data.amount;
}

// The quantity of each product the till sells from - read from THE till stock route (getPosStock), which also
// carries the warehouse's rules (negative stock, blocked exits).
export async function getPosStockLevels(posId) {
  return ((await getPosStock(posId)) || {}).stock || {};
}

export async function closeCashSession(sessionId, closingAmountCounted, closingNotes) {
  const res = await apiClient.post('/pos/sessions/' + sessionId + '/close', {
    closing_amount_counted: closingAmountCounted,
    closing_notes: closingNotes || null,
  });
  return res.data;
}

export async function listCashSessions(posId) {
  const res = await apiClient.get('/pos/sessions', { params: posId ? { pos_id: posId } : {} });
  return res.data;
}

export async function checkout(posId, customerId, lines, payments, invoiceType = 'FACTURA', discountGlobalPercent = 0, ftDetails = {}) {
  const res = await apiClient.post('/pos/checkout/' + posId, {
    customer_id: customerId || null,
    invoice_type: invoiceType,
    discount_global_percent: discountGlobalPercent,
    payment_term_id: ftDetails.paymentTermId || null,
    payment_method_id: ftDetails.paymentMethodId || null,
    bank_account_id: ftDetails.bankAccountId || null,
    due_date: ftDetails.dueDate || null,
    lines: lines.map((l) => ({
      product_id: l.productId || null,
      sale_unit_id: l.saleUnitId || null,
      service_id: l.serviceId || null,
      quantity: l.quantity,
      discount_percent: l.discountPercent || 0,
    })),
    payments: payments.map((p) => ({ payment_method_id: p.paymentMethodId, amount: p.amount })),
  });
  return res.data;
}


export async function createProFormaFromPos(posId, customerId, lines, discountGlobalPercent = 0) {
  const res = await apiClient.post('/pos/pro-forma/' + posId, {
    customer_id: customerId || null,
    discount_global_percent: discountGlobalPercent,
    lines: lines.map((l) => ({
      product_id: l.productId || null,
      sale_unit_id: l.saleUnitId || null,
      service_id: l.serviceId || null,
      quantity: l.quantity,
      discount_percent: l.discountPercent || 0,
    })),
  });
  return res.data;
}


export async function liquidatePendingInvoice(posId, proFormaId, targetInvoiceType, payments) {
  const res = await apiClient.post('/pos/liquidate/' + posId, {
    pro_forma_id: proFormaId,
    target_invoice_type: targetInvoiceType,
    payments: payments.map((p) => ({ payment_method_id: p.paymentMethodId, amount: p.amount })),
  });
  return res.data;
}

// The stock the point of sale sells from (its activity's warehouse), for the till to warn before checkout.
export async function getPosStock(posId) {
  const res = await apiClient.get('/pos/stock', { params: { pos_id: posId } });
  return res.data;
}

// The closing report (A4 PDF) of a closed session, as an object URL for the in-app PDF viewer.
export async function fetchClosingReportPdfBlob(sessionId) {
  const res = await apiClient.get('/pos/sessions/' + sessionId + '/closing-report', { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

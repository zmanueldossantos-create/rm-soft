// API calls for the Tesouraria module (motivos, movimentos de caixa,
// user <-> POS associations).
//
// ARCHITECTURE NOTE: this used to also cover a separate CashOffice entity
// ("Caixa Geral"). That concept has been retired - every Activity's default
// POS (PointOfSale.is_default) now covers that role, managed from the
// Activities/POS screens instead of a dedicated endpoint here.
import apiClient from './client';

export async function listCashMovementReasons(direction) {
  const res = await apiClient.get('/tesouraria/reasons', { params: direction ? { direction } : {} });
  return res.data;
}

export async function createCashMovementReason(name, direction) {
  const res = await apiClient.post('/tesouraria/reasons', { name, direction });
  return res.data;
}

export async function updateCashMovementReason(reasonId, name, direction) {
  const res = await apiClient.patch('/tesouraria/reasons/' + reasonId, { name, direction });
  return res.data;
}

export async function toggleCashMovementReasonStatus(reasonId) {
  const res = await apiClient.patch('/tesouraria/reasons/' + reasonId + '/toggle-status');
  return res.data;
}

export async function createCashMovement(payload) {
  const res = await apiClient.post('/tesouraria', payload);
  return res.data;
}

export async function listCashMovements(filters = {}) {
  const params = {};
  if (filters.posId) params.pos_id = filters.posId;
  const res = await apiClient.get('/tesouraria', { params });
  return res.data;
}

export async function listPendingReceptions(posId) {
  const res = await apiClient.get('/tesouraria/pending-receptions/' + posId);
  return res.data;
}

// lines: the notes and coins received ([{denomination_id, quantity}]) - a receiving till with billetage only
export async function receiveCashMovement(movementId, posId, lines = null) {
  const body = lines ? { denomination_lines: lines } : null;
  const res = await apiClient.post('/tesouraria/movements/' + movementId + '/receive', body, { params: { pos_id: posId } });
  return res.data;
}

// The notes and coins the sending till gave for a transfer - proposed at the reception.
export async function getTransferBilletage(movementId) {
  const res = await apiClient.get('/tesouraria/movements/' + movementId + '/billetage');
  return res.data;
}

export async function listPendingEmissions(posId) {
  const res = await apiClient.get('/tesouraria/pending-emissions/' + posId);
  return res.data;
}

export async function cancelCashMovement(movementId, posId) {
  await apiClient.delete('/tesouraria/movements/' + movementId, { params: { pos_id: posId } });
}

export async function getDailyReport(posId, dateFrom, dateTo) {
  const res = await apiClient.get('/tesouraria/daily-report', { params: { pos_id: posId, date_from: dateFrom, date_to: dateTo } });
  return res.data;
}

export async function getMyCashPointAssociation() {
  const res = await apiClient.get('/tesouraria/my-association');
  return res.data;
}

export async function listCashPointAssociations() {
  const res = await apiClient.get('/tesouraria/associations');
  return res.data;
}

export async function assignUserToCashPoint(userId, posId) {
  const res = await apiClient.put('/tesouraria/associations/' + userId, { pos_id: posId });
  return res.data;
}

export async function unassignUserFromCashPoint(userId) {
  await apiClient.delete('/tesouraria/associations/' + userId);
}


export async function listDocumentTypePaymentTermPreferences() {
  const res = await apiClient.get('/tesouraria/document-type-payment-term-preferences');
  return res.data;
}

export async function setDocumentTypePaymentTermPreference(documentTypeId, requiresPaymentTerm) {
  const res = await apiClient.put('/tesouraria/document-type-payment-term-preferences/' + documentTypeId, {
    requires_payment_term: requiresPaymentTerm,
  });
  return res.data;
}


export async function listPaymentMethodPreferences() {
  const res = await apiClient.get('/tesouraria/payment-method-preferences');
  return res.data;
}

export async function setPaymentMethodPreference(paymentMethodId, availableAtPos) {
  const res = await apiClient.put('/tesouraria/payment-method-preferences/' + paymentMethodId, { available_at_pos: availableAtPos });
  return res.data;
}

// The movements report (A4 PDF) of a till for the chosen dates - the very lines of the journal shown - as an
// object URL for the in-app PDF viewer.
export async function fetchDailyReportPdfBlob(posId, dateFrom, dateTo) {
  const res = await apiClient.get('/tesouraria/daily-report/pdf', {
    params: { pos_id: posId, date_from: dateFrom, date_to: dateTo },
    responseType: 'blob',
  });
  return URL.createObjectURL(res.data);
}

// ---------- Tesouraria overview (the manager's view of every till) ----------

export async function getTreasuryPosition() {
  const res = await apiClient.get('/tesouraria/overview/position');
  return res.data;
}

// filters: { dateFrom, dateTo, posId, movementType, status }
export async function listTreasuryMovements(filters = {}) {
  const params = {};
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  if (filters.posId) params.pos_id = filters.posId;
  if (filters.movementType) params.movement_type = filters.movementType;
  if (filters.status) params.movement_status = filters.status;
  const res = await apiClient.get('/tesouraria/overview/movements', { params });
  return res.data;
}

// filters: { dateFrom, dateTo, posId }
export async function listTreasuryClosings(filters = {}) {
  const params = {};
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  if (filters.posId) params.pos_id = filters.posId;
  const res = await apiClient.get('/tesouraria/overview/closings', { params });
  return res.data;
}

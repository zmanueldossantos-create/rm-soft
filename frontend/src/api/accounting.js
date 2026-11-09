// Contabilidade - the chart of accounts (plano de contas).
import apiClient from './client';

export async function getChart() {
  const res = await apiClient.get('/accounting/chart');
  return res.data;
}

// The first choice: 'PGC' (the system's reference list), 'PROPRIO' (then imported) or 'VAZIO'
export async function startChart(source) {
  const res = await apiClient.post('/accounting/chart/start', { source });
  return res.data;
}

// The Excel model, saved by the browser
export async function downloadChartTemplate() {
  const res = await apiClient.get('/accounting/chart/template', { responseType: 'blob' });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'plano_de_contas_modelo.xlsx';
  a.click();
  URL.revokeObjectURL(url);
}

// The filled model: { created, renamed, unchanged } - or a 422 with { detail, errors: [every wrong row] }
export async function importChart(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await apiClient.post('/accounting/chart/import', form, { headers: { 'Content-Type': 'multipart/form-data' } });
  return res.data;
}

export async function createAccount(code, name) {
  const res = await apiClient.post('/accounting/accounts', { code, name });
  return res.data;
}

export async function updateAccount(accountId, name, isActive) {
  const res = await apiClient.put('/accounting/accounts/' + accountId, { name, is_active: isActive });
  return res.data;
}

export async function deleteAccount(accountId) {
  await apiClient.delete('/accounting/accounts/' + accountId);
}

// «Contas por operação»: { operations: [{ key, group, label, kind, suggestion, account_id, account_code, account_name }],
// subaccount_per_customer, subaccount_per_supplier }
export async function getMappings() {
  const res = await apiClient.get('/accounting/mappings');
  return res.data;
}

export async function setMapping(key, accountId) {
  const res = await apiClient.put('/accounting/mappings/' + key, { account_id: accountId || null });
  return res.data;
}

export async function setMappingOptions(perCustomer, perSupplier) {
  const res = await apiClient.put('/accounting/mappings-options', { subaccount_per_customer: perCustomer, subaccount_per_supplier: perSupplier });
  return res.data;
}

export async function applyMappingSuggestions() {
  const res = await apiClient.post('/accounting/mappings/suggestions');
  return res.data;
}

// The sub-accounts still missing (one per bank account, till, customer, supplier): { created, missing_parent }
export async function syncSubaccounts() {
  const res = await apiClient.post('/accounting/subaccounts/sync');
  return res.data;
}

// ---------- Diários and lançamentos ----------

export async function getJournals() {
  const res = await apiClient.get('/accounting/journals');
  return res.data;
}

export async function createJournal(code, name) {
  const res = await apiClient.post('/accounting/journals', { code, name });
  return res.data;
}

export async function updateJournal(journalId, name, isActive) {
  const res = await apiClient.put('/accounting/journals/' + journalId, { name, is_active: isActive });
  return res.data;
}

export async function deleteJournal(journalId) {
  await apiClient.delete('/accounting/journals/' + journalId);
}

// filters: { journal_id, status, date_from, date_to, q } - empty ones are left out
export async function getEntries(filters = {}) {
  const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
  const res = await apiClient.get('/accounting/entries', { params });
  return res.data;
}

export async function getEntry(entryId) {
  const res = await apiClient.get('/accounting/entries/' + entryId);
  return res.data;
}

// payload: { journal_id, entry_date, description, document_ref, lines: [{account_id, description, debit, credit}], post }
export async function saveEntry(entryId, payload) {
  const res = entryId
    ? await apiClient.put('/accounting/entries/' + entryId, payload)
    : await apiClient.post('/accounting/entries', payload);
  return res.data;
}

export async function deleteEntry(entryId) {
  await apiClient.delete('/accounting/entries/' + entryId);
}

export async function reverseEntry(entryId, entryDate) {
  const res = await apiClient.post('/accounting/entries/' + entryId + '/reverse', { entry_date: entryDate });
  return res.data;
}

// ---------- the entries made by the system from the documents ----------

export async function getIntegration() {
  const res = await apiClient.get('/accounting/integration');
  return res.data;
}

export async function runIntegration() {
  const res = await apiClient.post('/accounting/integration/run');
  return res.data;
}

export async function setIntegrationStart(integrationStart) {
  const res = await apiClient.put('/accounting/integration/start', { integration_start: integrationStart });
  return res.data;
}

// the account of a treasury reason (motivo de tesouraria) - null: none
export async function setReasonAccount(reasonId, accountId) {
  const res = await apiClient.put('/accounting/reason-accounts/' + reasonId, { account_id: accountId || null });
  return res.data;
}

// ---------- reports: balancete and extrato de conta ----------

// filters: { date_from, date_to, max_level, all_accounts }
export async function getTrialBalance(filters) {
  const res = await apiClient.get('/accounting/trial-balance', { params: _params(filters) });
  return res.data;
}

export async function getAccountLedger(accountId, dateFrom, dateTo) {
  const res = await apiClient.get('/accounting/ledger/' + accountId, { params: { date_from: dateFrom, date_to: dateTo } });
  return res.data;
}

// a file of the reports, saved by the browser (Excel) or opened in a new tab (PDF)
export async function downloadAccountingFile(path, params, filename, open = false) {
  const res = await apiClient.get(path, { params: _params(params), responseType: 'blob' });
  const url = URL.createObjectURL(res.data);
  if (open) {
    window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    return;
  }
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function _params(filters) {
  return Object.fromEntries(Object.entries(filters || {}).filter(([, v]) => v !== '' && v !== null && v !== undefined && v !== false));
}

// the account of a stock movement type (the other side of the stock) - null: none
export async function setStockTypeAccount(movementTypeId, accountId) {
  const res = await apiClient.put('/accounting/stock-type-accounts/' + movementTypeId, { account_id: accountId || null });
  return res.data;
}

// 'PERMANENTE' (every stock movement posted at its cost) or 'INTERMITENTE' (none)
export async function setInventorySystem(system) {
  const res = await apiClient.put('/accounting/inventory-system', { inventory_system: system });
  return res.data;
}

// ---------- Balanço and Demonstração de resultados ----------

export async function getFinancialStatements(dateFrom, dateTo) {
  const res = await apiClient.get('/accounting/financial-statements', { params: { date_from: dateFrom, date_to: dateTo } });
  return res.data;
}

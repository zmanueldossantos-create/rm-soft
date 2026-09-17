// API calls for customers, scoped to the caller's company.
import apiClient from './client';

export async function listCustomers() {
  const res = await apiClient.get('/customers');
  return res.data;
}

export async function createCustomer(payload) {
  const res = await apiClient.post('/customers', payload);
  return res.data;
}

export async function updateCustomer(customerId, payload) {
  const res = await apiClient.patch('/customers/' + customerId, payload);
  return res.data;
}

export async function toggleCustomerStatus(customerId) {
  const res = await apiClient.patch('/customers/' + customerId + '/toggle-status');
  return res.data;
}

export async function suggestCustomerCode() {
  const res = await apiClient.get('/customers/suggest-code');
  return res.data;
}

export async function listCustomerBankLinks(customerId) {
  const res = await apiClient.get('/customers/' + customerId + '/bank-links');
  return res.data;
}

export async function addCustomerBankLink(customerId, companyBankAccountId) {
  const res = await apiClient.post('/customers/' + customerId + '/bank-links', { company_bank_account_id: companyBankAccountId });
  return res.data;
}

export async function removeCustomerBankLink(customerId, linkId) {
  await apiClient.delete('/customers/' + customerId + '/bank-links/' + linkId);
}

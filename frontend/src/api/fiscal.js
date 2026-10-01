// API calls for the fiscal Year/Period hierarchy (section 3.4 v6/v7).
// Year and month are computed server-side (strict sequential rule) -
// these calls never send a year/month value, only ids.
import apiClient from './client';

export async function getNextFiscalYear() {
  const res = await apiClient.get('/fiscal/years/next');
  return res.data;
}

export async function listFiscalYears() {
  const res = await apiClient.get('/fiscal/years');
  return res.data;
}

export async function createFiscalYear() {
  const res = await apiClient.post('/fiscal/years');
  return res.data;
}

export async function closeFiscalYear(yearId) {
  const res = await apiClient.patch('/fiscal/years/' + yearId + '/close');
  return res.data;
}

export async function getNextFiscalMonth(yearId) {
  const res = await apiClient.get('/fiscal/years/' + yearId + '/periods/next');
  return res.data;
}

export async function listFiscalPeriods(yearId) {
  const res = await apiClient.get('/fiscal/years/' + yearId + '/periods');
  return res.data;
}

export async function createFiscalPeriod(yearId) {
  const res = await apiClient.post('/fiscal/years/' + yearId + '/periods');
  return res.data;
}

export async function closeFiscalPeriod(periodId) {
  const res = await apiClient.patch('/fiscal/periods/' + periodId + '/close');
  return res.data;
}


export async function getCurrentPeriod() {
  const res = await apiClient.get('/fiscal/current-period');
  return res.data;
}

// Soft close (fecho parcial): automatic operations stop, internal late entries stay possible until the final close.
export async function partialCloseFiscalPeriod(periodId) {
  const res = await apiClient.patch('/fiscal/periods/' + periodId + '/partial-close');
  return res.data;
}

export async function partialCloseFiscalYear(yearId) {
  const res = await apiClient.patch('/fiscal/years/' + yearId + '/partial-close');
  return res.data;
}

// The periods an internal entry may be booked in (the active one and the soft-closed one).
export async function getPostingPeriods() {
  const res = await apiClient.get('/fiscal/posting-periods');
  return res.data;
}

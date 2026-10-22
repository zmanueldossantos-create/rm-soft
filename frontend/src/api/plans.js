// Planos and each company's contract (SUPER_ADMIN).
import apiClient from './client';

export async function getPlanCatalog() {
  return (await apiClient.get('/admin/plan-catalog')).data;
}

export async function listPlans() {
  return (await apiClient.get('/admin/plans')).data;
}

export async function savePlan(planId, payload) {
  const res = planId ? await apiClient.put('/admin/plans/' + planId, payload) : await apiClient.post('/admin/plans', payload);
  return res.data;
}

export async function getCompanyContract(companyId) {
  return (await apiClient.get('/admin/companies/' + companyId + '/contract')).data;
}

export async function saveCompanyContract(companyId, payload) {
  return (await apiClient.post('/admin/companies/' + companyId + '/contract', payload)).data;
}

// "65 000 Kz" - null: "-"
export function kz(value) {
  return value == null || value === '' ? '-' : Number(value).toLocaleString('pt-PT', { maximumFractionDigits: 2 }) + ' Kz';
}

// a limit: a number, or "Ilimitado" when the plan sets none
export function limitText(value) {
  return value == null ? 'Ilimitado' : String(value);
}

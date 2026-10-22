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

// ---------- Licenças (local installations)

export async function getLicenseInfo() {
  return (await apiClient.get('/admin/license-info')).data;
}

// «Gerar licença»: downloads the .lic file; a refusal comes back as a blob - turned back into the server's message
export async function generateLicense(companyId, installationCode) {
  try {
    const res = await apiClient.post('/admin/companies/' + companyId + '/license', { installation_code: installationCode }, { responseType: 'blob' });
    const match = /filename="([^"]+)"/.exec(res.headers['content-disposition'] || '');
    const url = URL.createObjectURL(res.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = match ? match[1] : 'licenca.lic';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    return link.download;
  } catch (err) {
    if (err.response?.data instanceof Blob) {
      try { err.response.data = JSON.parse(await err.response.data.text()); } catch { /* keep it */ }
    }
    throw err;
  }
}

export async function getCompanyLicense(companyId) {
  return (await apiClient.get('/admin/companies/' + companyId + '/license')).data;
}

export async function importCompanyLicense(companyId, content) {
  return (await apiClient.post('/admin/companies/' + companyId + '/license/import', { content })).data;
}

export async function getMyLicense() {
  return (await apiClient.get('/company/me/license')).data;
}

export async function importMyLicense(content) {
  return (await apiClient.post('/company/me/license', { content })).data;
}

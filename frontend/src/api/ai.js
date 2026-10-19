// The AI assistant's settings: the platform's provider and key, each company's switches (SUPER_ADMIN),
// the company's confirmations (gestor).
import apiClient from './client';

export async function getPlatformAi() {
  const res = await apiClient.get('/admin/ai-settings');
  return res.data;
}

// apiKey: null = unchanged, '' = removed
export async function updatePlatformAi({ provider, model, apiKey, monthlyLimit }) {
  const res = await apiClient.put('/admin/ai-settings', {
    provider: provider || null, model: model || null, api_key: apiKey, monthly_limit: monthlyLimit,
  });
  return res.data;
}

export async function testPlatformAi() {
  const res = await apiClient.post('/admin/ai-settings/test');
  return res.data;
}

export async function getCompanyAi(companyId) {
  const res = await apiClient.get('/admin/companies/' + companyId + '/ai-settings');
  return res.data;
}

export async function updateCompanyAi(companyId, switches) {
  const res = await apiClient.put('/admin/companies/' + companyId + '/ai-settings', switches);
  return res.data;
}

export async function getMyCompanyAi() {
  const res = await apiClient.get('/company/me/ai-settings');
  return res.data;
}

export async function updateMyCompanyAi(confirmations) {
  const res = await apiClient.put('/company/me/ai-settings', confirmations);
  return res.data;
}

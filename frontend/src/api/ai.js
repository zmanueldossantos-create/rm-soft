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

// ---------- The assistant itself

export async function getAssistantStatus() {
  const res = await apiClient.get('/ai/status');
  return res.data;
}

export async function listAiConversations() {
  const res = await apiClient.get('/ai/conversations');
  return res.data;
}

export async function getAiMessages(conversationId) {
  const res = await apiClient.get('/ai/conversations/' + conversationId + '/messages');
  return res.data;
}

export async function askAssistant(message, conversationId) {
  const res = await apiClient.post('/ai/ask', { message, conversation_id: conversationId || null }, { timeout: 180000 });
  return res.data;
}

// confirm: true = Confirmar, false = Cancelar
export async function decideAiAction(actionId, confirm) {
  const res = await apiClient.post('/ai/actions/' + actionId + '/' + (confirm ? 'confirm' : 'cancel'), null, { timeout: 120000 });
  return res.data;
}

// ---------- The company's email account

export async function getEmailSettings() {
  const res = await apiClient.get('/company/me/email-settings');
  return res.data;
}

// password: null = unchanged, '' = removed
export async function updateEmailSettings(settings) {
  const res = await apiClient.put('/company/me/email-settings', settings);
  return res.data;
}

export async function testEmailSettings(to) {
  const res = await apiClient.post('/company/me/email-settings/test', { to }, { timeout: 60000 });
  return res.data;
}

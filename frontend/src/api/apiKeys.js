import apiClient from './client';

// Definições da Empresa → Integração API (the gestor, option INTEGRACAO_API): the public API's access keys and journal.

export async function getApiKeys() {
  return (await apiClient.get('/company/me/api-keys')).data;
}

// the answer holds «key»: the only time the whole key is given
export async function createApiKey(data) {
  return (await apiClient.post('/company/me/api-keys', data)).data;
}

export async function revokeApiKey(id) {
  return (await apiClient.delete('/company/me/api-keys/' + id)).data;
}

export async function getApiJournal(keyId) {
  return (await apiClient.get('/company/me/api-keys/journal', { params: keyId ? { key_id: keyId } : {} })).data;
}

// Local installation: the link of this server to the RM SOFT relay (the site on the internet reaches it through it)
export async function saveRelay(data) {
  return (await apiClient.put('/company/me/api-keys/relay', data)).data;
}

export async function testRelay() {
  return (await apiClient.post('/company/me/api-keys/relay/test')).data;
}

export async function removeRelay() {
  return (await apiClient.delete('/company/me/api-keys/relay')).data;
}

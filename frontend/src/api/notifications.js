import apiClient from './client';

// Definições da Empresa → Notificações (the gestor): recipients, events, settings, history.

export async function getNotifications() {
  return (await apiClient.get('/company/me/notifications')).data;
}

export async function saveNotificationSettings(settings) {
  return (await apiClient.put('/company/me/notifications/settings', settings)).data;
}

export async function createRecipient(data) {
  return (await apiClient.post('/company/me/notifications/recipients', data)).data;
}

export async function updateRecipient(id, data) {
  return (await apiClient.put('/company/me/notifications/recipients/' + id, data)).data;
}

export async function deleteRecipient(id) {
  await apiClient.delete('/company/me/notifications/recipients/' + id);
}

export async function testRecipient(id) {
  return (await apiClient.post('/company/me/notifications/recipients/' + id + '/test')).data;
}

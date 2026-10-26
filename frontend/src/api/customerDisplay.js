import apiClient from './client';

// Ecrã do cliente (option ECRA_CLIENTE): the customer's screen of an activity - welcome message and pictures.

export async function getCustomerDisplay(activityId) {
  return (await apiClient.get('/customer-display/' + activityId)).data;
}

export async function saveCustomerDisplay(activityId, settings) {
  return (await apiClient.put('/customer-display/' + activityId, settings)).data;
}

export async function addCustomerDisplayImage(activityId, file) {
  const form = new FormData();
  form.append('file', file);
  return (await apiClient.post('/customer-display/' + activityId + '/images', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })).data;
}

export async function deleteCustomerDisplayImage(imageId) {
  return (await apiClient.delete('/customer-display/images/' + imageId)).data;
}

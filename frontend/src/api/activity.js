// API calls for Activities (business lines / points of sale within the company).
import apiClient from './client';
export async function listActivities() {
  const res = await apiClient.get('/activities');
  return res.data;
}
export async function createActivity(moduleId, name) {
  const res = await apiClient.post('/activities', { module_id: moduleId, name });
  return res.data;
}
export async function updateActivity(activityId, name) {
  const res = await apiClient.patch('/activities/' + activityId, { name });
  return res.data;
}
export async function toggleActivityStatus(activityId) {
  const res = await apiClient.patch('/activities/' + activityId + '/toggle-status');
  return res.data;
}


export async function listPointsOfSale(activityId) {
  const res = await apiClient.get('/activities/' + activityId + '/pos');
  return res.data;
}

export async function createPointOfSale(activityId, name, billetageEnabled = false, printing = {}) {
  const res = await apiClient.post('/activities/' + activityId + '/pos', { activity_id: activityId, name, billetage_enabled: billetageEnabled, ...printing });
  return res.data;
}

export async function updatePointOfSale(posId, name, billetageEnabled = false, printing = {}) {
  const res = await apiClient.patch('/activities/pos/' + posId, { name, billetage_enabled: billetageEnabled, ...printing });
  return res.data;
}

export async function togglePosStatus(posId) {
  const res = await apiClient.patch('/activities/pos/' + posId + '/toggle-status');
  return res.data;
}

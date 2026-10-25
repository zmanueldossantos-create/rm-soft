import apiClient from './client';

// «Pedidos» (SUPER_ADMIN): the demonstration requests of the public site.

export async function getDemoRequestsSummary() {
  return (await apiClient.get('/admin/demo-requests/summary')).data;
}

export async function listDemoRequests(status) {
  return (await apiClient.get('/admin/demo-requests', { params: status ? { status_filter: status } : {} })).data;
}

export async function updateDemoRequest(id, status, notes) {
  return (await apiClient.patch('/admin/demo-requests/' + id, { status, notes: notes || null })).data;
}

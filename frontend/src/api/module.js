// API calls for the Module catalog and company module grants (SUPER_ADMIN only).
import apiClient from './client';

export async function listModules() {
  const res = await apiClient.get('/admin/modules');
  return res.data;
}

export async function createModule(name, description) {
  const res = await apiClient.post('/admin/modules', { name, description: description || null });
  return res.data;
}

export async function updateModule(moduleId, name, description) {
  const res = await apiClient.patch('/admin/modules/' + moduleId, { name, description: description || null });
  return res.data;
}

export async function toggleModuleStatus(moduleId) {
  const res = await apiClient.patch('/admin/modules/' + moduleId + '/toggle-status');
  return res.data;
}

export async function getCompanyModules(companyId) {
  const res = await apiClient.get('/admin/companies/' + companyId + '/modules');
  return res.data;
}

export async function setCompanyModules(companyId, moduleIds) {
  const res = await apiClient.put('/admin/companies/' + companyId + '/modules', moduleIds);
  return res.data;
}

// SUPER_ADMIN global view: capabilities, sectors (modules), companies and impact.
export async function getAdminOverview() {
  const res = await apiClient.get('/admin/overview');
  return res.data;
}

export async function setModuleCapabilities(moduleId, capabilities) {
  const res = await apiClient.put('/admin/modules/' + moduleId + '/capabilities', { capabilities });
  return res.data;
}

export async function resetModuleCapabilities(moduleId) {
  const res = await apiClient.post('/admin/modules/' + moduleId + '/capabilities/reset');
  return res.data;
}

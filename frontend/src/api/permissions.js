import apiClient from './client';

export async function getPermissionMatrix() {
  const res = await apiClient.get('/permissions/matrix');
  return res.data;
}

export async function setRolePermission(role, permissionId, granted) {
  const res = await apiClient.post('/permissions/matrix', { role, permission_id: permissionId, granted });
  return res.data;
}


export async function getMyPermissions() {
  const res = await apiClient.get('/permissions/mine');
  return res.data;
}

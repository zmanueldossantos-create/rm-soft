// API calls for user (team member) management - GESTOR only.
import apiClient from './client';

export async function listUsers() {
  const res = await apiClient.get('/auth/users');
  return res.data;
}

export async function createTeamUser(fullName, phoneNumber, password, role) {
  const res = await apiClient.post('/auth/users', {
    full_name: fullName,
    phone_number: phoneNumber,
    password,
    role,
  });
  return res.data;
}

export async function updateTeamUser(userId, fullName, phoneNumber, role) {
  const res = await apiClient.patch('/auth/users/' + userId, {
    full_name: fullName,
    phone_number: phoneNumber,
    role,
  });
  return res.data;
}

export async function toggleUserStatus(userId) {
  const res = await apiClient.patch('/auth/users/' + userId + '/toggle-status');
  return res.data;
}


export async function resetUserPassword(userId, newPassword) {
  const res = await apiClient.post('/auth/users/' + userId + '/reset-password', {
    new_password: newPassword,
  });
  return res.data;
}

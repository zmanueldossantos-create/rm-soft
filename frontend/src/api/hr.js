import apiClient from './client';

// Recursos Humanos: the employees' files and the company's HR tables (capability HR)
export async function listEmployees(params = {}) {
  const res = await apiClient.get('/hr/employees', { params });
  return res.data;
}

export async function getEmployeeOptions() {
  const res = await apiClient.get('/hr/employees/options');
  return res.data;
}

export async function createEmployee(payload) {
  const res = await apiClient.post('/hr/employees', payload);
  return res.data;
}

export async function updateEmployee(employeeId, payload) {
  const res = await apiClient.put('/hr/employees/' + employeeId, payload);
  return res.data;
}

export async function registerDeparture(employeeId, payload) {
  const res = await apiClient.post('/hr/employees/' + employeeId + '/departure', payload);
  return res.data;
}

export async function readmitEmployee(employeeId, hiredOn) {
  const res = await apiClient.post('/hr/employees/' + employeeId + '/readmission', { hired_on: hiredOn });
  return res.data;
}

export async function listHrReferences() {
  const res = await apiClient.get('/hr/references');
  return res.data;
}

export async function createHrReference(kind, name) {
  const res = await apiClient.post('/hr/references', { kind, name });
  return res.data;
}

export async function updateHrReference(referenceId, name, isActive) {
  const res = await apiClient.put('/hr/references/' + referenceId, { name, is_active: isActive });
  return res.data;
}

export async function deleteHrReference(referenceId) {
  await apiClient.delete('/hr/references/' + referenceId);
}

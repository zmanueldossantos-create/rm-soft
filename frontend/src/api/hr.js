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

const MULTIPART = { headers: { 'Content-Type': 'multipart/form-data' } };

// the photo and the documents of the file - personal data, read with the session (never a public address)
export async function fetchEmployeePhotoUrl(employeeId) {
  const res = await apiClient.get('/hr/employees/' + employeeId + '/photo', { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

export async function uploadEmployeePhoto(employeeId, file) {
  const form = new FormData();
  form.append('file', file);
  const res = await apiClient.put('/hr/employees/' + employeeId + '/photo', form, MULTIPART);
  return res.data;
}

export async function deleteEmployeePhoto(employeeId) {
  await apiClient.delete('/hr/employees/' + employeeId + '/photo');
}

export async function listEmployeeDocuments(employeeId) {
  const res = await apiClient.get('/hr/employees/' + employeeId + '/documents');
  return res.data;
}

export async function addEmployeeDocument(employeeId, { documentTypeId, description, deliveredOn, expiresOn, file }) {
  const form = new FormData();
  if (documentTypeId) form.append('document_type_id', documentTypeId);
  if (description) form.append('description', description);
  if (deliveredOn) form.append('delivered_on', deliveredOn);
  if (expiresOn) form.append('expires_on', expiresOn);
  if (file) form.append('file', file);
  const res = await apiClient.post('/hr/employees/' + employeeId + '/documents', form, MULTIPART);
  return res.data;
}

export async function deleteEmployeeDocument(employeeId, documentId) {
  await apiClient.delete('/hr/employees/' + employeeId + '/documents/' + documentId);
}

export async function fetchEmployeeDocumentUrl(employeeId, documentId) {
  const res = await apiClient.get('/hr/employees/' + employeeId + '/documents/' + documentId + '/file', { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

export async function fetchEmployeePdfUrl(employeeId) {
  const res = await apiClient.get('/hr/employees/' + employeeId + '/pdf', { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

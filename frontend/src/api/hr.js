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

// the payroll settings (step 2): INSS, IRT tables, rubricas, the rubricas of an employee and his payslip simulation
export async function getPayrollSettings() {
  return (await apiClient.get('/hr/payroll/settings')).data;
}

export async function updatePayrollSettings(payload) {
  return (await apiClient.put('/hr/payroll/settings', payload)).data;
}

export async function listIrtTables() {
  return (await apiClient.get('/hr/payroll/irt-tables')).data;
}

export async function saveIrtTable(tableId, payload) {
  return (tableId ? await apiClient.put('/hr/payroll/irt-tables/' + tableId, payload) : await apiClient.post('/hr/payroll/irt-tables', payload)).data;
}

export async function deleteIrtTable(tableId) {
  await apiClient.delete('/hr/payroll/irt-tables/' + tableId);
}

export async function listPayrollItems() {
  return (await apiClient.get('/hr/payroll/items')).data;
}

export async function savePayrollItem(itemId, payload) {
  return (itemId ? await apiClient.put('/hr/payroll/items/' + itemId, payload) : await apiClient.post('/hr/payroll/items', payload)).data;
}

export async function deletePayrollItem(itemId) {
  await apiClient.delete('/hr/payroll/items/' + itemId);
}

export async function checkFormula(formula, code) {
  return (await apiClient.post('/hr/payroll/formula-check', { formula, code })).data;
}

export async function getEmployeePayrollItems(employeeId) {
  return (await apiClient.get('/hr/employees/' + employeeId + '/payroll-items')).data;
}

export async function setEmployeePayrollItems(employeeId, items) {
  return (await apiClient.put('/hr/employees/' + employeeId + '/payroll-items', { items })).data;
}

export async function simulatePayslip(employeeId, monthValues = {}) {
  return (await apiClient.post('/hr/employees/' + employeeId + '/simulation', { month_values: monthValues })).data;
}

// the work calendar and the absence types (step 3a / 3b)
export async function listHolidays(year) {
  return (await apiClient.get('/hr/calendar/holidays', { params: { year } })).data;
}

export async function generateHolidays(year) {
  return (await apiClient.post('/hr/calendar/holidays/generate', null, { params: { year } })).data;
}

export async function saveHoliday(holidayId, payload) {
  return (holidayId ? await apiClient.put('/hr/calendar/holidays/' + holidayId, payload) : await apiClient.post('/hr/calendar/holidays', payload)).data;
}

export async function deleteHoliday(holidayId) {
  await apiClient.delete('/hr/calendar/holidays/' + holidayId);
}

export async function listAbsenceTypes() {
  return (await apiClient.get('/hr/absence-types')).data;
}

export async function saveAbsenceType(typeId, payload) {
  return (typeId ? await apiClient.put('/hr/absence-types/' + typeId, payload) : await apiClient.post('/hr/absence-types', payload)).data;
}

export async function deleteAbsenceType(typeId) {
  await apiClient.delete('/hr/absence-types/' + typeId);
}

// the absences (step 3c)
export async function listAbsences(params = {}) {
  return (await apiClient.get('/hr/absences', { params })).data;
}

export async function getAbsenceOptions() {
  return (await apiClient.get('/hr/absences/options')).data;
}

export async function getAbsenceMap(year, month, departmentId) {
  return (await apiClient.get('/hr/absences/map', { params: { year, month, department_id: departmentId || undefined } })).data;
}

export async function saveAbsence(absenceId, payload) {
  return (absenceId ? await apiClient.put('/hr/absences/' + absenceId, payload) : await apiClient.post('/hr/absences', payload)).data;
}

export async function decideAbsence(absenceId, action, note) {
  return (await apiClient.post('/hr/absences/' + absenceId + '/' + action, { note: note || null })).data;
}

export async function attachAbsenceDocument(absenceId, file) {
  const form = new FormData();
  form.append('file', file);
  return (await apiClient.post('/hr/absences/' + absenceId + '/document', form, MULTIPART)).data;
}

export async function countDays(start, end, workingDays = true) {
  return (await apiClient.get('/hr/calendar/count', { params: { start, end, working_days: workingDays } })).data;
}

export async function cancelDeparture(employeeId) {
  return (await apiClient.delete('/hr/employees/' + employeeId + '/departure')).data;
}

// the holiday balance (step 3d)
export async function getVacations(year) {
  return (await apiClient.get('/hr/vacations', { params: { year } })).data;
}

export async function listVacationAdjustments(employeeId, year) {
  return (await apiClient.get('/hr/vacations/adjustments', { params: { employee_id: employeeId, year } })).data;
}

export async function addVacationAdjustment(payload) {
  return (await apiClient.post('/hr/vacations/adjustments', payload)).data;
}

export async function deleteVacationAdjustment(adjustmentId) {
  await apiClient.delete('/hr/vacations/adjustments/' + adjustmentId);
}

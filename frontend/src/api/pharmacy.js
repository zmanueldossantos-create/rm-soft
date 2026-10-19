// Farmácia: the context of the product form and the managed list of pharmaceutical forms.
import apiClient from './client';

// { enabled, medicine_exemption: {id, code, name} | null, forms: [{id, name, is_active}] }
export async function getPharmacyContext() {
  const res = await apiClient.get('/pharmacy/context');
  return res.data;
}

export async function listPharmaceuticalForms() {
  const res = await apiClient.get('/pharmacy/forms');
  return res.data;
}

export async function createPharmaceuticalForm(name) {
  const res = await apiClient.post('/pharmacy/forms', { name });
  return res.data;
}

export async function updatePharmaceuticalForm(formId, name) {
  const res = await apiClient.patch('/pharmacy/forms/' + formId, { name });
  return res.data;
}

export async function togglePharmaceuticalFormStatus(formId) {
  const res = await apiClient.patch('/pharmacy/forms/' + formId + '/toggle-status');
  return res.data;
}

// The dispensing regimes of a medicine - what the sale will ask.
export const DISPENSING_REGIMES = [
  { value: 'LIVRE', label: 'Venda livre' },
  { value: 'RECEITA', label: 'Sujeito a receita médica' },
  { value: 'RECEITA_ESPECIAL', label: 'Receita especial (psicotrópicos e estupefacientes)' },
];

// The words a medicine is found by at the counter: its substance (every brand of it) and its dosage.
export function medicineSearchText(p) {
  return p && p.is_medicine ? ((p.active_substance || '') + ' ' + (p.dosage || '')).toLowerCase() : '';
}

// "Paracetamol · Comprimido · 500 mg" - shown under a medicine's name.
export function medicineSummary(p) {
  if (!p || !p.is_medicine) return '';
  return [p.active_substance, p.pharmaceutical_form_name, p.dosage].filter(Boolean).join(' · ');
}

// ---------- Registers (livraison 3)

// Where one lot came from and where it went - every sector (a recall).
export async function traceLot(lotId) {
  const res = await apiClient.get('/pharmacy/lots/' + lotId + '/trace');
  return res.data;
}

export async function fetchLotTracePdf(lotId) {
  const res = await apiClient.get('/pharmacy/lots/' + lotId + '/trace/pdf', { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

function registerParams(filters) {
  const params = { date_from: filters.dateFrom, date_to: filters.dateTo };
  if (filters.special === 'especial') params.special = true;
  if (filters.special === 'normal') params.special = false;
  if (filters.q && filters.q.trim()) params.q = filters.q.trim();
  return params;
}

export async function listPrescriptions(filters) {
  const res = await apiClient.get('/pharmacy/prescriptions', { params: registerParams(filters) });
  return res.data;
}

export async function fetchPrescriptionsPdf(filters) {
  const res = await apiClient.get('/pharmacy/prescriptions/pdf', { params: registerParams(filters), responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

export async function getPsychotropicRegister(filters) {
  const res = await apiClient.get('/pharmacy/psychotropics', { params: { date_from: filters.dateFrom, date_to: filters.dateTo } });
  return res.data;
}

export async function fetchPsychotropicsPdf(filters) {
  const res = await apiClient.get('/pharmacy/psychotropics/pdf', { params: { date_from: filters.dateFrom, date_to: filters.dateTo }, responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

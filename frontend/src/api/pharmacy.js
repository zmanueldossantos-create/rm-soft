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

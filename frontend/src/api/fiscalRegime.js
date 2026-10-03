// API calls for fiscal regimes (SUPER_ADMIN only).
import apiClient from './client';

export async function listFiscalRegimes() {
  const res = await apiClient.get('/admin/fiscal-regimes');
  return res.data;
}

export async function createFiscalRegime(name, description, allowsNor, allowsRed, allowsIse, allowsInt, allowsOut, requiredExemptionId) {
  const res = await apiClient.post('/admin/fiscal-regimes', {
    name,
    description: description || null,
    allows_nor: allowsNor,
    allows_red: allowsRed,
    allows_ise: allowsIse,
    allows_int: allowsInt,
    allows_out: allowsOut,
    required_exemption_id: requiredExemptionId || null,
  });
  return res.data;
}

export async function updateFiscalRegime(regimeId, name, description, allowsNor, allowsRed, allowsIse, allowsInt, allowsOut, requiredExemptionId) {
  const res = await apiClient.patch('/admin/fiscal-regimes/' + regimeId, {
    name,
    description: description || null,
    allows_nor: allowsNor,
    allows_red: allowsRed,
    allows_ise: allowsIse,
    allows_int: allowsInt,
    allows_out: allowsOut,
    required_exemption_id: requiredExemptionId || null,
  });
  return res.data;
}

export async function toggleFiscalRegimeStatus(regimeId) {
  const res = await apiClient.patch('/admin/fiscal-regimes/' + regimeId + '/toggle-status');
  return res.data;
}

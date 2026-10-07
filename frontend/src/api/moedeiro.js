// API calls for the Moedeiro (billetage) feature.
import apiClient from './client';

export async function listDenominations(currencyId) {
  const res = await apiClient.get('/moedeiro/denominations', { params: currencyId ? { currency_id: currencyId } : {} });
  return res.data;
}

export async function recordDenominationCount(cashSessionId, countType, lines) {
  const res = await apiClient.post('/moedeiro/counts', {
    cash_session_id: cashSessionId,
    count_type: countType,
    lines: lines.map((l) => ({ denomination_id: l.denominationId, quantity: l.quantity })),
  });
  return res.data;
}

export async function getLatestDenominationCount(cashSessionId, countType) {
  const res = await apiClient.get('/moedeiro/counts/latest', { params: { cash_session_id: cashSessionId, count_type: countType } });
  return res.data;
}

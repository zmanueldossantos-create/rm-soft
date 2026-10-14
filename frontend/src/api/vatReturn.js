// Apuramento do IVA (vat_return_service): the VAT of a month - charged on sales, deductible on purchases, the result.
import apiClient from './client';

export async function listVatPeriods() {
  return (await apiClient.get('/vat-return/periods')).data;
}

export async function getVatReturn(periodId) {
  return (await apiClient.get('/vat-return/' + periodId)).data;
}

// the documents behind one line of the return (side: sales | purchases)
export async function listVatDocuments(periodId, side, line) {
  const params = { side, tax_code: line.tax_code, rate: line.rate };
  if (line.exemption_code) params.exemption_code = line.exemption_code;
  return (await apiClient.get('/vat-return/' + periodId + '/documents', { params })).data;
}

export async function fetchVatReturnPdfBlob(periodId) {
  const res = await apiClient.get('/vat-return/' + periodId + '/pdf', { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

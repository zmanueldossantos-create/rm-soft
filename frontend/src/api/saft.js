// API calls for SAF-T export ("Modo Fatura", section 4.2).
import apiClient from './client';

// includePurchases: the purchase invoices of the month too - the file is then of the type Q (acquisitions
// integrated with the invoicing) instead of F.
export async function downloadSaftFile(year, month, includePurchases = false) {
  const res = await apiClient.get('/saf-t/export', {
    params: { year, month, include_purchases: includePurchases },
    responseType: 'blob',
  });
  const blobUrl = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = blobUrl;
  link.download = `SAFT_${year}${String(month).padStart(2, '0')}.xml`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(blobUrl);
}

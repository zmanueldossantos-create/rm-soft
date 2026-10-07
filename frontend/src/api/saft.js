// API calls for SAF-T export ("Modo Fatura", section 4.2).
import apiClient from './client';

export async function downloadSaftFile(year, month) {
  const res = await apiClient.get('/saf-t/export', {
    params: { year, month },
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

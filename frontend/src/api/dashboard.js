// API calls for the dashboard summary.
import apiClient from './client';

export async function getDashboardSummary() {
  const res = await apiClient.get('/dashboard/summary');
  return res.data;
}

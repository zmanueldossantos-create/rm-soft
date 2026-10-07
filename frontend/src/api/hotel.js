import apiClient from './client';

export async function checkIn(bookingId, posId = null) {
  const params = posId ? { pos_id: posId } : {};
  const res = await apiClient.post('/hotel/bookings/' + bookingId + '/check-in', null, { params });
  return res.data;
}

export async function checkOut(bookingId, payments = []) {
  const res = await apiClient.post('/hotel/bookings/' + bookingId + '/check-out', { payments });
  return res.data;
}

export async function getOccupancyHistory(filters = {}) {
  const params = {};
  if (filters.activityId) params.activity_id = filters.activityId;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  const res = await apiClient.get('/hotel/occupancy-history', { params });
  return res.data;
}

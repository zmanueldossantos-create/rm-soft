import apiClient from './client';

export async function checkIn(bookingId, posId = null) {
  const params = posId ? { pos_id: posId } : {};
  const res = await apiClient.post('/hotel/bookings/' + bookingId + '/check-in', null, { params });
  return res.data;
}

// Only a stay with nothing left to pay: a stay with articles is paid at the till (closing its account concludes it).
export async function checkOut(bookingId) {
  const res = await apiClient.post('/hotel/bookings/' + bookingId + '/check-out');
  return res.data;
}

// New end of a stay in progress - the room-rate line of its account follows.
export async function extendStay(bookingId, endsAt) {
  const res = await apiClient.post('/hotel/bookings/' + bookingId + '/extend', { ends_at: endsAt });
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

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

// A prepaid passage: { resource_id, service_id, pos_id, payments: [{ payment_method_id, amount }], guest_name, party_size }
export async function walkIn(payload) {
  const res = await apiClient.post('/hotel/walk-in', payload);
  return res.data;
}

// New end of a stay in progress - the room-rate line of its account follows.
export async function extendStay(bookingId, endsAt) {
  const res = await apiClient.post('/hotel/bookings/' + bookingId + '/extend', { ends_at: endsAt });
  return res.data;
}

import apiClient from './client';

export async function checkIn(bookingId, posId = null) {
  const params = posId ? { pos_id: posId } : {};
  const res = await apiClient.post('/hotel/bookings/' + bookingId + '/check-in', null, { params });
  return res.data;
}

// Only a stay with nothing left to pay: a stay with articles is paid at the till (closing its account concludes it).
// A passage past its paid time: payload { pos_id, payments, terminal_id } charges its excess, { waive_reason } lets it go.
export async function checkOut(bookingId, payload = null) {
  const res = await apiClient.post('/hotel/bookings/' + bookingId + '/check-out', payload);
  return res.data;
}

// The excess of a passage at its exit: { minutes, slices } (slices of its rate to charge)
export async function getOverstay(bookingId) {
  const res = await apiClient.get('/hotel/bookings/' + bookingId + '/overstay');
  return res.data;
}

// A prepaid passage: { resource_id, service_id, pos_id, payments: [{ payment_method_id, amount }], guest_name, party_size }
export async function walkIn(payload) {
  const res = await apiClient.post('/hotel/walk-in', payload);
  return res.data;
}

// New end of a stay in progress - the room-rate line of its account follows.
// A passage (paid at its Entrada) pays its extra time at once: extra { pos_id, payments, terminal_id }.
export async function extendStay(bookingId, endsAt, extra = {}) {
  const res = await apiClient.post('/hotel/bookings/' + bookingId + '/extend', { ends_at: endsAt, ...extra });
  return res.data;
}

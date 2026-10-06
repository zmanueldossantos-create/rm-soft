import apiClient from './client';

// The kitchen screen (point 34c): the orders still in the kitchen and the last ones done today.
export async function getKitchenBoard() {
  const res = await apiClient.get('/kitchen/board');
  return res.data;
}

// start / ready / refuse / quantity on one dish - returns the updated board.
export async function kitchenLineAction(lineId, action, quantity = null) {
  const res = await apiClient.post('/kitchen/lines/' + lineId + '/' + action, { quantity });
  return res.data;
}

// start_all / ready_all on one order - returns the updated board.
export async function kitchenOrderAction(orderId, action) {
  const res = await apiClient.post('/kitchen/orders/' + orderId + '/' + action);
  return res.data;
}

// The kitchen orders of a period (YYYY-MM-DD, at most 92 days), with the history of every dish.
export async function getKitchenHistory(dateFrom, dateTo) {
  const res = await apiClient.get('/kitchen/history', { params: { date_from: dateFrom, date_to: dateTo } });
  return res.data;
}

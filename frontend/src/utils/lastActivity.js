// Remembers, per user and per device, the last activity picked on the resource screens
// (Recursos, Reservas, Histórico). A convenience only: browser storage may be empty or blocked.

const KEY_PREFIX = 'rmsoft.lastResourceActivity.';

export function readLastActivity(userId) {
  if (!userId) return '';
  try {
    return window.localStorage.getItem(KEY_PREFIX + userId) || '';
  } catch {
    return '';
  }
}

export function writeLastActivity(userId, activityId) {
  if (!userId || !activityId) return;
  try {
    window.localStorage.setItem(KEY_PREFIX + userId, activityId);
  } catch {
    // storage unavailable: nothing to remember
  }
}

// The remembered activity if it is still among the active ones, else null.
export function rememberedActivity(userId, activeActivities) {
  const id = readLastActivity(userId);
  return id ? activeActivities.find((a) => a.id === id) || null : null;
}

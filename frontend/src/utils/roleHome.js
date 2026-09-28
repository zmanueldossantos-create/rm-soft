// Where each role lands after login, and where a route guard sends a user who is refused a page.
// A role not listed here (GESTOR, CONTABILISTA, SUPER_ADMIN, and any future role added before
// this map is updated) uses the general /dashboard. Add an entry when a role gets its own landing
// screen - and keep it to a page that role can actually open.
export const ROLE_HOME = {
  CAIXA: '/caixa',
  ARMAZENISTA: '/stock/dashboard',
};

export function homeFor(role) {
  return ROLE_HOME[role] || '/dashboard';
}
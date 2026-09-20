import { useAuthStore } from '../store/authStore';

// Returns can(code). Once the list loaded from /permissions/mine is available it decides for
// everybody, GESTOR included: the backend removes from that list every permission whose
// capability the company's sectors do not give (see app.core.capabilities), so a GESTOR only
// sees what its company can actually use. While the list is still loading (null) the GESTOR is
// trusted - no flash of an empty menu - and every other role sees nothing gated. The backend
// remains the real gatekeeper: this only decides what the UI shows.
export function useCan() {
  const role = useAuthStore((state) => state.user?.role);
  const permissions = useAuthStore((state) => state.permissions);
  const can = (code) => (Array.isArray(permissions) ? permissions.includes(code) : role === 'GESTOR');
  // can.any(codes) - true if the user holds at least one of the given codes.
  can.any = (codes) => codes.some((code) => can(code));
  return can;
}

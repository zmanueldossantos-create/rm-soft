import { useAuthStore } from '../store/authStore';

// Returns can(code). Once the list loaded from /permissions/mine is available it decides for
// everybody: the backend removes from that list every permission whose capability the company's
// sectors do not give (see app.core.capabilities), so a GESTOR only sees what its company can
// actually use. While the list is still loading (null) EVERY role, GESTOR included, sees nothing
// gated - a brief empty/partial menu beats a page firing a call the company's sectors do not
// actually allow (see the products:manage / Servicos incident: a screen's initial Promise.all
// fired listProducts() before the real answer arrived, because a since-removed default trusted
// GESTOR early). Any effect that fetches gated data on mount should still wait for permissions to
// be an array before deciding what to fetch, since can() flips from false to its real value only
// on the next render.
export function useCan() {
  const permissions = useAuthStore((state) => state.permissions);
  const can = (code) => (Array.isArray(permissions) ? permissions.includes(code) : false);
  // can.any(codes) - true if the user holds at least one of the given codes.
  can.any = (codes) => codes.some((code) => can(code));
  return can;
}

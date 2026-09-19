import { useAuthStore } from '../store/authStore';

// Returns can(code). GESTOR always passes (the backend applies the same rule);
// every other role needs the code in the list loaded from /permissions/mine
// after login. While that list is still loading (null), non-GESTOR users see
// nothing gated - no flash of items they are not allowed to use. The backend
// remains the real gatekeeper: this only decides what the UI shows.
export function useCan() {
  const role = useAuthStore((state) => state.user?.role);
  const permissions = useAuthStore((state) => state.permissions);
  const can = (code) => role === 'GESTOR' || (Array.isArray(permissions) && permissions.includes(code));
  // can.any(codes) - true if the user holds at least one of the given codes.
  can.any = (codes) => codes.some((code) => can(code));
  return can;
}
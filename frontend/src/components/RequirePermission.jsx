import { Navigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuthStore } from '../store/authStore';

// Route guard: shows the page only if the user holds `perm` (or any code of `anyOf`), otherwise
// sends them to the dashboard (which is never guarded - guarding it could loop). Once the list
// from /permissions/mine is loaded it decides for everybody, GESTOR included (a sector the
// company does not have removes its permissions from the GESTOR's list too). While it is still
// loading (null) the GESTOR is trusted and every other role sees a spinner instead of being
// redirected - otherwise reloading /caixa would bounce a CAIXA to the dashboard before the list
// arrives. SUPER_ADMIN has no company permissions at all. The backend stays the real gatekeeper.
export default function RequirePermission({ perm, anyOf, children }) {
  const role = useAuthStore((state) => state.user?.role);
  const permissions = useAuthStore((state) => state.permissions);

  if (!role || role === 'SUPER_ADMIN') return <Navigate to="/dashboard" replace />;
  if (permissions === null) {
    if (role === 'GESTOR') return children;
    return (
      <div className="flex items-center justify-center py-24 text-text-muted text-sm">
        <Loader2 size={18} className="animate-spin mr-2" />
        A carregar...
      </div>
    );
  }
  const codes = anyOf || [perm];
  return codes.some((code) => permissions.includes(code)) ? children : <Navigate to="/dashboard" replace />;
}

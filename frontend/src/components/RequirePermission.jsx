import { Navigate, useLocation } from 'react-router-dom';
import { Loader2, Lock } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { homeFor } from '../utils/roleHome';

// Route guard: shows the page only if the user holds `perm` (or any code of `anyOf`).
//
// A refused user is sent to THEIR OWN landing page (homeFor(role): /caixa for a CAIXA, /dashboard
// for a GESTOR...) - never blindly to /dashboard, which is itself guarded for roles without
// dashboard:view. If the refused page IS that landing page there is nowhere left to send them, so
// an explicit "no access" message is rendered instead of redirecting: that is what keeps this
// guard loop-free, whatever permissions a company grants or revokes.
//
// SUPER_ADMIN has no company permissions at all: it is sent to /dashboard, except on a route that
// opts in with allowSuperAdmin (the dashboard itself, which has a SUPER_ADMIN view of its own).
//
// Once the list from /permissions/mine is loaded it decides for everybody, GESTOR included (a
// sector the company does not have removes its permissions from the GESTOR's list too). While it
// is still loading (null) the GESTOR is trusted and every other role sees a spinner instead of
// being redirected - otherwise reloading /caixa would bounce a CAIXA away before the list
// arrives. The backend stays the real gatekeeper.
export default function RequirePermission({ perm, anyOf, allowSuperAdmin = false, children }) {
  const role = useAuthStore((state) => state.user?.role);
  const permissions = useAuthStore((state) => state.permissions);
  const location = useLocation();

  if (!role) return <Navigate to="/login" replace />;
  if (role === 'SUPER_ADMIN') return allowSuperAdmin ? children : <Navigate to="/dashboard" replace />;

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
  if (codes.some((code) => permissions.includes(code))) return children;

  const home = homeFor(role);
  if (location.pathname !== home) return <Navigate to={home} replace />;

  return (
    <div className="flex flex-col items-center justify-center py-24 text-center gap-3">
      <Lock size={28} className="text-text-muted" />
      <p className="text-text-primary font-medium">Sem acesso a esta pagina</p>
      <p className="text-text-muted text-sm">O seu perfil nao tem permissao para ver este ecra. Contacte o gestor.</p>
    </div>
  );
}
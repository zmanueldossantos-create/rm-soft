// Opens a support access on the company's address: the one-time code of the link (from Empresas → «Entrar como
// suporte») becomes a session with the gestor's screens. Outside the protected routes: no session exists yet.
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { LifeBuoy, Loader2 } from 'lucide-react';
import apiClient from '../api/client';
import { useAuthStore } from '../store/authStore';
import { extractErrorMessage } from '../utils/errors';
import { homeFor } from '../utils/roleHome';

export default function Suporte() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const logout = useAuthStore((state) => state.logout);
  const [error, setError] = useState('');

  useEffect(() => {
    const code = params.get('code');
    if (!code) {
      setError('Link de suporte incompleto - volte a entrar a partir de Empresas.');
      return;
    }
    logout(); // whatever session this browser had (the admin's, in a local installation) is replaced
    (async () => {
      try {
        const { data } = await apiClient.post('/auth/support/redeem', { code });
        const me = await apiClient.get('/auth/me', { headers: { Authorization: 'Bearer ' + data.access_token } });
        login(data.access_token, data.refresh_token, me.data);
        navigate(homeFor(me.data.role), { replace: true });
      } catch (err) {
        setError(extractErrorMessage(err, 'Não foi possível abrir o acesso de suporte'));
      }
    })();
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary p-5">
      <div className="w-full max-w-md bg-bg-elevated border border-border rounded-lg p-8 text-center">
        <LifeBuoy size={28} className="text-amber-500 mx-auto mb-3" />
        <h1 className="font-display font-semibold text-lg text-text-primary mb-2">Acesso de suporte RM SOFT</h1>
        {error ? (
          <>
            <p className="text-danger text-sm mb-4">{error}</p>
            <Link to="/login" className="text-accent text-sm font-medium">Ir para o início de sessão</Link>
          </>
        ) : (
          <p className="text-text-muted text-sm flex items-center justify-center gap-2"><Loader2 size={16} className="animate-spin" /> A abrir a empresa...</p>
        )}
      </div>
    </div>
  );
}

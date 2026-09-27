import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Phone, Lock, Eye, EyeOff, LogIn, Mail } from 'lucide-react';
import apiClient from '../api/client';
import { useAuthStore } from '../store/authStore';
import { extractErrorMessage } from '../utils/errors';

// Where each role lands right after login - a role not listed here (GESTOR, CONTABILISTA,
// SUPER_ADMIN, and any future role added before this map is updated) falls back to /dashboard.
// Add an entry here when a role gets its own landing screen instead of the general overview.
const ROLE_HOME = {
  CAIXA: '/caixa',
  ARMAZENISTA: '/stock/dashboard',
};

export default function Login() {
  const [phoneSuffix, setPhoneSuffix] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);

  const supplierName = import.meta.env.VITE_SUPPLIER_NAME;
  const supplierEmail = import.meta.env.VITE_SUPPLIER_EMAIL;
  const supplierPhone = import.meta.env.VITE_SUPPLIER_PHONE;
  const appVersion = import.meta.env.VITE_APP_VERSION;

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);

    // Defensive - the field only expects the local number (the "+244"
    // prefix is shown as a separate fixed badge), but people sometimes type
    // the full number out of habit; strip a redundant leading +244 so we
    // never accidentally send "+244+244923456789" to the backend.
    const cleanedSuffix = phoneSuffix.replace(/\s/g, '').replace(/^\+?244/, '');
    const fullPhone = '+244' + cleanedSuffix;

    try {
      const loginRes = await apiClient.post('/auth/login', {
        phone_number: fullPhone,
        password,
      });

      const { access_token, refresh_token } = loginRes.data;

      const meRes = await apiClient.get('/auth/me', {
        headers: { Authorization: 'Bearer ' + access_token },
      });

      login(access_token, refresh_token, meRes.data);
      navigate(ROLE_HOME[meRes.data.role] || '/dashboard');
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao ligar ao servidor'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary p-5 relative overflow-hidden">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_0%,rgba(212,165,55,0.08),transparent_55%)]" />

      <div className="relative w-full max-w-[460px]">
        <div className="relative bg-bg-elevated rounded-lg overflow-hidden shadow-2xl ticket-edge">
          <div className="px-10 pt-9 pb-8">
            <p className="font-mono text-[11px] tracking-[0.14em] uppercase text-accent mb-2">
              Painel de gestão
            </p>
            <h1 className="font-display font-bold text-[26px] tracking-tight text-text-primary mb-1.5">
              RM SOFT
            </h1>
            <p className="text-text-muted text-sm mb-8">
              Inicie sessão com o seu número de telefone
            </p>

            <form onSubmit={handleSubmit} className="flex flex-col">
              <label htmlFor="phone" className="text-[11px] font-medium uppercase tracking-wide text-text-muted mt-1 mb-1.5">
                Número de telefone
              </label>
              <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent focus-within:ring-1 focus-within:ring-accent/30 transition-all">
                <span className="flex items-center gap-1.5 bg-bg-elevated px-3.5 py-3 text-text-muted border-r border-border font-mono text-sm whitespace-nowrap">
                  <Phone size={15} />
                  +244
                </span>
                <input
                  id="phone"
                  type="tel"
                  placeholder="923 456 789"
                  value={phoneSuffix}
                  onChange={(e) => setPhoneSuffix(e.target.value)}
                  required
                  className="flex-1 bg-transparent border-none px-3 py-3 text-text-primary font-mono text-sm outline-none placeholder:text-text-muted/50"
                />
              </div>

              <label htmlFor="password" className="text-[11px] font-medium uppercase tracking-wide text-text-muted mt-4 mb-1.5">
                Palavra-passe
              </label>
              <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent focus-within:ring-1 focus-within:ring-accent/30 transition-all">
                <span className="flex items-center pl-3.5 text-text-muted">
                  <Lock size={15} />
                </span>
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="flex-1 bg-transparent border-none px-2.5 py-3 text-text-primary font-mono text-sm outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? 'Ocultar palavra-passe' : 'Mostrar palavra-passe'}
                  className="flex items-center justify-center px-3.5 h-full text-text-muted hover:text-text-primary transition-colors"
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>

              {error && (
                <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] mt-4 rounded-r">
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={loading || !phoneSuffix || !password}
                className="mt-7 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3.5 flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
              >
                <LogIn size={18} />
                {loading ? 'A entrar...' : 'Entrar'}
              </button>
            </form>

            <fieldset className="mt-6 border border-border rounded-md px-4 pb-3 pt-2 bg-bg-inset/50">
              <legend className="font-mono text-[10px] uppercase tracking-wide text-text-muted px-1.5">
                Fornecedor
              </legend>
              <div className="flex items-center justify-between mb-1.5">
                <p className="font-display font-semibold text-[13px] text-text-primary">
                  {supplierName}
                </p>
                <span className="font-mono text-[10px] text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded">
                  v{appVersion}
                </span>
              </div>
              <div className="flex items-center justify-between text-[12px] text-text-muted font-mono">
                <span className="flex items-center gap-1.5">
                  <Mail size={12} className="text-accent shrink-0" />
                  {supplierEmail}
                </span>
                <span className="flex items-center gap-1.5">
                  <Phone size={12} className="text-accent shrink-0" />
                  {supplierPhone}
                </span>
              </div>
            </fieldset>
          </div>
        </div>
      </div>
    </div>
  );
}

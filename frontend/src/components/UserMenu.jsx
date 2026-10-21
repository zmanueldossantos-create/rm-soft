import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronUp, Eye, EyeOff, KeyRound, Loader2, LogOut } from 'lucide-react';
import Modal from './Modal';
import apiClient from '../api/client';
import { useAuthStore } from '../store/authStore';
import { extractErrorMessage } from '../utils/errors';

// The connected user, at the bottom left of every screen: a circle with the initials; a click opens a small menu
// upwards (the name, the phone, «Alterar palavra-passe», «Terminar sessão»). Esc or a click elsewhere closes it.

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 pr-10 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors';

// "Manuel dos Santos" -> "MS"; one word -> its first two letters
export function initialsOf(name) {
  const words = (name || '').trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

export default function UserMenu() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const [open, setOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onClick); document.removeEventListener('keydown', onKey); };
  }, [open]);

  if (!user) return null;
  const inSupport = !!user.support; // a support access: the platform user's own password is not changed from here

  return (
    <div ref={ref} className="relative min-w-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 min-w-0 rounded-md px-1.5 py-1 hover:bg-bg-inset transition-colors cursor-pointer"
      >
        <span className="w-7 h-7 shrink-0 rounded-full bg-accent text-white text-[11px] font-semibold flex items-center justify-center">
          {initialsOf(user.full_name)}
        </span>
        <span className="truncate text-text-primary">{user.full_name}</span>
        <span className="text-accent shrink-0">({user.role})</span>
        <ChevronUp size={14} className={'shrink-0 transition-transform ' + (open ? '' : 'rotate-180')} />
      </button>

      {open && (
        <div role="menu" className="absolute bottom-full left-0 mb-2 w-64 bg-bg-elevated border border-border rounded-lg shadow-xl overflow-hidden">
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border">
            <span className="w-10 h-10 shrink-0 rounded-full bg-accent text-white text-sm font-semibold flex items-center justify-center">
              {initialsOf(user.full_name)}
            </span>
            <div className="min-w-0">
              <div className="text-[13px] font-semibold text-text-primary truncate">{user.full_name}</div>
              <div className="text-[11px] text-text-muted font-mono truncate">{user.phone_number}</div>
            </div>
          </div>
          {!inSupport && (
            <button
              type="button"
              role="menuitem"
              onClick={() => { setOpen(false); setPasswordOpen(true); }}
              className="w-full flex items-center gap-2.5 px-4 py-2.5 text-[13px] text-text-primary hover:bg-bg-inset transition-colors cursor-pointer"
            >
              <KeyRound size={15} className="text-accent" /> Alterar palavra-passe
            </button>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={() => { logout(); navigate('/login'); }}
            className="w-full flex items-center gap-2.5 px-4 py-2.5 text-[13px] text-text-primary hover:bg-bg-inset hover:text-danger transition-colors cursor-pointer"
          >
            <LogOut size={15} /> Terminar sessão
          </button>
        </div>
      )}

      <ChangePasswordModal open={passwordOpen} onClose={() => setPasswordOpen(false)} />
    </div>
  );
}

function PasswordField({ label, value, onChange, show, autoFocus = false }) {
  return (
    <div>
      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{label}</label>
      <input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        autoFocus={autoFocus}
        required
        className={inputClass}
      />
    </div>
  );
}

function ChangePasswordModal({ open, onClose }) {
  const user = useAuthStore((state) => state.user);
  const login = useAuthStore((state) => state.login);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  // a fresh form each time it opens
  useEffect(() => {
    if (open) { setCurrent(''); setNext(''); setConfirm(''); setShow(false); setError(null); setDone(false); }
  }, [open]);

  const mismatch = confirm.length > 0 && next !== confirm;

  async function submit(e) {
    e.preventDefault();
    if (next !== confirm) { setError('A confirmação não coincide com a nova palavra-passe'); return; }
    setSaving(true);
    setError(null);
    try {
      const { data } = await apiClient.post('/auth/me/password', { current_password: current, new_password: next });
      login(data.access_token, data.refresh_token, user); // this device keeps working with its new session
      setDone(true);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível alterar a palavra-passe'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Alterar palavra-passe" subtitle={user?.full_name}>
      {done ? (
        <div className="flex flex-col gap-4">
          <div className="bg-success/10 border-l-2 border-success text-success px-3.5 py-2.5 text-[13px] rounded-r">
            Palavra-passe alterada. As sessões abertas noutros aparelhos foram terminadas.
          </div>
          <button type="button" onClick={onClose}
            className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer">
            Fechar
          </button>
        </div>
      ) : (
        <form onSubmit={submit} className="flex flex-col gap-4">
          <PasswordField label="Palavra-passe atual *" value={current} onChange={setCurrent} show={show} autoFocus />
          <PasswordField label="Nova palavra-passe *" value={next} onChange={setNext} show={show} />
          <div>
            <PasswordField label="Confirmar a nova palavra-passe *" value={confirm} onChange={setConfirm} show={show} />
            <p className={'text-[11px] mt-1 ' + (mismatch ? 'text-danger' : 'text-text-muted')}>
              {mismatch ? 'Não coincide com a nova palavra-passe' : 'Mínimo 8 caracteres'}
            </p>
          </div>
          <button type="button" onClick={() => setShow((v) => !v)}
            className="self-start flex items-center gap-1.5 text-[12px] text-text-muted hover:text-accent cursor-pointer">
            {show ? <EyeOff size={14} /> : <Eye size={14} />} {show ? 'Ocultar' : 'Mostrar'} as palavras-passe
          </button>
          <p className="text-[12px] text-text-muted">
            As sessões abertas noutros aparelhos serão terminadas; este aparelho continua ligado.
          </p>
          {error && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>
          )}
          <button
            type="submit"
            disabled={saving || !current || next.length < 8 || next !== confirm}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <KeyRound size={17} />}
            {saving ? 'A guardar...' : 'Alterar palavra-passe'}
          </button>
        </form>
      )}
    </Modal>
  );
}

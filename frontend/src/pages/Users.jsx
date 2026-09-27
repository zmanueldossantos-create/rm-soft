import { useState, useEffect, useMemo } from 'react';
import { UserCog, Plus, Loader2, Search, KeyRound, Pencil } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { listUsers, createTeamUser, updateTeamUser, toggleUserStatus, resetUserPassword } from '../api/users';
import { extractErrorMessage } from '../utils/errors';
import { useAuthStore } from '../store/authStore';

function ToggleSwitch({ checked, onChange, disabled }) {
  const trackClass = 'relative w-10 h-5.5 rounded-full transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ' + (checked ? 'bg-success' : 'bg-border');
  const knobClass = 'absolute top-0.5 left-0.5 w-4.5 h-4.5 bg-white rounded-full transition-transform ' + (checked ? 'translate-x-4.5' : 'translate-x-0');
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={onChange} disabled={disabled} className={trackClass}>
      <span className={knobClass} />
    </button>
  );
}

const ROLE_OPTIONS = [
  { value: 'GESTOR', label: 'Gestor' },
  { value: 'CAIXA', label: 'Caixa' },
  { value: 'ARMAZENISTA', label: 'Armazenista' },
  { value: 'CONTABILISTA', label: 'Contabilista' },
];

const emptyForm = { fullName: '', phone: '', password: '', role: '' };

export default function Users() {
  const currentUser = useAuthStore((state) => state.user);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [togglingId, setTogglingId] = useState(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [resetModalOpen, setResetModalOpen] = useState(false);
  const [resetTarget, setResetTarget] = useState(null);
  const [resetPassword, setResetPassword] = useState('');
  const [resetSaving, setResetSaving] = useState(false);
  const [resetError, setResetError] = useState('');
  const [resetSuccess, setResetSuccess] = useState(false);

  function openResetModal(user) {
    setResetTarget(user);
    setResetPassword('');
    setResetError('');
    setResetSuccess(false);
    setResetModalOpen(true);
  }

  async function handleResetPassword(e) {
    e.preventDefault();
    setResetError('');
    setResetSaving(true);
    try {
      await resetUserPassword(resetTarget.id, resetPassword);
      setResetSuccess(true);
    } catch (err) {
      setResetError(extractErrorMessage(err, 'Erro ao redefinir palavra-passe'));
    } finally {
      setResetSaving(false);
    }
  }

  async function loadUsers() {
    setLoading(true);
    setError('');
    try {
      const data = await listUsers();
      setUsers(data);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar utilizadores'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  const filteredUsers = useMemo(() => {
    const base = !search.trim()
      ? users
      : users.filter((u) => {
          const q = search.toLowerCase();
          return u.full_name.toLowerCase().includes(q) || u.phone_number.includes(q);
        });
    // GESTOR always appears first, regardless of creation order.
    return [...base].sort((a, b) => (a.role === 'GESTOR' ? -1 : b.role === 'GESTOR' ? 1 : 0));
  }, [users, search]);

  function openCreateModal() {
    setEditingId(null);
    setForm(emptyForm);
    setFormError('');
    setModalOpen(true);
  }

  function openEditModal(user) {
    setEditingId(user.id);
    setForm({
      fullName: user.full_name,
      phone: user.phone_number.startsWith('+244') ? user.phone_number.slice(4) : user.phone_number,
      password: '',
      role: user.role,
    });
    setFormError('');
    setModalOpen(true);
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      const fullPhone = form.phone.startsWith('+') ? form.phone : '+244' + form.phone.replace(/\s/g, '');
      if (editingId) {
        await updateTeamUser(editingId, form.fullName, fullPhone, form.role);
      } else {
        await createTeamUser(form.fullName, fullPhone, form.password, form.role);
      }
      setModalOpen(false);
      await loadUsers();
    } catch (err) {
      setFormError(extractErrorMessage(err, editingId ? 'Erro ao guardar utilizador' : 'Erro ao criar utilizador'));
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(userId) {
    setTogglingId(userId);
    try {
      await toggleUserStatus(userId);
      await loadUsers();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado do utilizador'));
    } finally {
      setTogglingId(null);
    }
  }

  const isFormValid = form.fullName && form.phone && form.role && (editingId || form.password.length >= 8);

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-center justify-between mb-1">
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
          <UserCog size={22} className="text-accent" />
          Utilizadores
        </h2>
      </div>
      <p className="text-text-muted text-sm mb-6">
        Gerir a equipa com acesso ao sistema - caixas, armazenistas e contabilistas
      </p>

      <div className="flex items-center justify-between gap-3 flex-wrap mb-5">
        <div className="relative max-w-sm w-full sm:w-auto sm:min-w-[260px]">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Pesquisar por nome ou numero..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
          />
        </div>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer"
        >
          <Plus size={17} />
          Novo utilizador
        </button>
      </div>

      <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
        {loading && (
          <div className="flex items-center justify-center py-16 text-text-muted text-sm">
            <Loader2 size={18} className="animate-spin mr-2" />
            A carregar...
          </div>
        )}

        {error && (
          <div className="px-6 py-4 text-danger text-sm bg-danger/10">{error}</div>
        )}

        {!loading && !error && filteredUsers.length === 0 && (
          <div className="text-center py-16 text-text-muted text-sm flex flex-col items-center gap-3">
            <span>{search ? 'Nenhum utilizador encontrado' : 'Nenhum utilizador registado ainda'}</span>
            <Search size={22} className="text-text-muted/40" />
          </div>
        )}

        {!loading && !error && filteredUsers.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Nome</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Telefone</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Função</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Estado</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((u) => (
                  <tr key={u.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                    <td className="px-6 py-4 font-display font-medium text-text-primary">{u.full_name}</td>
                    <td className="px-6 py-4 font-mono text-text-muted">{u.phone_number}</td>
                    <td className="px-6 py-4 font-mono text-text-muted">{u.role}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2.5">
                        <ToggleSwitch
                          checked={u.is_active}
                          disabled={togglingId === u.id || u.id === currentUser?.id}
                          onChange={() => handleToggle(u.id)}
                        />
                        <span className={'text-[12px] font-medium ' + (u.is_active ? 'text-success' : 'text-text-muted')}>
                          {u.is_active ? 'Ativo' : 'Inativo'}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {u.id !== currentUser?.id && (
                          <button
                            onClick={() => openEditModal(u)}
                            aria-label="Editar utilizador"
                            title="Editar utilizador"
                            className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer"
                          >
                            <Pencil size={14} />
                          </button>
                        )}
                        <button
                          onClick={() => openResetModal(u)}
                          aria-label="Redefinir palavra-passe"
                          title="Redefinir palavra-passe"
                          className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer"
                        >
                          <KeyRound size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title={editingId ? 'Editar utilizador' : 'Novo utilizador'}>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome completo *</label>
            <input
              value={form.fullName}
              onChange={(e) => updateField('fullName', e.target.value)}
              required
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Número de telefone *</label>
            <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
              <span className="px-3 py-2.5 text-text-muted border-r border-border font-mono text-sm">+244</span>
              <input
                value={form.phone}
                onChange={(e) => updateField('phone', e.target.value)}
                placeholder="923 456 789"
                required
                className="flex-1 bg-transparent border-none px-3 py-2.5 text-sm text-text-primary font-mono outline-none"
              />
            </div>
          </div>
          {!editingId && (
          <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Palavra-passe *</label>
            <input
                type="password"
                value={form.password}
                onChange={(e) => updateField('password', e.target.value)}
                required
                minLength={8}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
            <p className="text-[11px] text-text-muted mt-1">Mínimo 8 caracteres</p>
          </div>
          )}
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Função *</label>
            <Select
              value={form.role}
              onChange={(val) => updateField('role', val)}
              options={ROLE_OPTIONS}
              placeholder="Selecionar função"
            />
          </div>

          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
              {formError}
            </div>
          )}

          <button
            type="submit"
            disabled={saving || !isFormValid}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : (editingId ? <Pencil size={17} /> : <Plus size={17} />)}
            {saving ? 'A guardar...' : (editingId ? 'Guardar alteracoes' : 'Criar utilizador')}
          </button>
        </form>
      </Modal>

      <Modal open={resetModalOpen} onClose={() => setResetModalOpen(false)} title={'Redefinir palavra-passe' + (resetTarget ? ' - ' + resetTarget.full_name : '')}>
        {resetSuccess ? (
          <div className="flex flex-col gap-4">
            <div className="bg-success/10 border-l-2 border-success text-success px-3.5 py-2.5 text-[13px] rounded-r">
              Palavra-passe redefinida com sucesso.
            </div>
            <button
              type="button"
              onClick={() => setResetModalOpen(false)}
              className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer"
            >
              Fechar
            </button>
          </div>
        ) : (
          <form onSubmit={handleResetPassword} className="flex flex-col gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nova palavra-passe *</label>
              <input
                type="password"
                value={resetPassword}
                onChange={(e) => setResetPassword(e.target.value)}
                required
                minLength={8}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
              />
              <p className="text-[11px] text-text-muted mt-1">Mínimo 8 caracteres</p>
            </div>
            {resetError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
                {resetError}
              </div>
            )}
            <button
              type="submit"
              disabled={resetSaving || resetPassword.length < 8}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
            >
              {resetSaving ? <Loader2 size={17} className="animate-spin" /> : <KeyRound size={17} />}
              {resetSaving ? 'A guardar...' : 'Redefinir palavra-passe'}
            </button>
          </form>
        )}
      </Modal>
    </main>
  );
}



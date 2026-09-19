import { useState, useEffect } from 'react';
import { ShieldCheck, Loader2 } from 'lucide-react';
import { getPermissionMatrix, setRolePermission } from '../api/permissions';
import { extractErrorMessage } from '../utils/errors';

const ROLES = ['GESTOR', 'CAIXA', 'ARMAZENISTA', 'CONTABILISTA'];
const ROLE_LABELS = { GESTOR: 'Gestor', CAIXA: 'Caixa', ARMAZENISTA: 'Armazenista', CONTABILISTA: 'Contabilista' };

export default function Permissoes() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [savingKey, setSavingKey] = useState(null);

  useEffect(() => {
    loadMatrix();
  }, []);

  async function loadMatrix() {
    setLoading(true);
    setError('');
    try {
      setEntries(await getPermissionMatrix());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar permissoes'));
    } finally {
      setLoading(false);
    }
  }

  async function handleToggle(entry, role) {
    if (role === 'GESTOR') return;
    const key = entry.id + role;
    const currentlyGranted = entry.granted_roles.includes(role);
    setSavingKey(key);
    setError('');
    try {
      await setRolePermission(role, entry.id, !currentlyGranted);
      setEntries((prev) => prev.map((e) => {
        if (e.id !== entry.id) return e;
        const granted_roles = currentlyGranted
          ? e.granted_roles.filter((r) => r !== role)
          : [...e.granted_roles, role];
        return { ...e, granted_roles };
      }));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar permissao'));
    } finally {
      setSavingKey(null);
    }
  }

  const categories = [...new Set(entries.map((e) => e.category))];

  return (
    <main className="max-w-[1200px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <ShieldCheck size={22} className="text-accent" />
        Permissoes
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Configure o que cada perfil pode fazer. Apenas o modulo Consumo Interno usa este sistema por agora (piloto) - os restantes modulos continuam com permissoes fixas.
      </p>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : (
        categories.map((category) => (
          <div key={category} className="bg-bg-elevated border border-border rounded-lg overflow-hidden mb-5">
            <div className="px-4 py-2.5 border-b border-border bg-bg-inset">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">{category}</p>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
                  <th className="text-left px-4 py-2.5">Permissao</th>
                  {ROLES.map((role) => (
                    <th key={role} className="text-center px-4 py-2.5">{ROLE_LABELS[role]}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {entries.filter((e) => e.category === category).map((entry) => (
                  <tr key={entry.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-2.5 text-text-primary">{entry.label}</td>
                    {ROLES.map((role) => {
                      const key = entry.id + role;
                      const granted = entry.granted_roles.includes(role);
                      return (
                        <td key={role} className="px-4 py-2.5 text-center">
                          {savingKey === key ? (
                            <Loader2 size={14} className="animate-spin text-accent inline" />
                          ) : (
                            <input
                              type="checkbox"
                              checked={granted}
                              onChange={() => handleToggle(entry, role)}
                              disabled={role === 'GESTOR'}
                              title={role === 'GESTOR' ? 'O perfil Gestor tem sempre todas as permissoes' : undefined}
                              className={'w-4 h-4 accent-accent ' + (role === 'GESTOR' ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer')}
                            />
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))
      )}
    </main>
  );
}

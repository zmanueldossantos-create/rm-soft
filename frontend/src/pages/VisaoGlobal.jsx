import { useState, useEffect } from 'react';
import { LayoutGrid, Loader2, RefreshCw, AlertTriangle, RotateCcw } from 'lucide-react';
import { getAdminOverview, setModuleCapabilities, resetModuleCapabilities, setCompanyModules } from '../api/module';
import { extractErrorMessage } from '../utils/errors';

const TABS = [
  { key: 'setores', label: 'Setores' },
  { key: 'empresas', label: 'Empresas' },
  { key: 'funcoes', label: 'Funcoes' },
  { key: 'impacto', label: 'Impacto' },
];

const CHIP_ACTIVE = 'text-success bg-success/10';
const CHIP_OFF = 'text-text-muted bg-bg-inset';
const CHIP_ALERT = 'text-danger bg-danger/10';
const CHIP_WARN = 'text-accent bg-accent/10';

function Chip({ className, title, children }) {
  return (
    <span title={title} className={'inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ' + className}>
      {children}
    </span>
  );
}

// Every capability that needs `code`, directly or through another one - unchecking a
// capability must also uncheck these, otherwise the server would switch it back on.
function dependentsOf(code, capabilities) {
  const removed = new Set([code]);
  let changed = true;
  while (changed) {
    changed = false;
    capabilities.forEach((c) => {
      if (!removed.has(c.code) && c.requires.some((r) => removed.has(r))) {
        removed.add(c.code);
        changed = true;
      }
    });
  }
  return removed;
}

export default function VisaoGlobal() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('setores');
  const [savingKey, setSavingKey] = useState(null);

  async function load() {
    setError('');
    try {
      setOverview(await getAdminOverview());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar a visao global'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function run(key, action, fallback) {
    setSavingKey(key);
    setError('');
    try {
      await action();
      await load();
    } catch (err) {
      setError(extractErrorMessage(err, fallback));
    } finally {
      setSavingKey(null);
    }
  }

  function toggleModuleCapability(module, code) {
    const current = new Set(module.capabilities);
    if (current.has(code)) dependentsOf(code, overview.capabilities).forEach((c) => current.delete(c));
    else current.add(code);
    run('m:' + module.id + code, () => setModuleCapabilities(module.id, Array.from(current)), 'Erro ao atualizar as funcoes do setor');
  }

  function resetModule(module) {
    run('r:' + module.id, () => resetModuleCapabilities(module.id), 'Erro ao repor as funcoes padrao');
  }

  function toggleCompanySector(company, module) {
    const ids = company.modules.filter((m) => m.is_enabled).map((m) => m.id);
    const next = ids.includes(module.id) ? ids.filter((id) => id !== module.id) : [...ids, module.id];
    run('c:' + company.id + module.id, () => setCompanyModules(company.id, next), 'Erro ao atualizar setores da empresa');
  }

  if (loading && !overview) {
    return (
      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
        <div className="flex items-center justify-center py-24 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      </main>
    );
  }

  const caps = overview ? overview.capabilities : [];
  const capLabel = Object.fromEntries(caps.map((c) => [c.code, c.label]));
  const busy = savingKey !== null;

  function renderSetores() {
    return (
      <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
              <th className="text-left px-4 py-2.5">Setor</th>
              {caps.map((c) => (
                <th key={c.code} className="text-center px-3 py-2.5">{c.label}</th>
              ))}
              <th className="text-center px-3 py-2.5">Empresas</th>
              <th className="px-3 py-2.5" />
            </tr>
          </thead>
          <tbody>
            {overview.modules.map((m) => (
              <tr key={m.id} className="border-b border-border last:border-0">
                <td className="px-4 py-2.5">
                  <p className="text-text-primary font-medium">{m.name}</p>
                  <p className="text-[11px] text-text-muted font-mono">{m.code || 'personalizado'}</p>
                  {!m.is_ready && <Chip className={CHIP_WARN} title={m.ready_note}>Em desenvolvimento</Chip>}
                  {!m.is_active && <Chip className={CHIP_OFF}>Inativo</Chip>}
                  {!m.is_ready && m.ready_note && <p className="text-[11px] text-text-muted mt-1">{m.ready_note}</p>}
                </td>
                {caps.map((c) => (
                  <td key={c.code} className="text-center px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={m.capabilities.includes(c.code)}
                      disabled={busy}
                      onChange={() => toggleModuleCapability(m, c.code)}
                      className="w-4 h-4 accent-accent cursor-pointer disabled:opacity-50"
                    />
                  </td>
                ))}
                <td className="text-center px-3 py-2.5 font-mono text-text-muted">{m.companies_granted}</td>
                <td className="px-3 py-2.5 text-right">
                  {m.code && (
                    <button
                      type="button"
                      onClick={() => resetModule(m)}
                      disabled={busy}
                      className="inline-flex items-center gap-1.5 text-[12px] text-text-muted hover:text-accent cursor-pointer disabled:opacity-50"
                    >
                      <RotateCcw size={12} />
                      Repor padrao
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  function renderEmpresas() {
    const sectors = overview.modules.filter((m) => m.is_active);
    return (
      <div className="flex flex-col gap-4">
        {overview.companies.map((co) => {
          const grantedIds = new Set(co.modules.filter((m) => m.is_enabled).map((m) => m.id));
          return (
            <div key={co.id} className="bg-bg-elevated border border-border rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3 flex-wrap">
                <p className="font-display font-semibold text-text-primary">{co.name}</p>
                {!co.is_active && <Chip className={CHIP_OFF}>Empresa inativa</Chip>}
              </div>
              <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1.5">Setores</p>
              <div className="flex flex-wrap gap-x-5 gap-y-2 mb-4">
                {sectors.map((m) => {
                  const granted = grantedIds.has(m.id);
                  const blocked = !m.is_ready && !granted;
                  return (
                    <label
                      key={m.id}
                      title={blocked ? (m.ready_note || 'Em desenvolvimento') : undefined}
                      className={'flex items-center gap-2 text-[13px] select-none ' + (blocked ? 'opacity-50 cursor-not-allowed text-text-muted' : 'cursor-pointer text-text-primary')}
                    >
                      <input
                        type="checkbox"
                        checked={granted}
                        disabled={busy || blocked}
                        onChange={() => toggleCompanySector(co, m)}
                        className="w-4 h-4 accent-accent"
                      />
                      {m.name}
                      {!m.is_ready && <span className="text-[10px] text-accent">(em desenvolvimento)</span>}
                    </label>
                  );
                })}
              </div>
              <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1.5">Funcoes (alem do nucleo, sempre ativo)</p>
              <div className="flex flex-wrap gap-1.5 mb-4">
                {co.capabilities.map((cp) => {
                  const label = capLabel[cp.code] || cp.code;
                  if (cp.active) {
                    return (
                      <Chip key={cp.code} className={CHIP_ACTIVE} title={'Via ' + cp.via.join(', ')}>
                        {label}{cp.data_count > 0 ? ' - ' + cp.data_count + ' registos' : ''}
                      </Chip>
                    );
                  }
                  if (cp.inactive_with_data) {
                    return (
                      <Chip key={cp.code} className={CHIP_ALERT} title="Funcao inativa mas ja tem dados">
                        <AlertTriangle size={11} />
                        {label} - {cp.data_count} registos
                      </Chip>
                    );
                  }
                  return <Chip key={cp.code} className={CHIP_OFF}>{label}</Chip>;
                })}
              </div>
              <p className="text-[11px] uppercase tracking-wide text-text-muted mb-1.5">Atividades</p>
              {co.activities.length === 0 ? (
                <p className="text-text-muted text-[12px]">Nenhuma atividade configurada</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {co.activities.map((a, i) => (
                    <Chip key={a.name + i} className={a.is_active ? CHIP_ACTIVE : CHIP_OFF} title={a.is_active ? 'Ativa' : 'Inativa'}>
                      {a.name}{a.module && a.module !== a.name ? ' (' + a.module + ')' : ''}
                    </Chip>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  function renderFuncoes() {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-bg-elevated border border-border rounded-lg p-4 lg:col-span-2">
          <p className="font-display font-semibold text-text-primary mb-1">{overview.core.label} (sempre ativo)</p>
          <p className="text-text-muted text-[13px] mb-2">Disponivel para todas as empresas, seja qual for o setor.</p>
          <details>
            <summary className="text-[12px] text-text-muted cursor-pointer">{overview.core.permissions.length} permissoes</summary>
            <p className="text-[11px] text-text-muted font-mono mt-1.5 leading-relaxed">{overview.core.permissions.join('  ')}</p>
          </details>
        </div>
        {caps.map((c) => (
          <div key={c.code} className="bg-bg-elevated border border-border rounded-lg p-4">
            <div className="flex items-start justify-between gap-2 mb-1">
              <p className="font-display font-semibold text-text-primary">{c.label}</p>
              <span className="text-[10px] text-text-muted font-mono">{c.code}</span>
            </div>
            <p className="text-text-muted text-[13px] mb-3">{c.description}</p>
            <dl className="text-[12px] flex flex-col gap-1.5">
              <div className="flex gap-2">
                <dt className="text-text-muted w-28 shrink-0">Depende de</dt>
                <dd className="text-text-primary">{c.requires.length ? c.requires.map((r) => capLabel[r] || r).join(', ') : 'Nucleo apenas'}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-text-muted w-28 shrink-0">Ecras</dt>
                <dd className="text-text-primary font-mono">{c.screens.join(', ')}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-text-muted w-28 shrink-0">Setores</dt>
                <dd className="text-text-primary">{c.modules.length ? c.modules.join(', ') : 'Nenhum'}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-text-muted w-28 shrink-0">Empresas ativas</dt>
                <dd className="text-text-primary font-mono">{c.companies_active}</dd>
              </div>
            </dl>
            <details className="mt-2">
              <summary className="text-[12px] text-text-muted cursor-pointer">{c.permissions.length} permissoes</summary>
              <p className="text-[11px] text-text-muted font-mono mt-1.5 leading-relaxed">{c.permissions.join('  ')}</p>
            </details>
          </div>
        ))}
      </div>
    );
  }

  function renderImpacto() {
    if (overview.impact.length === 0) {
      return (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <p className="text-text-primary font-medium mb-1">Nenhum impacto</p>
          <p className="text-text-muted text-sm">Nenhuma empresa tem dados numa funcao que os seus setores nao incluem.</p>
        </div>
      );
    }
    return (
      <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
              <th className="text-left px-4 py-2.5">Empresa</th>
              <th className="text-left px-4 py-2.5">Funcao</th>
              <th className="text-right px-4 py-2.5">Registos</th>
            </tr>
          </thead>
          <tbody>
            {overview.impact.map((i) => (
              <tr key={i.company_id + i.capability} className="border-b border-border last:border-0">
                <td className="px-4 py-2.5 text-text-primary">{i.company}</td>
                <td className="px-4 py-2.5 text-text-primary">{capLabel[i.capability] || i.capability}</td>
                <td className="px-4 py-2.5 text-right font-mono text-danger">{i.data_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-text-muted text-[12px] px-4 py-3 border-t border-border">
          Estas funcoes ficariam indisponiveis ao aplicar a separacao. Os dados nao sao apagados - ative o setor correspondente para os manter acessiveis.
        </p>
      </div>
    );
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
          <LayoutGrid size={22} className="text-accent" />
          Visao global
        </h2>
        <button
          type="button"
          onClick={() => load()}
          className="flex items-center gap-2 border border-border hover:border-accent text-text-primary font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer"
        >
          <RefreshCw size={14} />
          Atualizar
        </button>
      </div>
      <p className="text-text-muted text-sm mb-4">Setores, funcoes e empresas da plataforma</p>

      <div className="bg-accent/10 border-l-2 border-accent text-accent px-3.5 py-2.5 text-[13px] rounded-r mb-4">
        Vista de configuracao: as funcoes ainda nao escondem ecras nem bloqueiam acoes das empresas - a aplicacao e um passo seguinte, a validar com a aba Impacto.
      </div>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      <div className="flex items-center gap-2 mb-4 flex-wrap">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (tab === t.key ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
          >
            {t.label}
          </button>
        ))}
        {busy && <Loader2 size={16} className="animate-spin text-accent" />}
      </div>

      {overview && tab === 'setores' && renderSetores()}
      {overview && tab === 'empresas' && renderEmpresas()}
      {overview && tab === 'funcoes' && renderFuncoes()}
      {overview && tab === 'impacto' && renderImpacto()}
    </main>
  );
}

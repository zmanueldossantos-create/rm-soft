import { useEffect, useState } from 'react';
import { AlertTriangle, Check, Copy, ExternalLink, KeyRound, Loader2, Plug, Plus, RefreshCw, Trash2 } from 'lucide-react';
import Modal from './Modal';
import ConfirmDialog from './ConfirmDialog';
import { API_ORIGIN } from '../api/config';
import { createApiKey, getApiJournal, getApiKeys, revokeApiKey } from '../api/apiKeys';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Integração API: the gestor gives other programs of the company (the site, the online shop, a booking engine, a
// report tool) an access key, with only the rights it needs. The key is shown once; the journal shows its calls.

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const when = (iso) => (iso ? new Date(iso).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '-');
const API_ADDRESS = (API_ORIGIN || window.location.origin) + '/api/public/v1';

async function copy(text, message) {
  try { await navigator.clipboard.writeText(text); toast.success(message); } catch { toast.error('Não foi possível copiar - selecione o texto e copie-o à mão'); }
}

export default function ApiKeysTab({ onAllowed }) {
  const [data, setData] = useState(null);
  const [journal, setJournal] = useState([]);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: '', scopes: [] });
  const [saving, setSaving] = useState(false);
  const [newKey, setNewKey] = useState(null); // the key just created: shown once
  const [revoking, setRevoking] = useState(null);

  async function load() {
    try {
      const d = await getApiKeys();
      onAllowed?.(d.allowed);
      setData(d);
      if (d.allowed) setJournal(await getApiJournal());
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Não foi possível carregar a Integração API'));
    }
  }
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function openCreate() {
    setForm({ name: '', scopes: [] });
    setCreating(true);
  }

  async function create() {
    setSaving(true);
    try {
      const created = await createApiKey(form);
      setCreating(false);
      setNewKey(created);
      toast.success('Chave criada - copie-a agora');
      load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao criar a chave'));
    } finally {
      setSaving(false);
    }
  }

  async function confirmRevoke() {
    try {
      await revokeApiKey(revoking.id);
      toast.success('Chave «' + revoking.name + '» revogada: deixa de funcionar já');
      setRevoking(null);
      load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Não foi possível revogar'));
    }
  }

  function toggleScope(code) {
    setForm((f) => ({ ...f, scopes: f.scopes.includes(code) ? f.scopes.filter((s) => s !== code) : [...f.scopes, code] }));
  }

  if (!data) return <div className="flex items-center justify-center py-16 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>;
  if (!data.allowed) {
    return <div className="bg-bg-elevated border border-border rounded-lg p-6 text-sm text-text-muted">A Integração API não está incluída no seu plano. Para a ter, contacte a RM SOFT.</div>;
  }
  const scopeLabel = Object.fromEntries(data.scopes.map((s) => [s.code, s.label.split(':')[0]]));

  return (
    <div className="flex flex-col gap-5">
      {/* ---------------------------------------------------------------------------------------------------- keys */}
      <div className="bg-bg-elevated border border-border rounded-lg p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
          <div className="max-w-2xl">
            <div className="flex items-center gap-2.5 mb-1">
              <Plug size={18} className="text-accent" />
              <h3 className="font-display font-semibold text-[16px] text-text-primary">Chaves de acesso</h3>
            </div>
            <p className="text-sm text-text-muted">Para ligar outros programas da empresa ao RM SOFT: o site, a loja online, um motor de reservas, uma ferramenta de relatórios. Dê a cada programa a sua chave, só com as permissões de que precisa.</p>
          </div>
          <button type="button" onClick={openCreate}
            className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md cursor-pointer">
            <Plus size={15} /> Nova chave
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[13px] mb-4 bg-bg-inset border border-border rounded-md px-4 py-3">
          <span className="text-text-muted">Endereço da API:</span>
          <code className="font-mono text-text-primary break-all">{API_ADDRESS}</code>
          <button type="button" onClick={() => copy(API_ADDRESS, 'Endereço copiado')} className="flex items-center gap-1.5 text-accent hover:text-accent-hover cursor-pointer"><Copy size={13} /> Copiar</button>
          <a href={API_ADDRESS + '/docs'} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-accent hover:text-accent-hover"><ExternalLink size={13} /> Documentação</a>
          <span className="text-text-muted">Limite: {data.rate_per_minute} pedidos por minuto por chave</span>
        </div>

        {data.keys.length === 0 ? (
          <div className="border border-dashed border-border rounded-md py-10 text-center text-sm text-text-muted">
            <KeyRound size={22} className="mx-auto mb-2 opacity-50" />Ainda nenhuma chave.
          </div>
        ) : (
          <ul className="flex flex-col divide-y divide-border border border-border rounded-md">
            {data.keys.map((k) => (
              <li key={k.id} className={'px-4 py-3.5 flex flex-col lg:flex-row lg:items-center gap-3 ' + (k.is_active ? '' : 'opacity-60')}>
                <div className="min-w-0 lg:w-64 shrink-0">
                  <div className="text-sm font-semibold text-text-primary flex items-center gap-2"><KeyRound size={14} className="text-accent" />{k.name}</div>
                  <div className="text-[12px] text-text-muted font-mono">{k.prefix}…</div>
                </div>
                <div className="flex-1 flex flex-wrap gap-1.5">
                  {k.scopes.map((code) => <span key={code} className="text-[12px] bg-bg-inset border border-border rounded px-2 py-0.5 text-text-primary">{scopeLabel[code] || code}</span>)}
                </div>
                <div className="text-[12px] text-text-muted lg:w-56 shrink-0">
                  {k.is_active ? <>Último uso: {k.last_used_at ? when(k.last_used_at) : 'nunca'}</> : <span className="text-danger">Revogada em {when(k.revoked_at)}</span>}
                  <span className="block">Criada em {when(k.created_at)}</span>
                </div>
                {k.is_active && (
                  <button type="button" onClick={() => setRevoking(k)}
                    className="self-start lg:self-center flex items-center gap-1.5 border border-border hover:border-danger hover:text-danger text-text-muted text-[13px] px-3 py-1.5 rounded-md cursor-pointer">
                    <Trash2 size={13} /> Revogar
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* ------------------------------------------------------------------------------------------------- journal */}
      <div className="bg-bg-elevated border border-border rounded-lg p-5 sm:p-6">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 className="font-display font-semibold text-[16px] text-text-primary mb-1">Registo de pedidos</h3>
            <p className="text-sm text-text-muted">Os últimos 200 pedidos feitos com as chaves (guardados {data.journal_days} dias).</p>
          </div>
          <button type="button" onClick={load} aria-label="Atualizar" className="w-9 h-9 flex items-center justify-center rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent cursor-pointer"><RefreshCw size={15} /></button>
        </div>
        {journal.length === 0 ? <p className="text-sm text-text-muted">Ainda nenhum pedido.</p> : (
          <div className="overflow-x-auto border border-border rounded-md max-h-[28rem] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-elevated">
                <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted border-b border-border">
                  <th className="px-3 py-2.5 font-medium">Data</th><th className="px-3 py-2.5 font-medium">Chave</th>
                  <th className="px-3 py-2.5 font-medium">Pedido</th><th className="px-3 py-2.5 font-medium">Resposta</th>
                  <th className="px-3 py-2.5 font-medium text-right">Tempo</th>
                </tr>
              </thead>
              <tbody>
                {journal.map((row, n) => (
                  <tr key={n} className="border-b border-border/60 last:border-0">
                    <td className="px-3 py-2 whitespace-nowrap text-text-muted">{when(row.created_at)}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{row.key_name}</td>
                    <td className="px-3 py-2 font-mono text-[12px]"><span className="text-accent">{row.method}</span> {row.path.replace('/api/public/v1', '')}</td>
                    <td className="px-3 py-2"><span className={'font-mono text-[12px] px-1.5 py-0.5 rounded ' + (row.status_code < 400 ? 'bg-success/15 text-success' : 'bg-danger/15 text-danger')}>{row.status_code}</span></td>
                    <td className="px-3 py-2 text-right font-mono text-[12px] text-text-muted">{row.duration_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ------------------------------------------------------------------------------------------- create a key */}
      <Modal open={creating} onClose={() => setCreating(false)} title="Nova chave de acesso"
             subtitle="Uma chave por programa: se um dia deixar de o usar, revoga só essa"
             footer={(
               <div className="flex justify-end gap-2">
                 <button type="button" onClick={() => setCreating(false)} className="border border-border text-text-primary text-sm px-4 py-2 rounded-md hover:border-accent cursor-pointer">Cancelar</button>
                 <button type="button" onClick={create} disabled={saving}
                   className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 py-2 rounded-md cursor-pointer disabled:opacity-50">
                   {saving ? <Loader2 size={15} className="animate-spin" /> : <KeyRound size={15} />}Criar chave
                 </button>
               </div>
             )}>
        <div className="flex flex-col gap-4">
          <div>
            <label className={labelClass}>Nome</label>
            <input value={form.name} maxLength={100} autoFocus onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Ex.: Site do hotel" className={inputClass} />
          </div>
          <div>
            <span className={labelClass}>Permissões</span>
            <div className="flex flex-col gap-2">
              {data.scopes.map((s) => (
                <label key={s.code} className="flex items-center gap-3 text-sm text-text-primary cursor-pointer border border-border rounded-md px-3 py-2.5 hover:border-accent">
                  <input type="checkbox" checked={form.scopes.includes(s.code)} onChange={() => toggleScope(s.code)} className="w-4 h-4 accent-accent cursor-pointer" />
                  {s.label}
                </label>
              ))}
            </div>
          </div>
        </div>
      </Modal>

      {/* ------------------------------------------------------------------------------- the key, shown only once */}
      <Modal open={!!newKey} onClose={() => setNewKey(null)} title={'Chave «' + (newKey?.name || '') + '»'}
             footer={(
               <div className="flex justify-end">
                 <button type="button" onClick={() => setNewKey(null)} className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 py-2 rounded-md cursor-pointer"><Check size={15} />Já copiei</button>
               </div>
             )}>
        {newKey && (
          <div className="flex flex-col gap-4">
            <div className="flex items-start gap-2.5 text-[13px] text-amber-500 [.light_&]:text-amber-700 bg-amber-500/10 border border-amber-500/30 rounded-md px-3 py-2.5">
              <AlertTriangle size={16} className="shrink-0 mt-0.5" />
              <span>Copie a chave agora e entregue-a a quem configura o programa. Por segurança, não volta a ser mostrada: se a perder, revogue-a e crie outra.</span>
            </div>
            <div className="flex items-center gap-2">
              <code className="flex-1 font-mono text-sm bg-bg-inset border border-border rounded-md px-3 py-2.5 break-all select-all text-text-primary">{newKey.key}</code>
              <button type="button" onClick={() => copy(newKey.key, 'Chave copiada')}
                className="flex items-center gap-1.5 border border-accent text-accent text-sm px-3 py-2.5 rounded-md cursor-pointer shrink-0"><Copy size={14} /> Copiar</button>
            </div>
            <p className="text-[13px] text-text-muted">O programa envia-a em cada pedido: <code className="font-mono">Authorization: Bearer {newKey.prefix}…</code></p>
          </div>
        )}
      </Modal>

      <ConfirmDialog open={!!revoking} danger confirmLabel="Revogar" onCancel={() => setRevoking(null)} onConfirm={confirmRevoke}
        title="Revogar a chave?" message={revoking ? 'O programa que usa «' + revoking.name + '» deixa de conseguir ligar-se. Não se pode desfazer.' : ''} />
    </div>
  );
}

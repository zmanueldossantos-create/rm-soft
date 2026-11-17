import { useEffect, useState } from 'react';
import { Loader2, Plus, Pencil, Trash2, Check, X } from 'lucide-react';
import Modal from './Modal';
import { listHrReferences, createHrReference, updateHrReference, deleteHrReference } from '../api/hr';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// The company's HR tables (departments, categories, job titles, contract types, schedules, education levels,
// documents): one tab per list - add, rename, switch off; a value no file uses can be deleted.
const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';

export default function HrTablesModal({ open, onClose, onChanged }) {
  const [kinds, setKinds] = useState([]);
  const [kind, setKind] = useState('DEPARTAMENTO');
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState('');
  const [editing, setEditing] = useState(null); // { id, name }
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const data = await listHrReferences();
      setKinds(data.kinds);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar as tabelas'));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    if (open) { setLoading(true); setEditing(null); setNewName(''); load(); }
  }, [open]);

  const current = kinds.find((k) => k.kind === kind);

  async function run(action, success) {
    setBusy(true);
    try {
      await action();
      if (success) toast.success(success);
      await load();
      onChanged?.();
      return true;
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Operação recusada'));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function add(e) {
    e.preventDefault();
    if (!newName.trim()) { toast.error('Indique o nome'); return; }
    if (await run(() => createHrReference(kind, newName), null)) setNewName('');
  }

  async function rename(value) {
    if (!editing.name.trim()) { toast.error('Indique o nome'); return; }
    if (await run(() => updateHrReference(value.id, editing.name, value.is_active), null)) setEditing(null);
  }

  return (
    <Modal open={open} onClose={onClose} title="Tabelas de RH" subtitle="Os valores que as fichas dos colaboradores propõem" maxWidthClass="max-w-3xl">
      {loading ? (
        <div className="flex items-center justify-center py-12 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" /> A carregar...</div>
      ) : (
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex sm:flex-col gap-1 overflow-x-auto sm:w-56 shrink-0">
            {kinds.map((k) => (
              <button key={k.kind} type="button" onClick={() => { setKind(k.kind); setEditing(null); setNewName(''); }}
                className={'text-left px-3 py-2 rounded-md text-sm whitespace-nowrap cursor-pointer transition-colors flex justify-between gap-2 ' + (kind === k.kind ? 'bg-accent/10 text-accent font-medium' : 'text-text-muted hover:text-text-primary hover:bg-bg-inset')}>
                <span>{k.label}</span><span className="text-[11px] opacity-70">{k.values.length}</span>
              </button>
            ))}
          </div>
          <div className="flex-1 min-w-0">
            <form noValidate onSubmit={add} className="flex gap-2 mb-3">
              <input value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={120} placeholder={'Novo valor em ' + (current?.label || '').toLowerCase()} className={inputClass} />
              <button type="submit" disabled={busy} className="h-9 px-3 rounded-md bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium flex items-center gap-1.5 shrink-0 cursor-pointer">
                <Plus size={15} /> Acrescentar
              </button>
            </form>
            {(current?.values || []).length === 0 ? (
              <p className="text-sm text-text-muted py-6 text-center">Nenhum valor nesta tabela.</p>
            ) : (
              <div className="border border-border rounded-md divide-y divide-border">
                {current.values.map((v) => (
                  <div key={v.id} className="flex items-center gap-2 px-3 py-2">
                    {editing?.id === v.id ? (
                      <>
                        <input autoFocus value={editing.name} maxLength={120} onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); rename(v); } if (e.key === 'Escape') setEditing(null); }} className={inputClass} />
                        <button type="button" title="Guardar" onClick={() => rename(v)} className="w-8 h-8 rounded-md border border-border text-success flex items-center justify-center cursor-pointer"><Check size={14} /></button>
                        <button type="button" title="Cancelar" onClick={() => setEditing(null)} className="w-8 h-8 rounded-md border border-border text-text-muted flex items-center justify-center cursor-pointer"><X size={14} /></button>
                      </>
                    ) : (
                      <>
                        <span className={'flex-1 text-sm ' + (v.is_active ? 'text-text-primary' : 'text-text-muted line-through')}>{v.name}</span>
                        {v.employees > 0 && <span className="text-[11px] text-text-muted whitespace-nowrap">{v.employees} colab.</span>}
                        <button type="button" disabled={busy} onClick={() => run(() => updateHrReference(v.id, v.name, !v.is_active), null)}
                          className={'h-7 px-2.5 rounded-md text-[12px] font-medium border cursor-pointer ' + (v.is_active ? 'border-border text-text-muted hover:text-text-primary' : 'border-success/40 text-success')}>
                          {v.is_active ? 'Desativar' : 'Ativar'}
                        </button>
                        <button type="button" title="Renomear" onClick={() => setEditing({ id: v.id, name: v.name })} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary flex items-center justify-center cursor-pointer"><Pencil size={13} /></button>
                        {v.employees === 0 && (
                          <button type="button" title="Apagar" disabled={busy} onClick={() => run(() => deleteHrReference(v.id), 'Valor apagado')} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger hover:border-danger flex items-center justify-center cursor-pointer"><Trash2 size={13} /></button>
                        )}
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

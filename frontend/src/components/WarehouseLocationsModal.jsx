import { useEffect, useState } from 'react';
import { Loader2, Pencil, Plus, Power, X, Check } from 'lucide-react';
import Modal from './Modal';
import { listWarehouseLocations, createWarehouseLocation, updateWarehouseLocation, toggleWarehouseLocation } from '../api/stock';
import { extractErrorMessage } from '../utils/errors';

const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2.5';
const inputCls = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';

// Emplacements (optional): the places of one warehouse (shelf, aisle, fridge) - a code and a description. Products are
// put away in them from the stock screen (column Localização). A place still holding products cannot be deactivated.
export default function WarehouseLocationsModal({ warehouse, canManage, onClose, onChanged }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [code, setCode] = useState('');
  const [description, setDescription] = useState('');
  const [editing, setEditing] = useState(null); // {id, code, description}
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setRows(await listWarehouseLocations(warehouse.id));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar as localizações'));
    }
  }

  useEffect(() => {
    if (!warehouse) return;
    setRows(null); setError(''); setCode(''); setDescription(''); setEditing(null);
    load();
  }, [warehouse]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run(action) {
    setBusy(true);
    setError('');
    try {
      await action();
      await load();
      onChanged?.();
      return true;
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar a localização'));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function add(e) {
    e.preventDefault();
    if (await run(() => createWarehouseLocation(warehouse.id, code, description))) { setCode(''); setDescription(''); }
  }

  async function saveEdit() {
    if (await run(() => updateWarehouseLocation(editing.id, editing.code, editing.description))) setEditing(null);
  }

  return (
    <Modal open={!!warehouse} onClose={onClose} title={warehouse ? 'Localizações - ' + warehouse.name : ''} maxWidthClass="max-w-3xl">
      <div className="flex flex-col gap-4">
        <p className="text-[12px] text-text-muted">
          Opcional: os sítios onde a mercadoria é arrumada neste armazém (prateleira, corredor, câmara fria). Cada produto recebe a sua localização no ecrã de Stock, coluna Localização; o inventário passa a seguir essa ordem.
        </p>
        {canManage && (
          <form onSubmit={add} className="grid grid-cols-1 sm:grid-cols-[180px_1fr_auto] gap-2 items-end">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Código *</label>
              <input value={code} maxLength={30} onChange={(e) => setCode(e.target.value)} placeholder="Ex: A-01" className={inputCls + ' font-mono uppercase'} />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Descrição</label>
              <input value={description} maxLength={200} onChange={(e) => setDescription(e.target.value)} placeholder="Ex: Prateleira 1, corredor A" className={inputCls} />
            </div>
            <button type="submit" disabled={busy || !code.trim()} className="h-[38px] flex items-center justify-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-semibold rounded-md px-4 cursor-pointer">
              <Plus size={15} /> Adicionar
            </button>
          </form>
        )}
        {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>}
        {rows === null ? (
          <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin text-accent" /></div>
        ) : rows.length === 0 ? (
          <p className="text-sm text-text-muted text-center py-8">Nenhuma localização - este armazém funciona sem elas.</p>
        ) : (
          <div className="border border-border rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border">
                <th className={th + ' text-left w-44'}>Código</th><th className={th + ' text-left'}>Descrição</th>
                <th className={th + ' text-right'}>Produtos</th><th className={th + ' text-left'}>Estado</th>{canManage && <th className={th + ' text-right'}>Ações</th>}
              </tr></thead>
              <tbody>
                {rows.map((l) => (
                  <tr key={l.id} className={'border-b border-border last:border-0 ' + (l.is_active ? '' : 'opacity-60')}>
                    {editing?.id === l.id ? (
                      <>
                        <td className="px-3 py-2"><input value={editing.code} maxLength={30} onChange={(e) => setEditing({ ...editing, code: e.target.value })} className={inputCls + ' font-mono uppercase'} /></td>
                        <td className="px-3 py-2"><input value={editing.description || ''} maxLength={200} onChange={(e) => setEditing({ ...editing, description: e.target.value })} className={inputCls} /></td>
                      </>
                    ) : (
                      <>
                        <td className="px-4 py-2.5 font-mono text-text-primary">{l.code}</td>
                        <td className="px-4 py-2.5 text-text-muted">{l.description || '-'}</td>
                      </>
                    )}
                    <td className="px-4 py-2.5 font-mono text-text-primary text-right">{l.products}</td>
                    <td className="px-4 py-2.5">
                      <span className={'text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded ' + (l.is_active ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger')}>{l.is_active ? 'Ativa' : 'Inativa'}</span>
                    </td>
                    {canManage && (
                      <td className="px-4 py-2.5">
                        <div className="flex items-center justify-end gap-1.5">
                          {editing?.id === l.id ? (
                            <>
                              <button type="button" onClick={saveEdit} disabled={busy || !editing.code.trim()} title="Guardar" className="w-8 h-8 flex items-center justify-center rounded-md border border-border text-success hover:bg-success/10 cursor-pointer disabled:opacity-50"><Check size={14} /></button>
                              <button type="button" onClick={() => setEditing(null)} title="Cancelar" className="w-8 h-8 flex items-center justify-center rounded-md border border-border text-text-muted hover:text-text-primary cursor-pointer"><X size={14} /></button>
                            </>
                          ) : (
                            <>
                              <button type="button" onClick={() => setEditing({ id: l.id, code: l.code, description: l.description })} title="Editar" className="w-8 h-8 flex items-center justify-center rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent cursor-pointer"><Pencil size={14} /></button>
                              <button type="button" onClick={() => run(() => toggleWarehouseLocation(l.id))} disabled={busy} title={l.is_active ? 'Desativar' : 'Ativar'} className={'w-8 h-8 flex items-center justify-center rounded-md border border-border cursor-pointer disabled:opacity-50 ' + (l.is_active ? 'text-danger hover:bg-danger/10' : 'text-success hover:bg-success/10')}><Power size={14} /></button>
                            </>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Modal>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { ClipboardCheck, Loader2, Plus, Printer, Save, Search, ChevronLeft, CheckCircle2 } from 'lucide-react';
import Modal from './Modal';
import Select from './Select';
import ConfirmDialog from './ConfirmDialog';
import PostingPeriodSelect from './PostingPeriodSelect';
import DateInput from './DateInput';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import {
  listInventories, createInventory, getInventory, saveInventoryCounts, validateInventory, fetchInventoryPdfBlob,
} from '../api/stock';

// Inventário (stock_inventory_service): count a warehouse. The list of its inventories, then one inventory - every
// product managed by stock with its expected quantity; the count is typed per unit (packages + base unit), its total
// in base units goes to the server with the count as typed ("1 SC + 17 KG"). Saved as a draft as often as needed;
// the validation books every difference as an adjustment and freezes the document.
const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5 whitespace-nowrap';
const qty = (v) => (v == null ? '-' : Number(v).toLocaleString('pt-PT', { maximumFractionDigits: 3 }));

// The count of a line: { [unitId | 'base']: '2' } -> total in base units and the detail as typed.
function countOf(line, fields) {
  const units = [...line.sale_units, { id: 'base', code: line.unit_code || '', factor: 1 }];
  const typed = units.filter((u) => fields?.[u.id] !== undefined && fields[u.id] !== '' && !Number.isNaN(parseFloat(fields[u.id])));
  if (typed.length === 0) return { total: null, detail: null };
  const total = Math.round(typed.reduce((s, u) => s + parseFloat(fields[u.id]) * u.factor, 0) * 1000) / 1000;
  return { total, detail: typed.map((u) => fields[u.id] + ' ' + u.code).join(' + ') };
}

export default function StockInventory({ open, onClose, warehouses, warehouseId, canAdjust, onValidated }) {
  const [view, setView] = useState('list'); // list | edit
  const [inventories, setInventories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [newWarehouseId, setNewWarehouseId] = useState('');
  const [periodId, setPeriodId] = useState('');
  const [periodRequired, setPeriodRequired] = useState(false);
  const [inventory, setInventory] = useState(null);
  const [fields, setFields] = useState({}); // { product_id: { unitId: '2' } }
  const [search, setSearch] = useState('');
  const [onlyUncounted, setOnlyUncounted] = useState(false);
  // a product followed by lot / expiry counted above what is expected: the lot its surplus enters
  const [surplus, setSurplus] = useState({});
  const [saving, setSaving] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pdf, setPdf] = useState(null);

  async function loadList() {
    setLoading(true);
    setError('');
    try {
      setInventories(await listInventories());
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar os inventários'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open) return;
    setView('list');
    setInventory(null);
    setNewWarehouseId(warehouseId || '');
    setPeriodId('');
    loadList();
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  function show(data) {
    setInventory(data);
    // a saved count comes back as its total in base units
    setFields(Object.fromEntries(data.lines.filter((l) => l.counted != null).map((l) => [l.product_id, { base: String(l.counted) }])));
    setSurplus(Object.fromEntries(data.lines.filter((l) => l.lot_rule).map((l) => [l.product_id, { lot: l.surplus_lot_number || '', date: l.surplus_expiry_date || '' }])));
    setSearch('');
    setOnlyUncounted(false);
    setView('edit');
  }

  async function openInventory(id) {
    setError('');
    try {
      show(await getInventory(id));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao abrir o inventário'));
    }
  }

  async function startInventory() {
    setSaving(true);
    setError('');
    try {
      show(await createInventory(newWarehouseId, periodId));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao criar o inventário'));
    } finally {
      setSaving(false);
    }
  }

  const editable = inventory?.status === 'RASCUNHO' && canAdjust;
  const counts = useMemo(() => Object.fromEntries((inventory?.lines || []).map((l) => [l.product_id, countOf(l, fields[l.product_id])])), [inventory, fields]);

  async function save() {
    setSaving(true);
    setError('');
    try {
      const payload = inventory.lines.map((l) => ({
        product_id: l.product_id, counted_quantity: counts[l.product_id].total, count_detail: counts[l.product_id].detail,
        surplus_lot_number: l.lot_rule ? (surplus[l.product_id]?.lot || '').trim() || null : null,
        surplus_expiry_date: l.lot_rule ? surplus[l.product_id]?.date || null : null,
      }));
      const data = await saveInventoryCounts(inventory.id, payload);
      setInventory(data);
      return true;
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar a contagem'));
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function validate() {
    setConfirmOpen(false);
    if (!(await save())) return;
    setSaving(true);
    try {
      show(await validateInventory(inventory.id));
      onValidated?.();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao validar o inventário'));
    } finally {
      setSaving(false);
    }
  }

  async function print() {
    try {
      if (editable) await save();
      setPdf({ url: await fetchInventoryPdfBlob(inventory.id), title: (editable ? 'Folha de contagem ' : 'Inventário ') + inventory.reference });
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao gerar o PDF'));
    }
  }

  const lines = (inventory?.lines || []).filter((l) => {
    if (onlyUncounted && counts[l.product_id]?.total != null) return false;
    return !search || (l.code + ' ' + l.name).toLowerCase().includes(search.toLowerCase());
  });
  // live figures of the draft (counted now, not yet saved)
  const live = (inventory?.lines || []).map((l) => {
    const counted = editable ? counts[l.product_id]?.total : l.counted;
    const diff = editable ? (counted == null ? null : Math.round((counted - l.expected) * 1000) / 1000) : l.difference;
    const value = editable ? (diff == null || l.unit_cost == null ? null : Math.round(diff * l.unit_cost * 100) / 100) : l.difference_value;
    return { ...l, counted, diff, value };
  });
  const liveById = Object.fromEntries(live.map((l) => [l.product_id, l]));
  const counted = live.filter((l) => l.counted != null).length;
  const differing = live.filter((l) => l.diff != null && l.diff !== 0);
  const differenceValue = differing.reduce((s, l) => s + (l.value || 0), 0);

  return (
    <>
    <Modal open={open} onClose={onClose} title="Inventário" maxWidthClass="max-w-6xl">
      {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>}

      {view === 'list' ? (
        <div className="flex flex-col gap-5">
          {canAdjust && (
            <div className="flex items-end gap-3 flex-wrap bg-bg-inset border border-border rounded-md p-4">
              <div className="w-64">
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Armazém *</label>
                <Select value={newWarehouseId} onChange={setNewWarehouseId} placeholder="Selecionar"
                  options={warehouses.filter((w) => w.is_active).map((w) => ({ value: w.id, label: w.name }))} />
              </div>
              <PostingPeriodSelect className="w-56" value={periodId} onChange={setPeriodId} onChoice={setPeriodRequired} />
              <button onClick={startInventory} disabled={saving || !newWarehouseId || (periodRequired && !periodId)}
                className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md px-5 py-2.5 flex items-center gap-2 cursor-pointer">
                {saving ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />} Novo inventário
              </button>
            </div>
          )}
          {loading ? (
            <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-accent" /></div>
          ) : inventories.length === 0 ? (
            <p className="text-text-muted text-[13px] text-center py-10">Nenhum inventário ainda</p>
          ) : (
            <div className="border border-border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border">
                  <th className={th + ' text-left'}>Número</th><th className={th + ' text-left'}>Armazém</th><th className={th + ' text-left'}>Período</th>
                  <th className={th + ' text-left'}>Estado</th><th className={th + ' text-right'}>Contados</th><th className={th + ' text-right'}>Diferenças</th>
                  <th className={th + ' text-right'}>Valor</th><th className={th + ' text-left'}>Criado / validado</th><th className={th}></th>
                </tr></thead>
                <tbody>
                  {inventories.map((i) => (
                    <tr key={i.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40">
                      <td className="px-3 py-2.5 font-mono text-text-primary">{i.reference}</td>
                      <td className="px-3 py-2.5 text-text-primary">{i.warehouse_name}</td>
                      <td className="px-3 py-2.5 text-text-muted">{i.period_label}</td>
                      <td className="px-3 py-2.5">
                        <span className={'text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded ' + (i.status === 'VALIDADO' ? 'text-success bg-success/10' : 'text-[#f59e0b] bg-[#f59e0b]/10')}>
                          {i.status === 'VALIDADO' ? 'Validado' : 'Em curso'}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-text-muted">{i.summary.counted} / {i.summary.lines}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-text-primary">{i.summary.differences}</td>
                      <td className={'px-3 py-2.5 text-right font-mono whitespace-nowrap ' + (i.summary.difference_value < 0 ? 'text-danger' : 'text-text-primary')}>{formatKz(i.summary.difference_value)} Kz</td>
                      <td className="px-3 py-2.5 text-[12px] text-text-muted">{(i.validated_by || i.created_by || '-') + ' · ' + new Date(i.validated_at || i.created_at).toLocaleDateString('pt-PT')}</td>
                      <td className="px-3 py-2.5 text-right">
                        <button onClick={() => openInventory(i.id)} className="text-[12px] font-medium text-accent hover:underline cursor-pointer">{i.status === 'VALIDADO' ? 'Ver' : 'Continuar'}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : inventory && (
        <div className="flex flex-col gap-4">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <button onClick={() => { setView('list'); loadList(); }} className="flex items-center gap-1 text-[12px] text-text-muted hover:text-text-primary cursor-pointer mb-1.5">
                <ChevronLeft size={14} /> Inventários
              </button>
              <p className="font-display font-semibold text-text-primary text-lg flex items-center gap-2">
                <ClipboardCheck size={18} className="text-accent" /> {inventory.reference} · {inventory.warehouse_name}
              </p>
              <p className="text-[12px] text-text-muted">
                Período {inventory.period_label}
                {inventory.status === 'VALIDADO' ? ` · validado por ${inventory.validated_by || '-'} em ${new Date(inventory.validated_at).toLocaleString('pt-PT')}` : ' · em curso - o stock esperado é o de agora'}
              </p>
            </div>
            <div className="flex gap-2">
              <button onClick={print} className="flex items-center gap-1.5 border border-border hover:border-accent hover:text-accent text-text-muted text-[13px] font-medium px-3.5 py-2 rounded-md cursor-pointer">
                <Printer size={14} /> {editable ? 'Folha de contagem' : 'Imprimir'}
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative w-72">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Pesquisar produto..."
                className="w-full bg-bg-inset border border-border rounded-md pl-9 pr-3 py-2 text-sm text-text-primary outline-none focus:border-accent" />
            </div>
            {editable && (
              <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer select-none">
                <input type="checkbox" checked={onlyUncounted} onChange={(e) => setOnlyUncounted(e.target.checked)} className="w-4 h-4 accent-accent" />
                Só os não contados
              </label>
            )}
          </div>

          <div className="border border-border rounded-md overflow-auto max-h-[52vh]">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-bg-elevated z-10"><tr className="border-b border-border">
                <th className={th + ' text-left'}>Código</th><th className={th + ' text-left'}>Produto</th><th className={th + ' text-right'}>Esperado</th>
                <th className={th + ' text-left'}>Contado</th><th className={th + ' text-right'}>Diferença</th><th className={th + ' text-right'}>Valor</th>
              </tr></thead>
              <tbody>
                {lines.map((l) => {
                  const row = liveById[l.product_id];
                  const units = [...l.sale_units, { id: 'base', code: l.unit_code || 'Base', factor: 1 }];
                  return (
                    <tr key={l.product_id} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 font-mono text-text-muted whitespace-nowrap">{l.code}</td>
                      <td className="px-3 py-2 text-text-primary">{l.name}{l.is_raw_material && <span className="ml-2 text-[10px] font-semibold uppercase text-text-muted bg-bg-inset px-1.5 py-0.5 rounded">MP</span>}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-muted whitespace-nowrap">{qty(l.expected)} <span className="text-[11px]">{l.unit_code}</span></td>
                      <td className="px-3 py-2">
                        {editable ? (
                          <div className="flex items-center gap-1.5 flex-wrap">
                            {units.map((u, k) => (
                              <span key={u.id} className="flex items-center gap-1">
                                {k > 0 && <span className="text-text-muted text-[11px]">+</span>}
                                <input type="number" min="0" step="any" inputMode="decimal"
                                  value={fields[l.product_id]?.[u.id] ?? ''}
                                  onChange={(e) => setFields((f) => ({ ...f, [l.product_id]: { ...(f[l.product_id] || {}), [u.id]: e.target.value } }))}
                                  onFocus={(e) => e.target.select()}
                                  className="w-20 bg-bg-inset border border-border rounded px-2 py-1 text-right font-mono text-sm text-text-primary outline-none focus:border-accent" />
                                <span className="text-[11px] text-text-muted">{u.code}</span>
                              </span>
                            ))}
                            {l.lot_rule && row.diff > 0 && (
                              <span className="basis-full flex items-center gap-1.5 mt-1">
                                <span className="text-[11px] text-text-muted whitespace-nowrap">Excedente:</span>
                                <input value={surplus[l.product_id]?.lot || ''} maxLength={60} placeholder={l.lot_rule.batch ? 'Lote *' : 'Lote'}
                                  onChange={(e) => setSurplus((x) => ({ ...x, [l.product_id]: { ...(x[l.product_id] || {}), lot: e.target.value } }))}
                                  className="w-28 bg-bg-inset border border-border rounded px-2 py-1 font-mono text-sm text-text-primary outline-none focus:border-accent" />
                                <span className="w-36" title={l.lot_rule.expiry ? 'Validade *' : 'Validade'}>
                                  <DateInput value={surplus[l.product_id]?.date || ''} onChange={(e) => setSurplus((x) => ({ ...x, [l.product_id]: { ...(x[l.product_id] || {}), date: e.target.value } }))}
                                    className="w-full bg-bg-inset border border-border rounded px-2 py-1 font-mono text-sm text-text-primary outline-none focus:border-accent" />
                                </span>
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="font-mono text-text-primary whitespace-nowrap">{l.counted == null ? <span className="text-text-muted text-[12px]">não contado</span> : qty(l.counted) + ' ' + (l.unit_code || '')}{l.count_detail && l.sale_units.length > 0 && <span className="block text-[11px] text-text-muted">{l.count_detail}</span>}{(l.surplus_lot_number || l.surplus_expiry_date) && l.difference > 0 && <span className="block text-[11px] text-text-muted">Excedente: lote {l.surplus_lot_number || '-'}{l.surplus_expiry_date ? ' · val. ' + new Date(l.surplus_expiry_date + 'T00:00:00').toLocaleDateString('pt-PT') : ''}</span>}</span>
                        )}
                      </td>
                      <td className={'px-3 py-2 text-right font-mono whitespace-nowrap ' + (row.diff > 0 ? 'text-success' : row.diff < 0 ? 'text-danger' : 'text-text-muted')}>
                        {row.diff == null ? '-' : (row.diff > 0 ? '+' : '') + qty(row.diff)}
                      </td>
                      <td className={'px-3 py-2 text-right font-mono whitespace-nowrap ' + (row.value < 0 ? 'text-danger' : 'text-text-primary')}>{row.value == null || row.diff === 0 ? '-' : formatKz(row.value) + ' Kz'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between gap-3 flex-wrap bg-bg-inset border border-border rounded-md px-4 py-3">
            <p className="text-[13px] text-text-muted">
              Contados <span className="font-mono text-text-primary">{counted} / {live.length}</span> · Diferenças <span className="font-mono text-text-primary">{differing.length}</span> · Valor
              <span className={'font-mono font-semibold ml-1 ' + (differenceValue < 0 ? 'text-danger' : 'text-text-primary')}>{formatKz(differenceValue)} Kz</span>
            </p>
            {editable && (
              <div className="flex gap-2">
                <button onClick={save} disabled={saving} className="flex items-center gap-1.5 border border-border hover:border-accent hover:text-accent text-text-primary text-[13px] font-medium px-4 py-2.5 rounded-md cursor-pointer disabled:opacity-50">
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Guardar rascunho
                </button>
                <button onClick={() => setConfirmOpen(true)} disabled={saving || counted === 0} className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[13px] font-semibold px-4 py-2.5 rounded-md cursor-pointer disabled:opacity-50">
                  <CheckCircle2 size={14} /> Validar inventário
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </Modal>

      <ConfirmDialog
        open={confirmOpen}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={validate}
        title="Validar inventário"
        message={`${differing.length} diferença(s) vão ser lançadas como ajustes de stock (valor ${formatKz(differenceValue)} Kz). Os produtos não contados ficam como estão. Depois de validado, o inventário não pode ser alterado.`}
        confirmLabel="Validar"
      />

      <Modal open={!!pdf} onClose={() => { if (pdf?.url) URL.revokeObjectURL(pdf.url); setPdf(null); }} title={pdf?.title || ''} maxWidthClass="max-w-3xl" stacked>
        {pdf && <iframe src={pdf.url} title={pdf.title} className="w-full h-[70vh] rounded-md border border-border" />}
      </Modal>
    </>
  );
}

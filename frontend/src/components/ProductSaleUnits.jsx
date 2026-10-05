import { useEffect, useState } from 'react';
import { Plus, Loader2, Pencil, Power, Check, X } from 'lucide-react';
import Select from './Select';
import { listSaleUnits, createSaleUnit, updateSaleUnit, toggleSaleUnit } from '../api/products';
import { extractErrorMessage } from '../utils/errors';

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const EMPTY = { unit_of_measure_id: '', factor: '', price: '', barcode: '' };
const money = (v) => Number(v || 0).toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// The other units a product is sold in (a pallet of 30 eggs, a box of 3 blisters). The product itself stays the base
// unit: stock is always counted in it. Each change is saved at once, independently of the product form; a sale unit is
// deactivated, never deleted.
// noPrice: a raw material's packages (never sold) - no price column, no price field, saved at 0.
export default function ProductSaleUnits({ productId, baseUnitId, units, noPrice = false }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [warnings, setWarnings] = useState([]);
  const baseCode = units.find((u) => u.id === baseUnitId)?.code || 'unidade base';

  async function load() {
    setLoading(true);
    try {
      setRows(await listSaleUnits(productId));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar as unidades e embalagens'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setForm(EMPTY);
    setEditingId(null);
    setError('');
    load();
  }, [productId]); // eslint-disable-line react-hooks/exhaustive-deps

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
    setWarnings([]);
  }

  function startEdit(row) {
    setEditingId(row.id);
    setForm({ unit_of_measure_id: row.unit_of_measure_id, factor: String(row.factor), price: String(row.price), barcode: row.barcode || '' });
    setError('');
  }

  function cancelEdit() {
    setEditingId(null);
    setForm(EMPTY);
    setError('');
    setWarnings([]);
  }

  const canSave = !!form.unit_of_measure_id && parseFloat(form.factor) > 0 && (noPrice || (form.price !== '' && parseFloat(form.price) >= 0));

  async function save(confirm = false) {
    if (!canSave || saving) return;
    setError('');
    setSaving(true);
    const payload = {
      unit_of_measure_id: form.unit_of_measure_id,
      factor: parseFloat(form.factor),
      price: noPrice ? 0 : parseFloat(form.price),
      barcode: form.barcode.trim() || null,
      confirm,
    };
    try {
      if (editingId) await updateSaleUnit(productId, editingId, payload);
      else await createSaleUnit(productId, payload);
      cancelEdit();
      await load();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (err?.response?.status === 409 && Array.isArray(detail?.warnings)) setWarnings(detail.warnings);
      else setError(extractErrorMessage(err, 'Erro ao guardar a unidade ou embalagem'));
    } finally {
      setSaving(false);
    }
  }

  async function toggle(row) {
    setError('');
    try {
      await toggleSaleUnit(productId, row.id);
      await load();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao alterar o estado'));
    }
  }

  // Inside the product form: Enter adds / saves the sale unit instead of submitting the product.
  const onEnter = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      save();
    }
  };

  const unitOptions = units.filter((u) => u.id !== baseUnitId).map((u) => ({ value: u.id, label: u.code + ' - ' + u.name }));
  // A universal unit (a dozen) always holds the same count: its factor is filled in and locked.
  const fixedFactor = units.find((u) => u.id === form.unit_of_measure_id)?.fixed_factor;

  return (
    <div className="flex flex-col gap-3 pt-3 border-t border-border">
      <div>
        <p className="text-[13px] font-medium text-text-primary">Unidades e embalagens</p>
        <p className="text-[12px] text-text-muted">{noPrice ? 'Outras formas de receber e usar esta mat\u00e9ria-prima.' : 'Outras formas de vender este produto.'} O stock e sempre contado em {baseCode}.</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-3"><Loader2 size={16} className="animate-spin text-accent" /></div>
      ) : rows.length > 0 && (
        <div className="overflow-x-auto border border-border rounded-md">
          <table className="w-full text-[12px]">
            <thead className="bg-bg-inset">
              <tr className="text-[10.5px] uppercase tracking-wide text-text-muted">
                <th className="text-left font-medium px-3 py-2">Unidade</th>
                <th className="text-right font-medium px-3 py-2">Contem</th>
                {!noPrice && <th className="text-right font-medium px-3 py-2">Preco</th>}
                {!noPrice && <th className="text-right font-medium px-3 py-2">Preco por {baseCode}</th>}
                <th className="text-left font-medium px-3 py-2">Codigo de barras</th>
                <th className="text-left font-medium px-3 py-2">Estado</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className={'border-t border-border ' + (row.is_active ? '' : 'opacity-50')}>
                  <td className="px-3 py-2 font-mono text-text-primary">{row.unit_of_measure_code}</td>
                  <td className="px-3 py-2 text-right font-mono">{Number(row.factor)} {baseCode}</td>
                  {!noPrice && <td className="px-3 py-2 text-right font-mono text-text-primary">{money(row.price)}</td>}
                  {!noPrice && <td className="px-3 py-2 text-right font-mono text-text-muted">{money(Number(row.price) / Number(row.factor))}</td>}
                  <td className="px-3 py-2 font-mono text-text-muted">{row.barcode || '-'}</td>
                  <td className="px-3 py-2">{row.is_active ? 'Activo' : 'Inactivo'}</td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-2.5">
                      <button type="button" onClick={() => startEdit(row)} title="Editar" className="text-text-muted hover:text-accent cursor-pointer"><Pencil size={14} /></button>
                      <button type="button" onClick={() => toggle(row)} title={row.is_active ? 'Desactivar' : 'Activar'} className="text-text-muted hover:text-accent cursor-pointer"><Power size={14} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-[1.4fr_0.8fr_0.9fr_1.2fr_auto] gap-2 items-end">
        <div>
          <label className={labelClass}>Unidade</label>
          <Select value={form.unit_of_measure_id} onChange={(v) => { const u = units.find((x) => x.id === v); update('unit_of_measure_id', v); if (u?.fixed_factor) update('factor', String(Number(u.fixed_factor))); }} options={unitOptions} placeholder="Selecionar" />
        </div>
        <div>
          <label className={labelClass}>Contem ({baseCode})</label>
          <input type="number" step="0.001" min="0" value={form.factor} onChange={(e) => update('factor', e.target.value)} onKeyDown={onEnter} placeholder="Ex: 30" readOnly={!!fixedFactor} className={inputClass + ' font-mono' + (fixedFactor ? ' opacity-60 cursor-not-allowed' : '')} />
        </div>
        {!noPrice && (
        <div>
          <label className={labelClass}>Preco (Kz)</label>
          <input type="number" step="0.01" min="0" value={form.price} onChange={(e) => update('price', e.target.value)} onKeyDown={onEnter} className={inputClass + ' font-mono'} />
        </div>
        )}
        <div>
          <label className={labelClass}>Codigo de barras</label>
          <input value={form.barcode} onChange={(e) => update('barcode', e.target.value)} onKeyDown={onEnter} className={inputClass + ' font-mono'} />
        </div>
        <div className="flex gap-1.5">
          <button type="button" onClick={() => save()} disabled={!canSave || saving} className="h-[42px] px-3.5 flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white text-[13px] font-medium rounded-md transition-colors cursor-pointer">
            {saving ? <Loader2 size={15} className="animate-spin" /> : editingId ? <Check size={15} /> : <Plus size={15} />}
            {editingId ? 'Guardar' : 'Adicionar'}
          </button>
          {editingId && (
            <button type="button" onClick={cancelEdit} title="Cancelar" className="h-[42px] px-3 flex items-center border border-border hover:border-accent text-text-muted rounded-md cursor-pointer"><X size={15} /></button>
          )}
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="bg-accent/10 border-l-2 border-accent px-3.5 py-2.5 text-[13px] rounded-r flex flex-col gap-2">
          {warnings.map((w) => <p key={w} className="text-text-primary">{w}</p>)}
          <div className="flex gap-2">
            <button type="button" onClick={() => setWarnings([])} className="px-3 py-1.5 border border-border hover:border-accent rounded-md text-[12px] text-text-primary cursor-pointer">Corrigir</button>
            <button type="button" onClick={() => save(true)} className="px-3 py-1.5 bg-accent hover:bg-accent-hover text-white rounded-md text-[12px] font-medium cursor-pointer">Confirmar assim mesmo</button>
          </div>
        </div>
      )}
      {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>}
    </div>
  );
}

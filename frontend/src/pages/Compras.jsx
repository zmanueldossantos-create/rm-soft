import { useEffect, useMemo, useState } from 'react';
import { FileInput, Plus, Loader2, Trash2, Ban, Search } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import DateInput from '../components/DateInput';
import PostingPeriodSelect from '../components/PostingPeriodSelect';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { useCan } from '../utils/permissions';
import { listSuppliers } from '../api/suppliers';
import { listProducts } from '../api/products';
import { listServices } from '../api/services';
import { legalVatRatesApi, vatCodesApi } from '../api/catalogs';
import { listPurchaseInvoices, getPurchaseInvoice, registerPurchaseInvoice, cancelPurchaseInvoice } from '../api/purchases';

// Faturas de compra (purchase_invoice_service): the supplier invoices the company registers - the VAT the supplier
// charged (a legal rate, its exemption motive when exempt), the share the company deducts by its regime, the rest a
// cost. A registration is never deleted: it is cancelled with its reason.
const inputCls = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';
// the cells of a line: the same height as the selects beside them
const cellCls = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5 whitespace-nowrap';
const kz = (v) => formatKz(v) + ' Kz';
const round2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;

function todayIso() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

const emptyLine = () => ({ kind: 'product', itemId: '', description: '', quantity: '1', unitPrice: '', rateId: '', exemptionId: '' });

export default function Compras() {
  const can = useCan();
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [suppliers, setSuppliers] = useState([]);
  const [products, setProducts] = useState([]);
  const [services, setServices] = useState([]);
  const [rates, setRates] = useState([]);
  const [motives, setMotives] = useState([]);
  const [filters, setFilters] = useState({ supplierId: '', status: '', dateFrom: todayIso().slice(0, 8) + '01', dateTo: todayIso() });
  const [search, setSearch] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState(null);
  const [periodRequired, setPeriodRequired] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [detail, setDetail] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelling, setCancelling] = useState(false);

  async function load() {
    setLoading(true);
    setError('');
    try {
      setInvoices(await listPurchaseInvoices(filters));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar as faturas de compra'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    listSuppliers().then(setSuppliers).catch(() => {});
    listProducts().then((d) => setProducts(d.filter((p) => p.is_active))).catch(() => {});
    listServices().then((d) => setServices(d.filter((s) => s.is_active !== false))).catch(() => {});
    legalVatRatesApi.list().then((d) => setRates(d.filter((r) => r.is_active).sort((a, b) => b.rate - a.rate))).catch(() => {});
    vatCodesApi.list().then((d) => setMotives(d.filter((m) => m.is_active))).catch(() => {});
  }, []);

  function openForm() {
    const normal = rates.find((r) => r.tax_category === 'NOR') || rates[0];
    setForm({ supplierId: '', supplierDocument: '', documentDate: todayIso(), dueDate: '', periodId: '', description: '',
      lines: [{ ...emptyLine(), rateId: normal?.id || '' }] });
    setFormError('');
    setFormOpen(true);
  }

  function updateLine(idx, patch) {
    setForm((f) => ({ ...f, lines: f.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  }

  // choosing an article proposes its description and, for a product, its last purchase price
  function chooseItem(idx, line, id) {
    const item = (line.kind === 'product' ? products : services).find((x) => x.id === id);
    updateLine(idx, { itemId: id, description: item?.name || '',  // sent as the line's text
      unitPrice: line.kind === 'product' && item?.purchase_price != null ? String(item.purchase_price) : line.unitPrice });
  }

  const rateById = useMemo(() => Object.fromEntries(rates.map((r) => [r.id, r])), [rates]);
  const computed = (form?.lines || []).map((l) => {
    const subtotal = round2((parseFloat(l.quantity) || 0) * (parseFloat(l.unitPrice) || 0));
    const rate = rateById[l.rateId];
    const vat = rate ? round2(subtotal * Number(rate.rate) / 100) : 0;
    return { subtotal, vat, total: round2(subtotal + vat), exempt: rate && Number(rate.rate) === 0 };
  });
  const totals = computed.reduce((t, c) => ({ subtotal: t.subtotal + c.subtotal, vat: t.vat + c.vat }), { subtotal: 0, vat: 0 });

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setFormError('');
    try {
      const created = await registerPurchaseInvoice({
        supplier_id: form.supplierId, supplier_document: form.supplierDocument, document_date: form.documentDate,
        due_date: form.dueDate || null, fiscal_period_id: form.periodId || null, description: form.description || null,
        lines: form.lines.map((l) => ({
          product_id: l.kind === 'product' && l.itemId ? l.itemId : null,
          service_id: l.kind === 'service' && l.itemId ? l.itemId : null,
          description: l.description || null, quantity: parseFloat(l.quantity) || 0, unit_price: parseFloat(l.unitPrice) || 0,
          legal_vat_rate_id: l.rateId, exemption_id: l.exemptionId || null,
        })),
      });
      setFormOpen(false);
      setDetail(created);
      load();
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao registar a fatura de compra'));
    } finally {
      setSaving(false);
    }
  }

  async function openDetail(id) {
    setCancelReason('');
    try {
      setDetail(await getPurchaseInvoice(id));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao abrir a fatura de compra'));
    }
  }

  async function cancel() {
    setCancelling(true);
    try {
      setDetail(await cancelPurchaseInvoice(detail.id, cancelReason));
      load();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao anular a fatura de compra'));
    } finally {
      setCancelling(false);
    }
  }

  const shown = invoices.filter((i) => !search || (i.supplier_name + ' ' + i.supplier_document + ' ' + i.reference).toLowerCase().includes(search.toLowerCase()));
  const active = shown.filter((i) => i.status === 'REGISTADA');
  const sum = (k) => active.reduce((s, i) => s + i[k], 0);
  const formValid = form && form.supplierId && form.supplierDocument.trim() && form.documentDate && (!periodRequired || form.periodId)
    && form.lines.length > 0 && form.lines.every((l, i) => (l.description.trim() || l.itemId) && parseFloat(l.quantity) > 0 && l.unitPrice !== '' && l.rateId && (!computed[i].exempt || l.exemptionId));

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-start justify-between gap-3 mb-6 flex-wrap">
        <div>
          <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
            <FileInput size={22} className="text-accent" /> Faturas de compra
          </h2>
          <p className="text-text-muted text-sm">As faturas dos fornecedores - IVA dedutível segundo o regime da empresa, o resto é custo</p>
        </div>
        {can('purchases:manage') && (
          <button onClick={openForm} className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md px-5 py-2.5 flex items-center gap-2 cursor-pointer">
            <Plus size={16} /> Nova fatura de compra
          </button>
        )}
      </div>

      <div className="flex items-end gap-2.5 mb-5 flex-wrap">
        <div className="relative w-64">
          <label className={labelCls}>Pesquisar</label>
          <Search size={15} className="absolute left-3 bottom-2.5 text-text-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Fornecedor, documento..." className={inputCls + ' pl-9'} />
        </div>
        <div className="w-56">
          <label className={labelCls}>Fornecedor</label>
          <Select value={filters.supplierId} onChange={(v) => setFilters((f) => ({ ...f, supplierId: v }))} placeholder="Todos"
            options={[{ value: '', label: 'Todos' }, ...suppliers.map((s) => ({ value: s.id, label: s.name }))]} />
        </div>
        <div className="w-40">
          <label className={labelCls}>Estado</label>
          <Select value={filters.status} onChange={(v) => setFilters((f) => ({ ...f, status: v }))} placeholder="Todos"
            options={[{ value: '', label: 'Todos' }, { value: 'REGISTADA', label: 'Registada' }, { value: 'ANULADA', label: 'Anulada' }]} />
        </div>
        <div>
          <label className={labelCls}>De</label>
          <DateInput value={filters.dateFrom} onChange={(e) => setFilters((f) => ({ ...f, dateFrom: e.target.value }))} className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Até</label>
          <DateInput value={filters.dateTo} min={filters.dateFrom || undefined} onChange={(e) => setFilters((f) => ({ ...f, dateTo: e.target.value }))} className={inputCls} />
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5">
        {[['Total (com IVA)', sum('total')], ['Base (sem IVA)', sum('subtotal')], ['IVA dedutível', sum('vat_deductible')], ['IVA não dedutível (custo)', sum('vat_non_deductible')]].map(([label, value]) => (
          <div key={label} className="bg-bg-elevated border border-border rounded-lg px-5 py-4">
            <p className="text-[11px] uppercase tracking-wide text-text-muted">{label}</p>
            <p className="font-mono font-semibold text-xl text-text-primary mt-1">{kz(value)}</p>
          </div>
        ))}
      </div>

      {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>}

      <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
        {loading ? (
          <div className="flex justify-center py-12"><Loader2 size={18} className="animate-spin text-accent" /></div>
        ) : shown.length === 0 ? (
          <p className="text-text-muted text-[13px] text-center py-12">Nenhuma fatura de compra neste período</p>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border">
              <th className={th + ' text-left'}>Registo</th><th className={th + ' text-left'}>Data</th><th className={th + ' text-left'}>Fornecedor</th>
              <th className={th + ' text-left'}>Documento</th><th className={th + ' text-right'}>Base</th><th className={th + ' text-right'}>IVA</th>
              <th className={th + ' text-right'}>Dedutível</th><th className={th + ' text-right'}>Total</th><th className={th + ' text-left'}>Estado</th>
            </tr></thead>
            <tbody>
              {shown.map((i) => (
                <tr key={i.id} onClick={() => openDetail(i.id)} className={'border-b border-border last:border-0 hover:bg-bg-inset/40 cursor-pointer ' + (i.status === 'ANULADA' ? 'opacity-50' : '')}>
                  <td className="px-3 py-2.5 font-mono text-text-muted">{i.reference}</td>
                  <td className="px-3 py-2.5 font-mono text-[12px] text-text-muted">{new Date(i.document_date + 'T00:00:00').toLocaleDateString('pt-PT')}</td>
                  <td className="px-3 py-2.5 text-text-primary">{i.supplier_name}<span className="block text-[11px] text-text-muted font-mono">{i.supplier_nif || ''}</span></td>
                  <td className="px-3 py-2.5 font-mono text-text-primary">{i.supplier_document}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-text-muted whitespace-nowrap">{kz(i.subtotal)}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-text-muted whitespace-nowrap">{kz(i.vat_total)}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-success whitespace-nowrap">{kz(i.vat_deductible)}</td>
                  <td className="px-3 py-2.5 text-right font-mono font-semibold text-text-primary whitespace-nowrap">{kz(i.total)}</td>
                  <td className="px-3 py-2.5">
                    <span className={'text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded ' + (i.status === 'ANULADA' ? 'text-danger bg-danger/10' : 'text-success bg-success/10')}>
                      {i.status === 'ANULADA' ? 'Anulada' : 'Registada'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title="Nova fatura de compra" maxWidthClass="max-w-6xl">
        {form && (
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className={labelCls}>Fornecedor *</label>
                <Select value={form.supplierId} onChange={(v) => setForm((f) => ({ ...f, supplierId: v }))} placeholder="Selecionar"
                  options={suppliers.filter((s) => s.is_active).map((s) => ({ value: s.id, label: s.name + (s.nif ? ' · ' + s.nif : '') }))} />
              </div>
              <div>
                <label className={labelCls}>N.º do documento do fornecedor *</label>
                <input value={form.supplierDocument} onChange={(e) => setForm((f) => ({ ...f, supplierDocument: e.target.value }))} placeholder="Ex: FT A/123" className={inputCls + ' font-mono'} />
              </div>
              <PostingPeriodSelect value={form.periodId} onChange={(v) => setForm((f) => ({ ...f, periodId: v }))} onChoice={setPeriodRequired} />
              <div>
                <label className={labelCls}>Data do documento *</label>
                <DateInput value={form.documentDate} max={todayIso()} onChange={(e) => setForm((f) => ({ ...f, documentDate: e.target.value }))} className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Vencimento</label>
                <DateInput value={form.dueDate} min={form.documentDate || undefined} onChange={(e) => setForm((f) => ({ ...f, dueDate: e.target.value }))} className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Descrição</label>
                <input value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} className={inputCls} />
              </div>
            </div>

            <div className="border border-border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border">
                  <th className={th + ' text-left w-28'}>Tipo</th><th className={th + ' text-left'}>Artigo / descrição</th><th className={th + ' text-right w-24'}>Qtd</th>
                  <th className={th + ' text-right w-32'}>Preço s/ IVA</th><th className={th + ' text-left w-56'}>IVA do fornecedor</th>
                  <th className={th + ' text-right w-32'}>Total</th><th className={th + ' w-10'}></th>
                </tr></thead>
                <tbody>
                  {form.lines.map((l, idx) => (
                    <tr key={idx} className="border-b border-border last:border-0 align-top">
                      <td className="px-2 py-2">
                        <Select value={l.kind} onChange={(v) => updateLine(idx, { kind: v, itemId: '', description: '' })}
                          options={[{ value: 'product', label: 'Produto' }, { value: 'service', label: 'Serviço' }, { value: 'free', label: 'Livre' }]} />
                      </td>
                      <td className="px-2 py-2 min-w-[260px]">
                        {/* an article of the catalog carries its own name; a free line is described here */}
                        {l.kind === 'free' ? (
                          <input value={l.description} onChange={(e) => updateLine(idx, { description: e.target.value })} placeholder="Descrição (ex: renda, eletricidade)" className={cellCls} />
                        ) : (
                          <Select value={l.itemId} onChange={(v) => chooseItem(idx, l, v)} placeholder="Selecionar"
                            options={(l.kind === 'product' ? products : services).map((x) => ({ value: x.id, label: x.code + ' - ' + x.name }))} />
                        )}
                      </td>
                      <td className="px-2 py-2"><input type="number" min="0" step="any" value={l.quantity} onChange={(e) => updateLine(idx, { quantity: e.target.value })} className={cellCls + ' text-right font-mono'} /></td>
                      <td className="px-2 py-2"><input type="number" min="0" step="any" value={l.unitPrice} onChange={(e) => updateLine(idx, { unitPrice: e.target.value })} className={cellCls + ' text-right font-mono'} /></td>
                      <td className="px-2 py-2">
                        <Select value={l.rateId} onChange={(v) => updateLine(idx, { rateId: v, exemptionId: '' })} placeholder="Taxa"
                          options={rates.map((r) => ({ value: r.id, label: r.tax_category + ' ' + Number(r.rate) + ' %' }))} />
                        {computed[idx].exempt && (
                          <div className="mt-1.5">
                            <Select value={l.exemptionId} onChange={(v) => updateLine(idx, { exemptionId: v })} placeholder="Motivo de isenção *"
                              options={motives.map((m) => ({ value: m.id, label: m.code + ' - ' + m.name }))} />
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-text-primary whitespace-nowrap">
                        {kz(computed[idx].total)}<span className="block text-[11px] text-text-muted">IVA {kz(computed[idx].vat)}</span>
                      </td>
                      <td className="px-2 py-2 text-center">
                        {form.lines.length > 1 && (
                          <button type="button" onClick={() => setForm((f) => ({ ...f, lines: f.lines.filter((_, i) => i !== idx) }))} className="text-text-muted hover:text-danger cursor-pointer mt-3"><Trash2 size={15} /></button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <button type="button" onClick={() => setForm((f) => ({ ...f, lines: [...f.lines, { ...emptyLine(), rateId: f.lines[f.lines.length - 1]?.rateId || '' }] }))}
              className="self-start flex items-center gap-1.5 border border-dashed border-accent/60 hover:border-accent text-accent text-[13px] font-medium rounded-md px-3.5 py-2 cursor-pointer">
              <Plus size={15} /> Linha
            </button>

            <div className="flex items-center justify-between gap-3 flex-wrap bg-bg-inset border border-border rounded-md px-4 py-3">
              <p className="text-[13px] text-text-muted">
                Base <span className="font-mono text-text-primary">{kz(totals.subtotal)}</span> · IVA <span className="font-mono text-text-primary">{kz(totals.vat)}</span>
                <span className="block text-[11px]">A parte dedutível do IVA segue o regime da empresa - calculada ao registar.</span>
              </p>
              <p className="font-mono font-semibold text-lg text-text-primary">{kz(totals.subtotal + totals.vat)}</p>
            </div>

            {formError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>}
            <button type="submit" disabled={saving || !formValid} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />} Registar fatura de compra
            </button>
          </form>
        )}
      </Modal>

      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail ? 'Fatura de compra ' + detail.reference : ''} maxWidthClass="max-w-5xl">
        {detail && (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[13px]">
              <div><p className={labelCls}>Fornecedor</p><p className="text-text-primary">{detail.supplier_name}</p><p className="font-mono text-[11px] text-text-muted">{detail.supplier_nif || ''}</p></div>
              <div><p className={labelCls}>Documento</p><p className="font-mono text-text-primary">{detail.supplier_document}</p></div>
              <div><p className={labelCls}>Data / vencimento</p><p className="text-text-primary">{new Date(detail.document_date + 'T00:00:00').toLocaleDateString('pt-PT')}{detail.due_date ? ' · ' + new Date(detail.due_date + 'T00:00:00').toLocaleDateString('pt-PT') : ''}</p></div>
              <div><p className={labelCls}>Período</p><p className="text-text-primary">{detail.period_label}</p></div>
            </div>
            {detail.status === 'ANULADA' && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
                Anulada por {detail.cancelled_by || '-'} em {new Date(detail.cancelled_at).toLocaleString('pt-PT')}: {detail.cancel_reason}
              </div>
            )}
            <div className="border border-border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border">
                  <th className={th + ' text-left'}>Descrição</th><th className={th + ' text-right'}>Qtd</th><th className={th + ' text-right'}>Preço</th>
                  <th className={th + ' text-left'}>IVA</th><th className={th + ' text-right'}>Base</th><th className={th + ' text-right'}>IVA</th>
                  <th className={th + ' text-right'}>Dedutível</th><th className={th + ' text-right'}>Custo</th>
                </tr></thead>
                <tbody>
                  {detail.lines.map((l) => (
                    <tr key={l.position} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 text-text-primary">{l.description}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-muted">{l.quantity.toLocaleString('pt-PT')}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-muted whitespace-nowrap">{kz(l.unit_price)}</td>
                      <td className="px-3 py-2 font-mono text-[12px] text-text-muted whitespace-nowrap">{l.tax_category} {l.vat_rate} %{l.exemption_code ? ' · ' + l.exemption_code : ''}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{kz(l.line_subtotal)}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{kz(l.line_vat)}</td>
                      <td className="px-3 py-2 text-right font-mono text-success whitespace-nowrap">{kz(l.vat_deductible)}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{kz(l.cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              {[['Base', detail.subtotal], ['IVA', detail.vat_total], ['Total', detail.total], [`IVA dedutível (${detail.deductible_pct} %)`, detail.vat_deductible], ['IVA não dedutível', detail.vat_non_deductible]].map(([label, value]) => (
                <div key={label} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5">
                  <p className="text-[10px] uppercase tracking-wide text-text-muted">{label}</p>
                  <p className="font-mono font-semibold text-text-primary">{kz(value)}</p>
                </div>
              ))}
            </div>
            <p className="text-[12px] text-text-muted">Registada por {detail.created_by || '-'} em {new Date(detail.created_at).toLocaleString('pt-PT')}{detail.description ? ' · ' + detail.description : ''}</p>
            {detail.status === 'REGISTADA' && can('purchases:manage') && (
              <div className="flex items-end gap-2 border-t border-border pt-4">
                <div className="flex-1">
                  <label className={labelCls}>Motivo da anulação</label>
                  <input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="Ex: registada em duplicado" className={inputCls} />
                </div>
                <button onClick={cancel} disabled={cancelling || !cancelReason.trim()} className="flex items-center gap-1.5 border border-danger/60 text-danger hover:bg-danger/10 disabled:opacity-50 text-[13px] font-medium px-4 py-2 rounded-md cursor-pointer">
                  {cancelling ? <Loader2 size={14} className="animate-spin" /> : <Ban size={14} />} Anular
                </button>
              </div>
            )}
          </div>
        )}
      </Modal>
    </main>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { FileInput, Plus, Loader2, Trash2, Ban, Search, Eye, Wallet, CheckCircle2 } from 'lucide-react';
import SupplierPaymentModal from '../components/SupplierPaymentModal';
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
import { listWarehouses } from '../api/stock';
import { legalVatRatesApi, vatCodesApi } from '../api/catalogs';
import { listPurchaseInvoices, getPurchaseInvoice, registerPurchaseInvoice, cancelPurchaseInvoice } from '../api/purchases';

// Faturas de compra (purchase_invoice_service): the supplier invoices the company registers - the VAT the supplier
// charged (a legal rate, its exemption motive when exempt), the share the company deducts by its regime, the rest a
// cost. A registration is never deleted: it is cancelled with its reason. Its products may enter a warehouse at their
// cost (the system's automatic entry) - one purchase, one entry: no separate Receção. For the SAF-T: the supplier
// document's type (a credit note refers to the invoice it corrects, never moves the stock and counts against), its
// printed hash and, per line, what the deductible VAT is for.
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

const DOC_TYPES = [{ value: 'FT', label: 'Fatura' }, { value: 'FR', label: 'Fatura-recibo' }, { value: 'TV', label: 'Talão de venda' }, { value: 'NC', label: 'Nota de crédito' }];
const DOC_TYPE_LABEL = Object.fromEntries(DOC_TYPES.map((t) => [t.value, t.label]));
// what the deductible VAT is for (SAF-T DeductibleTaxType) - by default from the line's kind
const DESTINATIONS = [{ value: 'INV', label: 'INV - Existências' }, { value: 'OBC', label: 'OBC - Outros bens de consumo' }, { value: 'SERV', label: 'SERV - Serviços' },
  { value: 'MFI', label: 'MFI - Meios fixos e investimentos' }, { value: 'IMPT', label: 'IMPT - Importação' }, { value: 'SCE', label: 'SCE - Serviços contratados no estrangeiro' }];
const DEFAULT_DESTINATION = { product: 'INV', service: 'SERV', free: 'OBC' };
const sign = (i) => (i.purchase_type === 'NC' ? -1 : 1);
// what is paid on an invoice (supplier_payment_service): a FT is owed until paid, a FR / TV was paid when issued
const PAYMENT_STATUS = { PENDENTE: ['Pendente', 'text-text-muted bg-text-muted/10'], PARCIAL: ['Parcial', 'text-text-primary bg-text-muted/15'], PAGA: ['Paga', 'text-success bg-success/10'] };

const emptyLine = () => ({ kind: 'product', destination: 'INV', itemId: '', saleUnitId: '', description: '', quantity: '1', unitPrice: '', rateId: '', exemptionId: '' });

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
  const [warehouses, setWarehouses] = useState([]);
  // payment 'DUE': every invoice still owed, whatever its date
  const [filters, setFilters] = useState({ supplierId: '', status: '', payment: '', dateFrom: todayIso().slice(0, 8) + '01', dateTo: todayIso() });
  const [selected, setSelected] = useState([]);  // invoices ticked to pay (one supplier)
  const [paying, setPaying] = useState(null);
  const [notice, setNotice] = useState('');
  const [search, setSearch] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState(null);
  const [periodRequired, setPeriodRequired] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  const [detail, setDetail] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [detailError, setDetailError] = useState('');  // shown in the open invoice, where the action was made

  async function load() {
    setLoading(true);
    setError('');
    try {
      const due = filters.payment === 'DUE';
      const rows = await listPurchaseInvoices(due ? { supplierId: filters.supplierId, status: 'REGISTADA' } : filters);
      setInvoices(due ? rows.filter((i) => i.amount_due > 0.005) : rows);
      setSelected((sel) => sel.filter((id) => rows.some((i) => i.id === id && i.amount_due > 0.005)));
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
    listWarehouses().then(setWarehouses).catch(() => {});
  }, []);

  function openForm() {
    const normal = rates.find((r) => r.tax_category === 'NOR') || rates[0];
    // the goods enter the central warehouse (the first one) unless another is chosen - or not at all
    setForm({ supplierId: '', purchaseType: 'FT', supplierDocument: '', supplierHash: '', referenceInvoiceId: '', documentDate: todayIso(), dueDate: '', periodId: '', description: '',
      stockEntry: can('stock:receive'), warehouseId: warehouses.find((w) => w.is_active)?.id || '',
      lines: [{ ...emptyLine(), rateId: normal?.id || '' }] });
    setFormError('');
    setFormOpen(true);
  }

  function updateLine(idx, patch) {
    setForm((f) => ({ ...f, lines: f.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));
  }

  // choosing an article proposes its description and, for a product, its last purchase price (per base unit)
  function chooseItem(idx, line, id) {
    const item = (line.kind === 'product' ? products : services).find((x) => x.id === id);
    updateLine(idx, { itemId: id, saleUnitId: '', description: item?.name || '',  // sent as the line's text
      unitPrice: line.kind === 'product' && item?.purchase_price != null ? String(item.purchase_price) : line.unitPrice });
  }

  const productById = useMemo(() => Object.fromEntries(products.map((p) => [p.id, p])), [products]);
  const unitOf = (l) => (productById[l.itemId]?.sale_units || []).find((u) => u.id === l.saleUnitId) || null;

  // the unit it was bought in (a sack of 20 kg): the last price paid, per base unit, times the unit's factor
  function chooseUnit(idx, line, value) {
    const product = productById[line.itemId];
    const unit = (product?.sale_units || []).find((u) => u.id === value) || null;
    updateLine(idx, { saleUnitId: unit ? unit.id : '',
      unitPrice: product?.purchase_price != null ? String(round2(Number(product.purchase_price) * (unit ? Number(unit.factor) : 1))) : line.unitPrice });
  }

  // a credit note corrects one of the supplier's registered invoices
  const [supplierInvoices, setSupplierInvoices] = useState([]);
  useEffect(() => {
    if (!form || form.purchaseType !== 'NC' || !form.supplierId) { setSupplierInvoices([]); return; }
    listPurchaseInvoices({ supplierId: form.supplierId, status: 'REGISTADA' })
      .then((d) => setSupplierInvoices(d.filter((i) => i.purchase_type !== 'NC'))).catch(() => setSupplierInvoices([]));
  }, [form?.purchaseType, form?.supplierId]); // eslint-disable-line react-hooks/exhaustive-deps

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
        stock_entry: stockEntry, warehouse_id: stockEntry ? form.warehouseId : null,
        purchase_type: form.purchaseType, supplier_hash: form.supplierHash.trim() || null,
        reference_invoice_id: form.purchaseType === 'NC' ? form.referenceInvoiceId : null,
        lines: form.lines.map((l) => ({
          product_id: l.kind === 'product' && l.itemId ? l.itemId : null,
          sale_unit_id: l.kind === 'product' && l.saleUnitId ? l.saleUnitId : null,
          service_id: l.kind === 'service' && l.itemId ? l.itemId : null,
          description: l.description || null, quantity: parseFloat(l.quantity) || 0, unit_price: parseFloat(l.unitPrice) || 0,
          legal_vat_rate_id: l.rateId, exemption_id: l.exemptionId || null, deductible_tax_type: l.destination,
        })),
      });
      setFormOpen(false);
      setCancelReason('');
      setDetailError('');
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
    setDetailError('');
    try {
      setDetail(await getPurchaseInvoice(id));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao abrir a fatura de compra'));
    }
  }

  async function cancel() {
    setCancelling(true);
    setDetailError('');
    try {
      setDetail(await cancelPurchaseInvoice(detail.id, cancelReason));
      setCancelReason('');
      load();
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao anular a fatura de compra'));
    } finally {
      setCancelling(false);
    }
  }

  const canPay = can('purchases:pay');
  const selectedSupplier = invoices.find((i) => i.id === selected[0])?.supplier_id;
  const payable = (i) => i.status === 'REGISTADA' && i.purchase_type === 'FT' && i.amount_due > 0.005;
  const canTick = (i) => payable(i) && (!selectedSupplier || i.supplier_id === selectedSupplier);
  const toggle = (id) => setSelected((sel) => (sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id]));
  const shown = invoices.filter((i) => !search || (i.supplier_name + ' ' + i.supplier_document + ' ' + i.reference).toLowerCase().includes(search.toLowerCase()));
  const active = shown.filter((i) => i.status === 'REGISTADA');
  const sum = (k) => active.reduce((s, i) => s + sign(i) * i[k], 0);  // a credit note counts against
  const hasProduct = !!form && form.lines.some((l) => l.kind === 'product' && l.itemId);
  const isCreditNote = !!form && form.purchaseType === 'NC';
  const stockEntry = !!form && form.stockEntry && hasProduct && !isCreditNote;
  const formValid = form && form.supplierId && (!stockEntry || form.warehouseId) && (!isCreditNote || form.referenceInvoiceId) && form.supplierDocument.trim() && form.documentDate && (!periodRequired || form.periodId)
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
        <div className="flex items-center gap-2.5">
          {canPay && selected.length > 0 && (
            <button onClick={() => setPaying(invoices.filter((i) => selected.includes(i.id)))} className="border border-accent text-accent hover:bg-accent/10 font-semibold text-sm rounded-md px-5 py-2.5 flex items-center gap-2 cursor-pointer">
              <Wallet size={16} /> Pagar {selected.length} {selected.length === 1 ? 'fatura' : 'faturas'}
            </button>
          )}
          {can('purchases:manage') && (
            <button onClick={openForm} className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md px-5 py-2.5 flex items-center gap-2 cursor-pointer">
              <Plus size={16} /> Nova fatura de compra
            </button>
          )}
        </div>
      </div>

      <div className="flex items-end gap-2.5 mb-5 flex-wrap">
        <div className="relative w-56">
          <label className={labelCls}>Pesquisar</label>
          <Search size={15} className="absolute left-3 bottom-2.5 text-text-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Fornecedor, documento..." className={inputCls + ' pl-9'} />
        </div>
        <div className="w-52">
          <label className={labelCls}>Fornecedor</label>
          <Select value={filters.supplierId} onChange={(v) => setFilters((f) => ({ ...f, supplierId: v }))} placeholder="Todos"
            options={[{ value: '', label: 'Todos' }, ...suppliers.map((s) => ({ value: s.id, label: s.name }))]} />
        </div>
        <div className="w-36">
          <label className={labelCls}>Estado</label>
          <Select value={filters.status} onChange={(v) => setFilters((f) => ({ ...f, status: v }))} placeholder="Todos"
            options={[{ value: '', label: 'Todos' }, { value: 'REGISTADA', label: 'Registada' }, { value: 'ANULADA', label: 'Anulada' }]} />
        </div>
        <div className="w-56">
          <label className={labelCls}>Pagamento</label>
          <Select value={filters.payment} onChange={(v) => setFilters((f) => ({ ...f, payment: v }))}
            options={[{ value: '', label: 'Todas' }, { value: 'DUE', label: 'Em dívida (todas as datas)' }]} />
        </div>
        <div className="w-40">
          <label className={labelCls}>De</label>
          <DateInput value={filters.dateFrom} disabled={filters.payment === 'DUE'} onChange={(e) => setFilters((f) => ({ ...f, dateFrom: e.target.value }))} className={inputCls + (filters.payment === 'DUE' ? ' opacity-40 cursor-not-allowed' : '')} />
        </div>
        <div className="w-40">
          <label className={labelCls}>Até</label>
          <DateInput value={filters.dateTo} disabled={filters.payment === 'DUE'} min={filters.dateFrom || undefined} onChange={(e) => setFilters((f) => ({ ...f, dateTo: e.target.value }))} className={inputCls + (filters.payment === 'DUE' ? ' opacity-40 cursor-not-allowed' : '')} />
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
      {notice && (
        <div className="bg-success/10 border-l-2 border-success text-success px-3.5 py-2.5 text-[13px] rounded-r mb-4 flex items-center justify-between gap-3">
          <span className="flex items-center gap-2"><CheckCircle2 size={15} /> {notice}</span>
          <button onClick={() => setNotice('')} className="text-[12px] underline cursor-pointer">Fechar</button>
        </div>
      )}
      {canPay && <p className="text-[12px] text-text-muted mb-3">Para pagar, marque as faturas em dívida de um fornecedor - um pagamento para todas.</p>}

      <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
        {loading ? (
          <div className="flex justify-center py-12"><Loader2 size={18} className="animate-spin text-accent" /></div>
        ) : shown.length === 0 ? (
          <p className="text-text-muted text-[13px] text-center py-12">Nenhuma fatura de compra neste período</p>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border">
              {canPay && <th className={th + ' w-10'} />}
              <th className={th + ' text-left'}>Registo</th><th className={th + ' text-left'}>Data</th><th className={th + ' text-left'}>Fornecedor</th>
              <th className={th + ' text-left'}>Documento</th><th className={th + ' text-right'}>Base</th><th className={th + ' text-right'}>IVA</th>
              <th className={th + ' text-right'}>Dedutível</th><th className={th + ' text-right'}>Total</th><th className={th + ' text-right'}>Em dívida</th>
              <th className={th + ' text-left'}>Estado</th><th className={th + ' text-right'}>Ações</th>
            </tr></thead>
            <tbody>
              {shown.map((i) => (
                <tr key={i.id} className={'border-b border-border last:border-0 ' + (i.status === 'ANULADA' ? 'opacity-50' : '') + (selected.includes(i.id) ? ' bg-accent/5' : '')}>
                  {canPay && (
                    <td className="px-3 py-2.5 text-center">
                      {payable(i) && (
                        <input type="checkbox" checked={selected.includes(i.id)} disabled={!selected.includes(i.id) && !canTick(i)} onChange={() => toggle(i.id)}
                          title={!selected.includes(i.id) && !canTick(i) ? 'Outro fornecedor: um pagamento é de um só fornecedor' : 'Marcar para pagar'}
                          className="w-4 h-4 accent-accent cursor-pointer disabled:cursor-not-allowed disabled:opacity-30" />
                      )}
                    </td>
                  )}
                  <td className="px-3 py-2.5 font-mono text-text-muted">{i.reference}</td>
                  <td className="px-3 py-2.5 font-mono text-[12px] text-text-muted">{new Date(i.document_date + 'T00:00:00').toLocaleDateString('pt-PT')}</td>
                  <td className="px-3 py-2.5 text-text-primary">{i.supplier_name}<span className="block text-[11px] text-text-muted font-mono">{i.supplier_nif || ''}</span></td>
                  <td className="px-3 py-2.5 font-mono text-text-primary">{i.supplier_document}{i.purchase_type === 'NC' && <span className="ml-2 text-[10.5px] font-sans font-semibold uppercase text-danger">Nota de crédito</span>}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-text-muted whitespace-nowrap">{kz(i.subtotal)}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-text-muted whitespace-nowrap">{kz(i.vat_total)}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-success whitespace-nowrap">{kz(i.vat_deductible)}</td>
                  <td className="px-3 py-2.5 text-right font-mono font-semibold text-text-primary whitespace-nowrap">{kz(i.total)}</td>
                  <td className={'px-3 py-2.5 text-right font-mono whitespace-nowrap ' + (i.overdue ? 'text-danger' : 'text-text-primary')}>{i.payment_status ? kz(i.amount_due) : '-'}</td>
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    {i.status === 'ANULADA' && <span className="text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded text-danger bg-danger/10">Anulada</span>}
                    {i.purchase_type === 'NC' && i.status !== 'ANULADA' && <span className="text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded text-text-muted bg-text-muted/10">Registada</span>}
                    {i.payment_status && (
                      <span className={'text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded ' + PAYMENT_STATUS[i.payment_status][1]}>{PAYMENT_STATUS[i.payment_status][0]}</span>
                    )}
                    {i.overdue && <span className="ml-1.5 text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded text-danger bg-danger/10">Vencida</span>}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => openDetail(i.id)} className="inline-flex items-center gap-1.5 border border-border hover:border-accent hover:text-accent text-text-primary text-[12px] font-medium px-2.5 py-1.5 rounded-md cursor-pointer">
                      <Eye size={14} /> Ver
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title="Nova fatura de compra" maxWidthClass="max-w-7xl">
        {form && (
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div>
                <label className={labelCls}>Fornecedor *</label>
                <Select value={form.supplierId} onChange={(v) => setForm((f) => ({ ...f, supplierId: v, referenceInvoiceId: '' }))} placeholder="Selecionar"
                  options={suppliers.filter((s) => s.is_active).map((s) => ({ value: s.id, label: s.name + (s.nif ? ' · ' + s.nif : '') }))} />
              </div>
              <div>
                <label className={labelCls}>Tipo de documento *</label>
                <Select value={form.purchaseType} onChange={(v) => setForm((f) => ({ ...f, purchaseType: v, referenceInvoiceId: '' }))} options={DOC_TYPES} />
              </div>
              <div>
                <label className={labelCls}>N.º do documento do fornecedor *</label>
                <input value={form.supplierDocument} onChange={(e) => setForm((f) => ({ ...f, supplierDocument: e.target.value }))} placeholder={isCreditNote ? 'Ex: NC A/12' : 'Ex: FT A/123'} className={inputCls + ' font-mono'} />
              </div>
              <div>
                <label className={labelCls}>Hash do documento</label>
                <input value={form.supplierHash} maxLength={4} onChange={(e) => setForm((f) => ({ ...f, supplierHash: e.target.value }))} placeholder="4 caracteres impressos" className={inputCls + ' font-mono'} />
              </div>
              {isCreditNote && (
                <div className="md:col-span-4">
                  <label className={labelCls}>Fatura corrigida *</label>
                  <Select value={form.referenceInvoiceId} onChange={(v) => setForm((f) => ({ ...f, referenceInvoiceId: v }))}
                    placeholder={form.supplierId ? (supplierInvoices.length ? 'Selecionar a fatura deste fornecedor' : 'Nenhuma fatura registada deste fornecedor') : 'Escolha primeiro o fornecedor'}
                    options={supplierInvoices.map((i) => ({ value: i.id, label: i.reference + ' · ' + i.supplier_document + ' · ' + new Date(i.document_date + 'T00:00:00').toLocaleDateString('pt-PT') + ' · ' + kz(i.total) }))} />
                </div>
              )}
              <div>
                <label className={labelCls}>Data do documento *</label>
                <DateInput value={form.documentDate} max={todayIso()} onChange={(e) => setForm((f) => ({ ...f, documentDate: e.target.value }))} className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Vencimento</label>
                <DateInput value={form.dueDate} min={form.documentDate || undefined} onChange={(e) => setForm((f) => ({ ...f, dueDate: e.target.value }))} className={inputCls} />
              </div>
              <PostingPeriodSelect value={form.periodId} onChange={(v) => setForm((f) => ({ ...f, periodId: v }))} onChoice={setPeriodRequired} />
              <div>
                <label className={labelCls}>Descrição</label>
                <input value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} className={inputCls} />
              </div>
            </div>

            <div className="border border-border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border">
                  <th className={th + ' text-left w-28'}>Tipo</th><th className={th + ' text-left'}>Artigo / descrição</th><th className={th + ' text-left w-28'}>Un.</th><th className={th + ' text-right w-28'}>Qtd</th>
                  <th className={th + ' text-right w-32'}>Preço s/ IVA</th><th className={th + ' text-left w-64'}>IVA do fornecedor · destino</th>
                  <th className={th + ' text-right w-32'}>Total</th><th className={th + ' w-10'}></th>
                </tr></thead>
                <tbody>
                  {form.lines.map((l, idx) => (
                    <tr key={idx} className="border-b border-border last:border-0 align-top">
                      <td className="px-2 py-2">
                        <Select value={l.kind} onChange={(v) => updateLine(idx, { kind: v, itemId: '', description: '', destination: DEFAULT_DESTINATION[v] })}
                          options={[{ value: 'product', label: 'Produto' }, { value: 'service', label: 'Serviço' }, { value: 'free', label: 'Livre' }]} />
                      </td>
                      <td className="px-2 py-2 min-w-[220px]">
                        {/* an article of the catalog carries its own name; a free line is described here */}
                        {l.kind === 'free' ? (
                          <input value={l.description} onChange={(e) => updateLine(idx, { description: e.target.value })} placeholder="Descrição (ex: renda, eletricidade)" className={cellCls} />
                        ) : (
                          <Select value={l.itemId} onChange={(v) => chooseItem(idx, l, v)} placeholder="Selecionar"
                            options={(l.kind === 'product' ? products : services).map((x) => ({ value: x.id, label: x.code + ' - ' + x.name }))} />
                        )}
                      </td>
                      <td className="px-2 py-2">
                        {/* a product is bought in one of its units (a sack of 20 kg); its stock moves in base units */}
                        {l.kind === 'product' && (productById[l.itemId]?.sale_units || []).length > 0 ? (
                          <Select value={l.saleUnitId || 'base'} onChange={(v) => chooseUnit(idx, l, v === 'base' ? '' : v)}
                            options={[{ value: 'base', label: productById[l.itemId].unit_of_measure_code || 'Base' }, ...productById[l.itemId].sale_units.map((u) => ({ value: u.id, label: u.unit_of_measure_code }))]} />
                        ) : (
                          <p className="px-1 py-3 font-mono text-[13px] text-text-muted">{l.kind === 'product' ? (productById[l.itemId]?.unit_of_measure_code || '-') : '-'}</p>
                        )}
                      </td>
                      <td className="px-2 py-2">
                        <input type="number" min="0" step="any" value={l.quantity} onChange={(e) => updateLine(idx, { quantity: e.target.value })} className={cellCls + ' text-right font-mono min-w-[88px]'} />
                        {unitOf(l) && parseFloat(l.quantity) > 0 && (
                          <p className="text-[10.5px] text-text-muted mt-0.5 text-right whitespace-nowrap">= {(parseFloat(l.quantity) * Number(unitOf(l).factor)).toLocaleString('pt-PT', { maximumFractionDigits: 3 })} {productById[l.itemId].unit_of_measure_code}</p>
                        )}
                      </td>
                      <td className="px-2 py-2"><input type="number" min="0" step="any" value={l.unitPrice} onChange={(e) => updateLine(idx, { unitPrice: e.target.value })} className={cellCls + ' text-right font-mono min-w-[120px]'} /></td>
                      <td className="px-2 py-2">
                        <Select value={l.rateId} onChange={(v) => updateLine(idx, { rateId: v, exemptionId: '' })} placeholder="Taxa"
                          options={rates.map((r) => ({ value: r.id, label: r.tax_category + ' ' + Number(r.rate) + ' %' }))} />
                        {/* what the deductible VAT is for (SAF-T) - under the rate it belongs to */}
                        <div className="mt-1.5">
                          <Select value={l.destination} onChange={(v) => updateLine(idx, { destination: v })}
                            options={DESTINATIONS.map((d) => ({ value: d.value, label: d.label }))} />
                        </div>
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

            {hasProduct && can('stock:receive') && !isCreditNote && (
              <div className="flex items-center gap-4 flex-wrap border border-border rounded-md px-4 py-3">
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input type="checkbox" checked={form.stockEntry} onChange={(e) => setForm((f) => ({ ...f, stockEntry: e.target.checked }))} className="w-4 h-4 accent-accent cursor-pointer" />
                  <span className="text-sm text-text-primary">Dar entrada em stock dos produtos</span>
                </label>
                {form.stockEntry ? (
                  <div className="w-64">
                    <Select value={form.warehouseId} onChange={(v) => setForm((f) => ({ ...f, warehouseId: v }))} placeholder="Armazém *"
                      options={warehouses.filter((w) => w.is_active).map((w) => ({ value: w.id, label: w.name }))} />
                  </div>
                ) : (
                  <p className="text-[12px] text-text-muted">A mercadoria já entrou noutro documento - esta fatura não mexe no stock.</p>
                )}
                {form.stockEntry && <p className="text-[12px] text-text-muted basis-full">Cada produto entra ao seu custo (preço sem IVA + IVA não dedutível) - atualiza o custo médio.</p>}
              </div>
            )}

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
              <div><p className={labelCls}>Documento</p><p className="font-mono text-text-primary">{detail.supplier_document}</p>
                <p className="text-[11px] text-text-muted">{DOC_TYPE_LABEL[detail.purchase_type] || detail.purchase_type}{detail.supplier_hash ? ' · hash ' + detail.supplier_hash : ''}</p>
                {detail.reference_invoice && <p className="text-[11px] text-text-muted">Corrige {detail.reference_invoice}</p>}</div>
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
                  <th className={th + ' text-right'}>Dedutível</th><th className={th + ' text-left'}>Destino</th><th className={th + ' text-right'}>Custo</th>
                </tr></thead>
                <tbody>
                  {detail.lines.map((l) => (
                    <tr key={l.position} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 text-text-primary">{l.description}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-muted whitespace-nowrap">{l.quantity.toLocaleString('pt-PT')}{l.unit ? ' ' + l.unit : ''}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-muted whitespace-nowrap">{kz(l.unit_price)}</td>
                      <td className="px-3 py-2 font-mono text-[12px] text-text-muted whitespace-nowrap">{l.tax_category} {l.vat_rate} %{l.exemption_code ? ' · ' + l.exemption_code : ''}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{kz(l.line_subtotal)}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{kz(l.line_vat)}</td>
                      <td className="px-3 py-2 text-right font-mono text-success whitespace-nowrap">{kz(l.vat_deductible)}</td>
                      <td className="px-3 py-2 font-mono text-[12px] text-text-muted" title={DESTINATIONS.find((d) => d.value === l.deductible_tax_type)?.label}>{l.deductible_tax_type}</td>
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
            {detail.payment_status && (
              <p className="text-[13px] text-text-muted">
                Pagamento: <span className="text-text-primary font-medium">{PAYMENT_STATUS[detail.payment_status][0]}</span>
                {' · pago '}<span className="font-mono text-text-primary">{kz(detail.amount_paid)}</span>
                {detail.amount_credited > 0 && <>{' · notas de crédito '}<span className="font-mono text-text-primary">{kz(detail.amount_credited)}</span></>}
                {' · em dívida '}<span className={'font-mono ' + (detail.overdue ? 'text-danger' : 'text-text-primary')}>{kz(detail.amount_due)}</span>
                {detail.overdue && ' (vencida)'}
              </p>
            )}
            <p className="text-[13px] text-text-muted">
              {detail.stock_entry_reference
                ? <>Entrada em stock: <span className="font-mono text-text-primary">{detail.stock_entry_reference}</span> · {detail.warehouse_name}{detail.stock_exit_reference && <> · saída na anulação: <span className="font-mono text-text-primary">{detail.stock_exit_reference}</span></>}</>
                : 'Sem entrada em stock'}
            </p>
            <p className="text-[12px] text-text-muted">Registada por {detail.created_by || '-'} em {new Date(detail.created_at).toLocaleString('pt-PT')}{detail.description ? ' · ' + detail.description : ''}</p>
            {detailError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{detailError}</div>}
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

      <SupplierPaymentModal invoices={paying} onClose={() => setPaying(null)}
        onPaid={(payment) => { setPaying(null); setSelected([]); setNotice('Pagamento ' + payment.reference + ' registado (' + kz(payment.amount) + ') - ' + payment.supplier_name); load(); }} />
    </main>
  );
}

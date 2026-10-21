import { useEffect, useMemo, useState } from 'react';
import { Send, Plus, Loader2, Trash2, Ban, FileText, Eye, Receipt } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import DateInput from '../components/DateInput';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { useCan } from '../utils/permissions';
import { listCustomers } from '../api/customers';
import { listSuppliers } from '../api/suppliers';
import { listProducts } from '../api/products';
import { listWarehouses } from '../api/stock';
import { listPurchaseInvoices } from '../api/purchases';
import { listActivities } from '../api/activity';
import { listGuias, getGuia, createGuia, cancelGuia, fetchGuiaPdfBlob, invoiceGuias } from '../api/guias';
import { useToastState } from '../components/Toaster';

// Guias (goods_movement_service): the documents that travel with the goods - GR to a customer, GT between two
// warehouses of the company, GD back to a supplier. Issued like an invoice (series, hash, ATCUD), they move the stock;
// cancelled with a reason, the goods come back. An invoiced GR cannot be cancelled. The GR of a customer are invoiced
// together: one Fatura with their lines, without taking the goods out of the stock again.
const TYPES = [{ value: 'GR', label: 'Guia de Remessa' }, { value: 'GT', label: 'Guia de Transporte' }, { value: 'GD', label: 'Guia de Devolução' }];
const TYPE_LABEL = Object.fromEntries(TYPES.map((t) => [t.value, t.label]));
const STATUS = { EMITIDA: ['Emitida', 'text-success bg-success/10'], FATURADA: ['Faturada', 'text-text-primary bg-text-muted/15'], ANULADA: ['Anulada', 'text-danger bg-danger/10'] };
const inputCls = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const cellCls = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5 whitespace-nowrap';
const kz = (v) => formatKz(v) + ' Kz';
const round2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;
const pad = (n) => String(n).padStart(2, '0');

function todayIso() {
  const d = new Date();
  return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}

function nowLocal() {  // value of a datetime-local input: now, in the browser's time
  const d = new Date();
  return todayIso() + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
}

const when = (v) => (v ? new Date(v).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Luanda' }) : '-');
// A customer in one of these states receives no guide (the server refuses it too)
const BLOCKED_CUSTOMER = ['BLOQUEADO', 'ELIMINADO', 'INACTIVO', 'SUSPENSO'];

const emptyLine = () => ({ productId: '', saleUnitId: '', quantity: '1', unitPrice: '' });

export default function Guias() {
  const can = useCan();
  const [guias, setGuias] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useToastState('error');
  const [filters, setFilters] = useState({ type: '', status: '', dateFrom: todayIso().slice(0, 8) + '01', dateTo: todayIso() });
  const [customers, setCustomers] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [products, setProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [supplierInvoices, setSupplierInvoices] = useState([]);

  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useToastState('error');
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useToastState('error');
  const [cancelReason, setCancelReason] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [pdf, setPdf] = useState(null);

  // invoicing: the GR ticked in the list (of one customer), the activity whose FT series the invoice takes
  const [selected, setSelected] = useState([]);
  const [activities, setActivities] = useState([]);
  const [invoicing, setInvoicing] = useState(null);  // the GR being invoiced
  const [invoiceActivity, setInvoiceActivity] = useState('');
  const [invoiceError, setInvoiceError] = useToastState('error');
  const [invoiceSaving, setInvoiceSaving] = useState(false);
  const [notice, setNotice] = useToastState('success');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const rows = await listGuias(filters);
      setGuias(rows);
      // a ticked guide stays ticked only while it is still in the list and still to invoice
      setSelected((sel) => sel.filter((id) => rows.some((g) => g.id === id && g.status === 'EMITIDA')));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar as guias'));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    listCustomers().then((d) => setCustomers(d.filter((c) => c.is_active !== false && !BLOCKED_CUSTOMER.includes(c.status)))).catch(() => {});
    listSuppliers().then((d) => setSuppliers(d.filter((s) => s.is_active))).catch(() => {});
    listProducts().then((d) => setProducts(d.filter((p) => p.is_active && p.managed_by_stock !== false))).catch(() => {});
    listWarehouses().then((d) => setWarehouses(d.filter((w) => w.is_active))).catch(() => {});
    if (can('guias:invoice')) listActivities().then((d) => setActivities(d.filter((a) => a.is_active))).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // a return (GD) may name the supplier's purchase invoice
  useEffect(() => {
    if (!form || form.type !== 'GD' || !form.supplierId) { setSupplierInvoices([]); return; }
    listPurchaseInvoices({ supplierId: form.supplierId, status: 'REGISTADA' }).then(setSupplierInvoices).catch(() => setSupplierInvoices([]));
  }, [form?.type, form?.supplierId]); // eslint-disable-line react-hooks/exhaustive-deps

  const productById = useMemo(() => Object.fromEntries(products.map((p) => [p.id, p])), [products]);
  const warehouseById = useMemo(() => Object.fromEntries(warehouses.map((w) => [w.id, w])), [warehouses]);

  function openForm() {
    const central = warehouses[0];
    setForm({ type: '', originId: central?.id || '', customerId: '', destinationId: '', supplierId: '', purchaseInvoiceId: '',
      startTime: nowLocal(), startTimeEdited: false, vehicle: '', loadAddress: central?.address || central?.name || '', unloadAddress: '', notes: '', lines: [emptyLine()] });
    setFormError('');
  }

  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const updateLine = (idx, patch) => setForm((f) => ({ ...f, lines: f.lines.map((l, i) => (i === idx ? { ...l, ...patch } : l)) }));

  // the receiver proposes the unloading place: the customer's or supplier's address, the destination warehouse's
  function chooseParty(patch, address) {
    set({ ...patch, unloadAddress: address || '' });
  }

  const unitOf = (l) => (productById[l.productId]?.sale_units || []).find((u) => u.id === l.saleUnitId) || null;
  // the proposed price of a line: a GR the sale price of its unit, a GT / GD the current cost of the goods
  function proposedPrice(l) {
    const p = productById[l.productId];
    if (!p || !form.type) return 0;
    const unit = unitOf(l);
    if (form.type === 'GR') return unit ? Number(unit.price) : Number(p.price || 0);
    return Number(p.average_cost ?? p.purchase_price ?? 0) * (unit ? Number(unit.factor) : 1);
  }
  const lineNet = (l) => round2((parseFloat(l.quantity) || 0) * (l.unitPrice !== '' ? parseFloat(l.unitPrice) || 0 : proposedPrice(l)));
  const total = form ? form.lines.reduce((s, l) => s + lineNet(l), 0) : 0;

  const partyOk = form && ((form.type === 'GR' && form.customerId) || (form.type === 'GT' && form.destinationId && form.destinationId !== form.originId) || (form.type === 'GD' && form.supplierId));
  const formValid = form && form.originId && partyOk && form.unloadAddress.trim() && form.startTime
    && form.lines.length > 0 && form.lines.every((l) => l.productId && parseFloat(l.quantity) > 0);

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setFormError('');
    try {
      const created = await createGuia({
        movement_type: form.type, origin_warehouse_id: form.originId, // not changed: the server starts the transport at the moment of issue (the form may stay open for a while)
        start_time: form.startTimeEdited ? new Date(form.startTime).toISOString() : null,
        customer_id: form.type === 'GR' ? form.customerId : null, destination_warehouse_id: form.type === 'GT' ? form.destinationId : null,
        supplier_id: form.type === 'GD' ? form.supplierId : null, purchase_invoice_id: form.type === 'GD' && form.purchaseInvoiceId ? form.purchaseInvoiceId : null,
        load_address: form.loadAddress || null, unload_address: form.unloadAddress, vehicle_plate: form.vehicle || null, notes: form.notes || null,
        lines: form.lines.map((l) => ({ product_id: l.productId, sale_unit_id: l.saleUnitId || null, quantity: parseFloat(l.quantity) || 0,
          unit_price: l.unitPrice !== '' ? parseFloat(l.unitPrice) : null })),
      });
      setForm(null);
      setCancelReason('');
      setDetailError('');
      setDetail(created);
      load();
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao emitir a guia'));
    } finally {
      setSaving(false);
    }
  }

  async function openDetail(id) {
    setCancelReason('');
    setDetailError('');
    try {
      setDetail(await getGuia(id));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao abrir a guia'));
    }
  }

  async function cancel() {
    setCancelling(true);
    setDetailError('');
    try {
      setDetail(await cancelGuia(detail.id, cancelReason));
      setCancelReason('');
      load();
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao anular a guia'));
    } finally {
      setCancelling(false);
    }
  }

  // a GR can be ticked when issued and of the same customer as the ones already ticked
  const selectedCustomer = guias.find((g) => g.id === selected[0])?.customer_id;
  const canTick = (g) => g.movement_type === 'GR' && g.status === 'EMITIDA' && (!selectedCustomer || g.customer_id === selectedCustomer);
  const toggle = (id) => setSelected((sel) => (sel.includes(id) ? sel.filter((x) => x !== id) : [...sel, id]));

  function openInvoicing(rows) {
    setInvoicing(rows);
    setInvoiceActivity(activities.length === 1 ? activities[0].id : '');
    setInvoiceError('');
  }

  async function submitInvoice() {
    setInvoiceSaving(true);
    setInvoiceError('');
    try {
      const inv = await invoiceGuias(invoicing.map((g) => g.id), invoiceActivity);
      setNotice('Fatura ' + inv.reference + ' emitida (' + kz(inv.total) + ') para ' + invoicing.map((g) => g.reference).join(', '));
      const refreshed = detail && invoicing.some((g) => g.id === detail.id) ? await getGuia(detail.id) : null;
      if (refreshed) setDetail(refreshed);
      setInvoicing(null);
      setSelected([]);
      load();
    } catch (err) {
      setInvoiceError(extractErrorMessage(err, 'Erro ao faturar as guias'));
    } finally {
      setInvoiceSaving(false);
    }
  }

  async function openPdf(guia) {
    try {
      setPdf({ url: await fetchGuiaPdfBlob(guia.id), title: guia.type_label + ' ' + guia.reference });
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao gerar o PDF'));
    }
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-start justify-between gap-3 mb-6 flex-wrap">
        <div>
          <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
            <Send size={22} className="text-accent" /> Guias
          </h2>
          <p className="text-text-muted text-sm">Remessa a um cliente, transporte entre armazéns, devolução a um fornecedor - a mercadoria sai do stock com a guia</p>
        </div>
        <div className="flex items-center gap-2.5">
          {can('guias:invoice') && selected.length > 0 && (
            <button onClick={() => openInvoicing(guias.filter((g) => selected.includes(g.id)))} className="border border-accent text-accent hover:bg-accent/10 font-semibold text-sm rounded-md px-5 py-2.5 flex items-center gap-2 cursor-pointer">
              <Receipt size={16} /> Faturar {selected.length} {selected.length === 1 ? 'guia' : 'guias'}
            </button>
          )}
          {can('guias:manage') && (
            <button onClick={openForm} className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md px-5 py-2.5 flex items-center gap-2 cursor-pointer">
              <Plus size={16} /> Nova guia
            </button>
          )}
        </div>
      </div>

      <div className="flex items-end gap-2.5 mb-5 flex-wrap">
        <div className="w-56">
          <label className={labelCls}>Tipo</label>
          <Select value={filters.type} onChange={(v) => setFilters((f) => ({ ...f, type: v }))} options={[{ value: '', label: 'Todas' }, ...TYPES]} />
        </div>
        <div className="w-40">
          <label className={labelCls}>Estado</label>
          <Select value={filters.status} onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
            options={[{ value: '', label: 'Todos' }, { value: 'EMITIDA', label: 'Emitida' }, { value: 'FATURADA', label: 'Faturada' }, { value: 'ANULADA', label: 'Anulada' }]} />
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

      {can('guias:invoice') && (
        <p className="text-[12px] text-text-muted mb-3">Para faturar, marque as guias de remessa emitidas de um cliente - uma fatura para todas.</p>
      )}

      <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
        {loading ? (
          <div className="flex justify-center py-12"><Loader2 size={18} className="animate-spin text-accent" /></div>
        ) : guias.length === 0 ? (
          <p className="text-text-muted text-[13px] text-center py-12">Nenhuma guia neste período</p>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border">
              {can('guias:invoice') && <th className={th + ' w-10'} />}
              <th className={th + ' text-left'}>Número</th><th className={th + ' text-left'}>Tipo</th><th className={th + ' text-left'}>Início do transporte</th>
              <th className={th + ' text-left'}>Destinatário</th><th className={th + ' text-left'}>Carga</th><th className={th + ' text-left'}>Viatura</th>
              <th className={th + ' text-right'}>Total</th><th className={th + ' text-left'}>Estado</th><th className={th + ' text-right'}>Ações</th>
            </tr></thead>
            <tbody>
              {guias.map((g) => (
                <tr key={g.id} className={'border-b border-border last:border-0 ' + (g.status === 'ANULADA' ? 'opacity-50' : '') + (selected.includes(g.id) ? ' bg-accent/5' : '')}>
                  {can('guias:invoice') && (
                    <td className="px-3 py-2.5 text-center">
                      {g.movement_type === 'GR' && g.status === 'EMITIDA' && (
                        <input type="checkbox" checked={selected.includes(g.id)} disabled={!selected.includes(g.id) && !canTick(g)} onChange={() => toggle(g.id)}
                          title={!selected.includes(g.id) && !canTick(g) ? 'Outro cliente: uma fatura é de um só cliente' : 'Marcar para faturar'}
                          className="w-4 h-4 accent-accent cursor-pointer disabled:cursor-not-allowed disabled:opacity-30" />
                      )}
                    </td>
                  )}
                  <td className="px-3 py-2.5 font-mono text-text-primary whitespace-nowrap">{g.reference}</td>
                  <td className="px-3 py-2.5 text-text-muted">{g.type_label}</td>
                  <td className="px-3 py-2.5 font-mono text-[12px] text-text-muted whitespace-nowrap">{when(g.start_time)}</td>
                  <td className="px-3 py-2.5 text-text-primary">{g.party}</td>
                  <td className="px-3 py-2.5 text-text-muted">{g.origin_warehouse}</td>
                  <td className="px-3 py-2.5 font-mono text-[12px] text-text-muted">{g.vehicle_plate || '-'}</td>
                  <td className="px-3 py-2.5 text-right font-mono font-semibold text-text-primary whitespace-nowrap">{kz(g.gross_total)}</td>
                  <td className="px-3 py-2.5"><span className={'text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded ' + STATUS[g.status][1]}>{STATUS[g.status][0]}</span></td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => openDetail(g.id)} className="inline-flex items-center gap-1.5 border border-border hover:border-accent hover:text-accent text-text-primary text-[12px] font-medium px-2.5 py-1.5 rounded-md cursor-pointer">
                      <Eye size={14} /> Ver
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal open={!!form} onClose={() => setForm(null)} title="Nova guia" maxWidthClass="max-w-6xl">
        {form && (
          <form onSubmit={submit} className="flex flex-col gap-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <div>
                <label className={labelCls}>Tipo de guia *</label>
                <Select value={form.type} onChange={(v) => set({ type: v, customerId: '', destinationId: '', supplierId: '', purchaseInvoiceId: '', unloadAddress: '',
                  lines: form.lines.map((l) => ({ ...l, unitPrice: '' })) })} placeholder="Selecionar" options={TYPES} />
              </div>
              <div>
                <label className={labelCls}>Armazém de carga *</label>
                <Select value={form.originId} onChange={(v) => set({ originId: v, loadAddress: warehouseById[v]?.address || warehouseById[v]?.name || '' })}
                  placeholder="Selecionar" options={warehouses.map((w) => ({ value: w.id, label: w.name }))} />
              </div>
              {!form.type && (
                <div className="md:col-span-2">
                  <label className={labelCls}>Destinatário *</label>
                  <p className={inputCls + ' text-text-muted py-[11px]'}>Escolha primeiro o tipo de guia</p>
                </div>
              )}
              {form.type === 'GR' && (
                <div className="md:col-span-2">
                  <label className={labelCls}>Cliente *</label>
                  <Select value={form.customerId} onChange={(v) => chooseParty({ customerId: v }, customers.find((c) => c.id === v)?.address)} placeholder="Selecionar"
                    options={customers.map((c) => ({ value: c.id, label: c.name + (c.nif ? ' · ' + c.nif : '') }))} />
                </div>
              )}
              {form.type === 'GT' && (
                <div className="md:col-span-2">
                  <label className={labelCls}>Armazém de descarga *</label>
                  <Select value={form.destinationId} onChange={(v) => chooseParty({ destinationId: v }, warehouseById[v]?.address || warehouseById[v]?.name)} placeholder="Selecionar"
                    options={warehouses.filter((w) => w.id !== form.originId).map((w) => ({ value: w.id, label: w.name }))} />
                </div>
              )}
              {form.type === 'GD' && (
                <>
                  <div>
                    <label className={labelCls}>Fornecedor *</label>
                    <Select value={form.supplierId} onChange={(v) => chooseParty({ supplierId: v, purchaseInvoiceId: '' }, suppliers.find((s) => s.id === v)?.address)} placeholder="Selecionar"
                      options={suppliers.map((s) => ({ value: s.id, label: s.name }))} />
                  </div>
                  <div>
                    <label className={labelCls}>Fatura de compra</label>
                    <Select value={form.purchaseInvoiceId} onChange={(v) => set({ purchaseInvoiceId: v })} placeholder={form.supplierId ? 'Nenhuma' : 'Escolha o fornecedor'}
                      options={[{ value: '', label: 'Nenhuma' }, ...supplierInvoices.map((i) => ({ value: i.id, label: i.reference + ' · ' + i.supplier_document }))]} />
                  </div>
                </>
              )}
              <div>
                <label className={labelCls}>Início do transporte *</label>
                <input type="datetime-local" value={form.startTime} onChange={(e) => set({ startTime: e.target.value, startTimeEdited: true })} className={inputCls} />
                {!form.startTimeEdited && <p className="text-[11px] text-text-muted mt-1">Se não alterar, conta a hora da emissão da guia</p>}
              </div>
              <div>
                <label className={labelCls}>Viatura (matrícula)</label>
                <input value={form.vehicle} onChange={(e) => set({ vehicle: e.target.value })} placeholder="Ex: LD-12-34-AB" className={inputCls + ' font-mono uppercase'} />
              </div>
              <div>
                <label className={labelCls}>Local de carga</label>
                <input value={form.loadAddress} onChange={(e) => set({ loadAddress: e.target.value })} className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Local de descarga *</label>
                <input value={form.unloadAddress} onChange={(e) => set({ unloadAddress: e.target.value })} placeholder="Morada de entrega" className={inputCls} />
              </div>
            </div>

            <div className="border border-border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border">
                  <th className={th + ' text-left'}>Artigo</th><th className={th + ' text-left w-28'}>Un.</th><th className={th + ' text-right w-28'}>Qtd</th>
                  <th className={th + ' text-right w-36'}>{form.type === 'GR' ? 'Preço s/ IVA' : form.type ? 'Custo' : 'Preço'}</th><th className={th + ' text-right w-36'}>Valor</th><th className={th + ' w-10'}></th>
                </tr></thead>
                <tbody>
                  {form.lines.map((l, idx) => {
                    const p = productById[l.productId];
                    const unit = unitOf(l);
                    return (
                      <tr key={idx} className="border-b border-border last:border-0 align-top">
                        <td className="px-2 py-2 min-w-[240px]">
                          <Select value={l.productId} onChange={(v) => updateLine(idx, { productId: v, saleUnitId: '', unitPrice: '' })} placeholder="Selecionar"
                            options={products.filter((x) => form.type !== 'GR' || !x.is_raw_material).map((x) => ({ value: x.id, label: x.code + ' - ' + x.name }))} />
                        </td>
                        <td className="px-2 py-2">
                          {(p?.sale_units || []).length > 0 ? (
                            <Select value={l.saleUnitId || 'base'} onChange={(v) => updateLine(idx, { saleUnitId: v === 'base' ? '' : v, unitPrice: '' })}
                              options={[{ value: 'base', label: p.unit_of_measure_code || 'Base' }, ...p.sale_units.map((u) => ({ value: u.id, label: u.unit_of_measure_code }))]} />
                          ) : <p className="px-1 py-3 font-mono text-[13px] text-text-muted">{p?.unit_of_measure_code || '-'}</p>}
                        </td>
                        <td className="px-2 py-2">
                          <input type="number" min="0" step="any" value={l.quantity} onChange={(e) => updateLine(idx, { quantity: e.target.value })} className={cellCls + ' text-right font-mono min-w-[88px]'} />
                          {unit && parseFloat(l.quantity) > 0 && <p className="text-[10.5px] text-text-muted mt-0.5 text-right whitespace-nowrap">= {(parseFloat(l.quantity) * Number(unit.factor)).toLocaleString('pt-PT', { maximumFractionDigits: 3 })} {p.unit_of_measure_code}</p>}
                        </td>
                        <td className="px-2 py-2">
                          <input type="number" min="0" step="any" value={l.unitPrice} placeholder={p ? String(round2(proposedPrice(l))) : ''} onChange={(e) => updateLine(idx, { unitPrice: e.target.value })} className={cellCls + ' text-right font-mono min-w-[120px]'} />
                        </td>
                        <td className="px-3 py-3 text-right font-mono text-text-primary whitespace-nowrap">{kz(lineNet(l))}</td>
                        <td className="px-2 py-2 text-center">
                          {form.lines.length > 1 && <button type="button" onClick={() => set({ lines: form.lines.filter((_, i) => i !== idx) })} className="text-text-muted hover:text-danger cursor-pointer mt-3"><Trash2 size={15} /></button>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <button type="button" onClick={() => set({ lines: [...form.lines, emptyLine()] })}
              className="self-start flex items-center gap-1.5 border border-dashed border-accent/60 hover:border-accent text-accent text-[13px] font-medium rounded-md px-3.5 py-2 cursor-pointer">
              <Plus size={15} /> Linha
            </button>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
              <div className="md:col-span-2">
                <label className={labelCls}>Observações</label>
                <input value={form.notes} onChange={(e) => set({ notes: e.target.value })} className={inputCls} />
              </div>
              <div className="bg-bg-inset border border-border rounded-md px-4 py-2.5 text-right">
                <p className="text-[11px] uppercase tracking-wide text-text-muted">{form.type === 'GR' ? 'Valor sem IVA' : form.type ? 'Valor ao custo' : 'Valor'}</p>
                <p className="font-mono font-semibold text-lg text-text-primary">{kz(total)}</p>
              </div>
            </div>
            <p className="text-[12px] text-text-muted">
              {form.type === 'GR' && 'A mercadoria sai do armazém de carga ao emitir; a fatura feita a partir desta guia não a volta a tirar. O IVA de cada artigo é aplicado na guia.'}
              {form.type === 'GT' && 'A mercadoria passa do armazém de carga para o de descarga ao emitir.'}
              {form.type === 'GD' && 'A mercadoria sai do armazém de carga e volta ao fornecedor ao emitir.'}
            </p>

            <button type="submit" disabled={saving || !formValid} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
              {saving ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />} Emitir {form.type ? TYPE_LABEL[form.type].toLowerCase() : 'guia'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail ? detail.type_label + ' ' + detail.reference : ''} maxWidthClass="max-w-5xl">
        {detail && (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[13px]">
              <div><p className={labelCls}>{detail.movement_type === 'GR' ? 'Cliente' : detail.movement_type === 'GT' ? 'Armazém de descarga' : 'Fornecedor'}</p>
                <p className="text-text-primary">{detail.party}</p>{detail.party_nif && <p className="font-mono text-[11px] text-text-muted">{detail.party_nif}</p>}
                {detail.purchase_invoice && <p className="text-[11px] text-text-muted">Fatura {detail.purchase_invoice}</p>}</div>
              <div><p className={labelCls}>Carga</p><p className="text-text-primary">{detail.origin_warehouse}</p>{detail.load_address !== detail.origin_warehouse && <p className="text-[11px] text-text-muted">{detail.load_address}</p>}</div>
              <div><p className={labelCls}>Descarga</p><p className="text-text-primary">{detail.unload_address}</p></div>
              <div><p className={labelCls}>Início do transporte</p><p className="text-text-primary">{when(detail.start_time)}</p><p className="font-mono text-[11px] text-text-muted">{detail.vehicle_plate || 'sem viatura'}</p></div>
            </div>
            {detail.status === 'FATURADA' && (
              <div className="bg-bg-inset border-l-2 border-success text-text-primary px-3.5 py-2.5 text-[13px] rounded-r">
                Faturada na fatura <span className="font-mono font-semibold">{detail.invoice_reference}</span> - a mercadoria saiu do stock com a guia
              </div>
            )}
            {detail.status === 'ANULADA' && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
                Anulada por {detail.cancelled_by || '-'} em {when(detail.cancelled_at)}: {detail.cancel_reason}
              </div>
            )}
            <div className="border border-border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border">
                  <th className={th + ' text-left'}>Código</th><th className={th + ' text-left'}>Descrição</th><th className={th + ' text-right'}>Qtd</th>
                  <th className={th + ' text-right'}>Preço</th><th className={th + ' text-left'}>IVA</th><th className={th + ' text-right'}>Valor</th>
                </tr></thead>
                <tbody>
                  {detail.lines.map((l) => (
                    <tr key={l.position} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 font-mono text-[12px] text-text-muted">{l.product_code}</td>
                      <td className="px-3 py-2 text-text-primary">{l.description}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-muted whitespace-nowrap">{l.quantity.toLocaleString('pt-PT')}{l.unit ? ' ' + l.unit : ''}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-muted whitespace-nowrap">{kz(l.unit_price)}</td>
                      <td className="px-3 py-2 font-mono text-[12px] text-text-muted whitespace-nowrap">{detail.movement_type === 'GR' ? `${l.tax_code} ${l.vat_rate} %${l.exemption_code ? ' · ' + l.exemption_code : ''}` : '-'}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{kz(l.line_net)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[['Valor', detail.net_total], ['IVA', detail.vat_total], ['Total', detail.gross_total]].map(([label, value]) => (
                <div key={label} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5">
                  <p className="text-[10px] uppercase tracking-wide text-text-muted">{label}</p>
                  <p className="font-mono font-semibold text-text-primary">{kz(value)}</p>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between gap-3 flex-wrap text-[12px] text-text-muted">
              <p>Emitida por {detail.created_by || '-'} em {when(detail.created_at)} · ATCUD <span className="font-mono">{detail.atcud}</span>{detail.notes ? ' · ' + detail.notes : ''}</p>
              <div className="flex items-center gap-2">
                {detail.movement_type === 'GR' && detail.status === 'EMITIDA' && can('guias:invoice') && (
                  <button onClick={() => openInvoicing([detail])} className="inline-flex items-center gap-1.5 border border-accent text-accent hover:bg-accent/10 text-[12px] font-semibold px-3 py-1.5 rounded-md cursor-pointer">
                    <Receipt size={14} /> Faturar
                  </button>
                )}
                <button onClick={() => openPdf(detail)} className="inline-flex items-center gap-1.5 border border-border hover:border-accent hover:text-accent text-text-primary text-[12px] font-medium px-3 py-1.5 rounded-md cursor-pointer">
                  <FileText size={14} /> Ver PDF
                </button>
              </div>
            </div>
            {detail.status === 'EMITIDA' && can('guias:manage') && (
              <div className="flex items-end gap-2 border-t border-border pt-4">
                <div className="flex-1">
                  <label className={labelCls}>Motivo da anulação</label>
                  <input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="Ex: mercadoria não saiu" className={inputCls} />
                </div>
                <button onClick={cancel} disabled={cancelling || !cancelReason.trim()} className="flex items-center gap-1.5 border border-danger/60 text-danger hover:bg-danger/10 disabled:opacity-50 text-[13px] font-medium px-4 py-2 rounded-md cursor-pointer">
                  {cancelling ? <Loader2 size={14} className="animate-spin" /> : <Ban size={14} />} Anular
                </button>
              </div>
            )}
          </div>
        )}
      </Modal>

      <Modal open={!!invoicing} onClose={() => setInvoicing(null)} title="Faturar guias de remessa" maxWidthClass="max-w-3xl" stacked>
        {invoicing && (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <p className={labelCls}>Cliente</p>
                <p className="text-text-primary text-sm py-2.5">{invoicing[0].party}</p>
              </div>
              <div>
                <label className={labelCls}>Atividade *</label>
                <Select value={invoiceActivity} onChange={setInvoiceActivity} placeholder="Selecionar"
                  options={activities.map((a) => ({ value: a.id, label: a.name }))} />
              </div>
            </div>
            <div className="border border-border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border">
                  <th className={th + ' text-left'}>Guia</th><th className={th + ' text-left'}>Data</th><th className={th + ' text-right'}>Total</th>
                </tr></thead>
                <tbody>
                  {invoicing.map((g) => (
                    <tr key={g.id} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 font-mono text-text-primary">{g.reference}</td>
                      <td className="px-3 py-2 font-mono text-[12px] text-text-muted">{when(g.start_time)}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-primary">{kz(g.gross_total)}</td>
                    </tr>
                  ))}
                  <tr className="bg-bg-inset">
                    <td className="px-3 py-2 font-semibold text-text-primary" colSpan={2}>Total da fatura</td>
                    <td className="px-3 py-2 text-right font-mono font-semibold text-text-primary">{kz(round2(invoicing.reduce((s, g) => s + g.gross_total, 0)))}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="text-[12px] text-text-muted">
              Uma Fatura (FT) com as linhas das guias, ao preço de cada guia; a mercadoria já saiu do stock com as guias e não volta a sair.
              As guias passam a «Faturada». O pagamento regista-se depois com um recibo.
            </p>
            <button onClick={submitInvoice} disabled={invoiceSaving || !invoiceActivity} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
              {invoiceSaving ? <Loader2 size={17} className="animate-spin" /> : <Receipt size={17} />} Emitir fatura
            </button>
          </div>
        )}
      </Modal>

      <Modal open={!!pdf} onClose={() => { if (pdf?.url) URL.revokeObjectURL(pdf.url); setPdf(null); }} title={pdf?.title || ''} maxWidthClass="max-w-3xl" stacked>
        {pdf && <iframe src={pdf.url} title={pdf.title} className="w-full h-[70vh] rounded-md border border-border" />}
      </Modal>
    </main>
  );
}

import { useState, useEffect, useMemo } from 'react';
import { CakeSlice, Plus, Pencil, Loader2, Search, X, Trash2, Store, Truck, ChefHat, CheckCircle2, Undo2, Eye } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import DateInput from '../components/DateInput';
import { useCan } from '../utils/permissions';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';
import { listOrders, getOrderOptions, createOrder, updateOrder, setOrderStatus, cancelOrder, getOrderCancelInfo } from '../api/orders';
import { listPaymentMethodPreferences } from '../api/tesouraria';
import { getMyCompanyBankAccounts } from '../api/company';
import { banksApi } from '../api/catalogs';
import { useAuthStore } from '../store/authStore';

// Encomendas: what customers ordered to be made and handed over later - by delivery date, with a production note per
// line, moved through production (Encomendada -> Em produção -> Pronta). The deposit and the delivery are done at the
// till (Caixa → Encomendas); here an invoiced order is cancelled by the gestor, its deposit given back or kept.

const STATUS_STYLE = {
  ENCOMENDADA: 'bg-sky-500/15 text-sky-400', EM_PRODUCAO: 'bg-amber-500/15 text-amber-500', PRONTA: 'bg-success/15 text-success',
  ENTREGUE: 'bg-bg-inset text-text-muted', CANCELADA: 'bg-danger/15 text-danger',
};
const FILTERS = [
  { key: 'ABERTAS', label: 'Por entregar' }, { key: 'HOJE', label: 'Hoje' }, { key: 'AMANHA', label: 'Amanhã' },
  { key: 'SEMANA', label: 'Próximos 7 dias' }, { key: 'TODAS', label: 'Todas' },
];
const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';

function isoDay(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

// a delivery moment, as Luanda sees it: 'DD/MM/YYYY HH:MM'
function when(value) {
  const d = new Date(value);
  const p = (n) => String(n).padStart(2, '0');
  return p(d.getDate()) + '/' + p(d.getMonth() + 1) + '/' + d.getFullYear() + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}

function localParts(value) {
  const d = new Date(value);
  const p = (n) => String(n).padStart(2, '0');
  return { date: d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()), time: p(d.getHours()) + ':' + p(d.getMinutes()) };
}

const emptyLine = () => ({ key: Math.random().toString(36).slice(2), article: '', quantity: '1', price: '', note: '' });
const emptyForm = () => ({ customerId: '', activityId: '', date: isoDay(1), time: '10:00', mode: 'LOJA', address: '', contactName: '', contactPhone: '', notes: '', lines: [emptyLine()] });

export default function Encomendas() {
  const can = useCan();
  const canManage = can('orders:manage');
  const canProduce = can('orders:production');
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('ABERTAS');
  const [search, setSearch] = useState('');
  const [busyId, setBusyId] = useState(null);

  const [options, setOptions] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null); // the order changed, or null for a new one
  const [viewing, setViewing] = useState(null); // an order only shown (not editable)
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [cancelling, setCancelling] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelInfo, setCancelInfo] = useState(null); // invoiced? paid? the tills that can give cash back
  const [deposit, setDeposit] = useState(''); // DEVOLVER | RETER
  const [refund, setRefund] = useState({ methodId: '', posId: '', bankId: '' });
  const [refundMethods, setRefundMethods] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);
  const [banks, setBanks] = useState([]);
  const isGestor = useAuthStore((st) => st.user?.role) === 'GESTOR';

  const params = useMemo(() => {
    if (filter === 'ABERTAS') return { status_filter: 'ABERTAS' };
    if (filter === 'HOJE') return { date_from: isoDay(0), date_to: isoDay(0) };
    if (filter === 'AMANHA') return { date_from: isoDay(1), date_to: isoDay(1) };
    if (filter === 'SEMANA') return { date_from: isoDay(0), date_to: isoDay(7) };
    return {};
  }, [filter]);

  async function load() {
    setLoading(true);
    try {
      setOrders(await listOrders({ ...params, search: search.trim() || undefined }));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar as encomendas'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(t);
  }, [params, search]); // eslint-disable-line react-hooks/exhaustive-deps

  async function ensureOptions() {
    if (options) return options;
    const data = await getOrderOptions();
    setOptions(data);
    return data;
  }

  async function openNew() {
    try {
      const data = await ensureOptions();
      if (!data.activities.length) {
        toast.error('Nenhuma atividade da empresa tem as Encomendas');
        return;
      }
      setEditing(null);
      setForm({ ...emptyForm(), activityId: data.activities.length === 1 ? data.activities[0].id : '' });
      setFormOpen(true);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao abrir o formulário'));
    }
  }

  async function openOrder(order) {
    if (!(canManage && order.editable)) {
      setViewing(order);
      return;
    }
    try {
      await ensureOptions();
      const { date, time } = localParts(order.delivery_at);
      setEditing(order);
      setForm({
        customerId: order.customer_id, activityId: order.activity_id, date, time, mode: order.delivery_mode,
        address: order.delivery_address || '', contactName: order.contact_name || '', contactPhone: order.contact_phone || '',
        notes: order.notes || '',
        lines: order.lines.map((l) => ({ key: l.id, article: (l.product_id ? 'product:' + l.product_id : 'service:' + l.service_id),
          quantity: String(l.quantity), price: String(l.unit_price), note: l.production_note || '' })),
      });
      setFormOpen(true);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao abrir a encomenda'));
    }
  }

  const articleById = useMemo(() => Object.fromEntries((options?.articles || []).map((a) => [a.kind + ':' + a.id, a])), [options]);
  const articleOptions = useMemo(() => (options?.articles || []).map((a) => ({
    value: a.kind + ':' + a.id, label: a.name + (a.code ? ' (' + a.code + ')' : '') + (a.kind === 'service' ? ' · serviço' : ''),
  })), [options]);

  function updateLine(key, patch) {
    setForm((f) => ({ ...f, lines: f.lines.map((l) => (l.key === key ? { ...l, ...patch } : l)) }));
  }

  function chooseArticle(key, value) {
    const article = articleById[value];
    updateLine(key, { article: value, price: article ? String(article.price) : '' });
  }

  const totals = useMemo(() => {
    let subtotal = 0;
    let vat = 0;
    for (const l of form.lines) {
      const a = articleById[l.article];
      const amount = (Number(l.quantity) || 0) * (Number(l.price) || 0);
      subtotal += amount;
      vat += a ? amount * Number(a.vat_rate) / 100 : 0;
    }
    return { subtotal, vat, total: subtotal + vat };
  }, [form.lines, articleById]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!form.customerId) {
      toast.error('Escolha o cliente da encomenda');
      return;
    }
    if (!form.date || !form.time) {
      toast.error('Indique a data e a hora da entrega');
      return;
    }
    if (form.mode === 'ENTREGA' && !form.address.trim()) {
      toast.error('Indique a morada de entrega');
      return;
    }
    const lines = form.lines.filter((l) => l.article);
    if (!lines.length) {
      toast.error('A encomenda deve ter pelo menos um artigo');
      return;
    }
    const payload = {
      customer_id: form.customerId, activity_id: form.activityId || null,
      delivery_at: form.date + 'T' + form.time + ':00+01:00', delivery_mode: form.mode,
      delivery_address: form.mode === 'ENTREGA' ? form.address : null,
      contact_name: form.contactName || null, contact_phone: form.contactPhone || null, notes: form.notes || null,
      lines: lines.map((l) => {
        const [kind, id] = l.article.split(':');
        return { [kind === 'product' ? 'product_id' : 'service_id']: id, quantity: Number(l.quantity),
          unit_price: l.price === '' ? null : Number(l.price), production_note: l.note || null };
      }),
    };
    setSaving(true);
    try {
      const saved = editing ? await updateOrder(editing.id, payload) : await createOrder(payload);
      toast.success((editing ? 'Encomenda alterada: ' : 'Encomenda registada: ') + saved.reference);
      setFormOpen(false);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar a encomenda'));
    } finally {
      setSaving(false);
    }
  }

  async function changeStatus(order, status) {
    setBusyId(order.id);
    try {
      const saved = await setOrderStatus(order.id, status);
      toast.success(saved.reference + ': ' + saved.status_label.toLowerCase());
      if (viewing?.id === order.id) setViewing(saved);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao mudar o estado'));
    } finally {
      setBusyId(null);
    }
  }

  async function openCancel(order) {
    setCancelReason('');
    setDeposit('');
    setRefund({ methodId: '', posId: '', bankId: '' });
    setCancelInfo(null);
    setCancelling(order);
    try {
      const info = await getOrderCancelInfo(order.id);
      setCancelInfo(info);
      if (info.invoiced && info.paid > 0) {
        listPaymentMethodPreferences().then((m) => setRefundMethods(m.filter((x) => x.allows_payment))).catch(() => setRefundMethods([]));
        getMyCompanyBankAccounts().then((a) => setBankAccounts(a.filter((x) => x.is_active))).catch(() => setBankAccounts([]));
        banksApi.list().then(setBanks).catch(() => setBanks([]));
      }
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao preparar o cancelamento'));
    }
  }

  const refundMethod = refundMethods.find((m) => m.id === refund.methodId);

  async function confirmCancel(e) {
    e.preventDefault();
    if (cancelReason.trim().length < 3) {
      toast.error('Indique o motivo do cancelamento');
      return;
    }
    const paid = cancelInfo?.invoiced ? cancelInfo.paid : 0;
    if (paid > 0 && !deposit) {
      toast.error('Escolha se o valor pago é devolvido ou retido');
      return;
    }
    let refundPayload = null;
    if (paid > 0 && deposit === 'DEVOLVER') {
      if (!refund.methodId) { toast.error('Escolha como o valor pago é devolvido'); return; }
      if (refundMethod?.is_cash && !refund.posId) { toast.error('Escolha a caixa de onde sai o numerário'); return; }
      if (refundMethod?.uses_bank_account && !refund.bankId) { toast.error('Escolha a conta bancária de onde sai a devolução'); return; }
      refundPayload = { payment_method_id: refund.methodId, pos_id: refundMethod?.is_cash ? refund.posId : null,
        bank_account_id: refundMethod?.uses_bank_account ? refund.bankId : null };
    }
    setBusyId(cancelling.id);
    try {
      const saved = await cancelOrder(cancelling.id, cancelReason, paid > 0 ? deposit : null, refundPayload);
      toast.success('Encomenda cancelada: ' + saved.reference);
      setCancelling(null);
      setViewing(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao cancelar a encomenda'));
    } finally {
      setBusyId(null);
    }
  }

  const now = Date.now();
  const open = (o) => ['ENCOMENDADA', 'EM_PRODUCAO', 'PRONTA'].includes(o.status);

  function productionButtons(o, compact = true) {
    if (!canProduce || !open(o)) return null;
    const base = 'inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md border text-[12px] font-medium transition-colors cursor-pointer disabled:opacity-50 ';
    return (
      <>
        {o.status === 'ENCOMENDADA' && (
          <button type="button" disabled={busyId === o.id} onClick={() => changeStatus(o, 'EM_PRODUCAO')} className={base + 'border-amber-500/50 text-amber-500 hover:bg-amber-500/10'}>
            <ChefHat size={13} /> {compact ? 'Produzir' : 'Iniciar produção'}
          </button>
        )}
        {o.status === 'EM_PRODUCAO' && (
          <button type="button" disabled={busyId === o.id} onClick={() => changeStatus(o, 'PRONTA')} className={base + 'border-success/50 text-success hover:bg-success/10'}>
            <CheckCircle2 size={13} /> Pronta
          </button>
        )}
        {o.status !== 'ENCOMENDADA' && (
          <button type="button" disabled={busyId === o.id} title="Voltar ao estado anterior" onClick={() => changeStatus(o, o.status === 'PRONTA' ? 'EM_PRODUCAO' : 'ENCOMENDADA')} className={base + 'border-border text-text-muted hover:text-text-primary'}>
            <Undo2 size={13} />
          </button>
        )}
      </>
    );
  }

  // an invoiced order: its lines are those of its Fatura - only the delivery, the contact and the notes change
  const locked = !!editing?.lines_locked;

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <CakeSlice size={22} className="text-accent" />
        Encomendas
      </h2>
      <p className="text-text-muted text-sm mb-5">O que os clientes encomendam para levantar ou receber mais tarde: data de entrega, notas de produção e estado</p>

      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" onClick={() => setFilter(f.key)}
              className={'h-9 px-3.5 rounded-md text-sm font-medium border transition-colors cursor-pointer ' + (filter === f.key ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary')}>
              {f.label}
            </button>
          ))}
          <div className="relative w-full sm:w-[260px]">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
            <input type="text" placeholder="Cliente, telefone..." value={search} onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
        </div>
        {canManage && (
          <button type="button" onClick={openNew} className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer">
            <Plus size={16} /> Nova encomenda
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>
      ) : orders.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <CakeSlice size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium">Nenhuma encomenda</p>
        </div>
      ) : (
        <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
                <th className="text-left px-4 py-2.5">Entrega</th>
                <th className="text-left px-4 py-2.5">N.º</th>
                <th className="text-left px-4 py-2.5">Cliente</th>
                <th className="text-left px-4 py-2.5">Artigos</th>
                <th className="text-right px-4 py-2.5">Total</th>
                <th className="text-left px-4 py-2.5">Estado</th>
                <th className="text-right px-4 py-2.5">Ações</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => {
                const late = open(o) && new Date(o.delivery_at).getTime() < now;
                return (
                  <tr key={o.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors align-top">
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      <div className={'font-mono text-[13px] ' + (late ? 'text-danger font-semibold' : 'text-text-primary')}>{when(o.delivery_at)}</div>
                      <div className="text-[11.5px] text-text-muted flex items-center gap-1">
                        {o.delivery_mode === 'ENTREGA' ? <><Truck size={12} /> Entrega</> : <><Store size={12} /> Levanta na loja</>}
                        {late && <span className="text-danger"> · atrasada</span>}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[12.5px] text-text-primary whitespace-nowrap">{o.reference}</td>
                    <td className="px-4 py-2.5">
                      <div className="text-text-primary font-medium">{o.customer_name}</div>
                      <div className="text-[11.5px] text-text-muted">{o.contact_phone || o.customer_phone || ''}</div>
                    </td>
                    <td className="px-4 py-2.5 text-text-muted max-w-[360px]">
                      {o.lines.map((l) => (
                        <div key={l.id} className="truncate"><span className="text-text-primary">{l.quantity} × {l.description}</span>{l.production_note ? ' · ' + l.production_note : ''}</div>
                      ))}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono whitespace-nowrap text-text-primary">
                      {formatKz(o.total)} Kz
                      {o.invoice_id && (
                        <div className="text-[11.5px] text-text-muted">
                          {o.invoice_reference} · {o.due > 0.005 ? <span className="text-amber-500">falta {formatKz(o.due)}</span> : <span className="text-success">pago</span>}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-2.5"><span className={'inline-block px-2 py-0.5 rounded text-[11.5px] font-medium ' + STATUS_STYLE[o.status]}>{o.status_label}</span></td>
                    <td className="px-4 py-2.5 text-right whitespace-nowrap">
                      <div className="inline-flex items-center gap-1.5">
                        {productionButtons(o)}
                        <button type="button" title={canManage && o.editable ? 'Alterar' : 'Ver'} onClick={() => openOrder(o)} className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                          {canManage && o.editable ? <Pencil size={13} /> : <Eye size={13} />}
                        </button>
                        {canManage && open(o) && (
                          <button type="button" title="Cancelar" onClick={() => openCancel(o)} className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger hover:border-danger transition-colors cursor-pointer">
                            <X size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={editing ? 'Alterar encomenda ' + editing.reference : 'Nova encomenda'} maxWidthClass="max-w-5xl">
        <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className={(options?.activities || []).length > 1 ? '' : 'sm:col-span-2'}>
              <label className={labelClass}>Cliente *</label>
              <Select value={form.customerId} disabled={locked} onChange={(v) => setForm((p) => ({ ...p, customerId: v }))} placeholder="Escolher o cliente"
                options={(options?.customers || []).map((c) => ({ value: c.id, label: c.name + (c.phone_number ? ' · ' + c.phone_number : '') }))} />
            </div>
            {(options?.activities || []).length > 1 ? (
              <div>
                <label className={labelClass}>Atividade *</label>
                <Select value={form.activityId} onChange={(v) => setForm((p) => ({ ...p, activityId: v }))} placeholder="Escolher"
                  options={options.activities.map((a) => ({ value: a.id, label: a.name }))} />
              </div>
            ) : null}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={labelClass}>Data de entrega *</label>
                <DateInput value={form.date} onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))} required className={inputClass} />
              </div>
              <div>
                <label className={labelClass}>Hora *</label>
                <input type="time" value={form.time} onChange={(e) => setForm((p) => ({ ...p, time: e.target.value }))} required className={inputClass} />
              </div>
            </div>
            <div>
              <label className={labelClass}>Como é entregue</label>
              <div className="grid grid-cols-2 gap-2">
                {[['LOJA', 'Levanta na loja', Store], ['ENTREGA', 'Entrega na morada', Truck]].map(([value, label, Icon]) => (
                  <button key={value} type="button" onClick={() => setForm((p) => ({ ...p, mode: value }))}
                    className={'flex items-center justify-center gap-2 h-[42px] rounded-md border text-sm font-medium transition-colors cursor-pointer ' + (form.mode === value ? 'border-accent bg-accent/10 text-accent' : 'border-border text-text-muted hover:text-text-primary')}>
                    <Icon size={15} /> {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {/* the address (a delivery) and the contact on one line */}
          <div className={'grid grid-cols-1 gap-3 ' + (form.mode === 'ENTREGA' ? 'sm:grid-cols-3' : 'sm:grid-cols-2')}>
            {form.mode === 'ENTREGA' && (
              <div>
                <label className={labelClass}>Morada de entrega *</label>
                <input value={form.address} onChange={(e) => setForm((p) => ({ ...p, address: e.target.value }))} required className={inputClass} />
              </div>
            )}
            <div>
              <label className={labelClass}>Quem levanta / recebe (opcional)</label>
              <input value={form.contactName} onChange={(e) => setForm((p) => ({ ...p, contactName: e.target.value }))} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Telefone de contacto (opcional)</label>
              <input value={form.contactPhone} onChange={(e) => setForm((p) => ({ ...p, contactPhone: e.target.value }))} placeholder="+244..." className={inputClass} />
            </div>
          </div>

          <div>
            <p className={labelClass}>Artigos *</p>
            {locked && (
              <p className="text-[12.5px] text-amber-500 mb-2">Encomenda faturada ({editing.invoice_reference}): os artigos, as quantidades e os preços já não se alteram - só a entrega, o contacto e as notas.</p>
            )}
            <div className="flex flex-col gap-2">
              {form.lines.map((l) => {
                const a = articleById[l.article];
                const amount = (Number(l.quantity) || 0) * (Number(l.price) || 0) * (1 + (a ? Number(a.vat_rate) : 0) / 100);
                return (
                  <div key={l.key} className="grid grid-cols-12 gap-2 items-start bg-bg-inset/40 border border-border rounded-md p-2">
                    <div className="col-span-12 md:col-span-4"><Select value={l.article} disabled={locked} onChange={(v) => chooseArticle(l.key, v)} placeholder="Artigo" options={articleOptions} /></div>
                    <input type="number" min="0" step="any" value={l.quantity} readOnly={locked} onChange={(e) => updateLine(l.key, { quantity: e.target.value })} title="Quantidade" className={inputClass + ' col-span-3 md:col-span-1 text-right'} />
                    <input type="number" min="0" step="any" value={l.price} readOnly={locked || !isGestor} onChange={(e) => updateLine(l.key, { price: e.target.value })} title={isGestor ? 'Preço sem IVA' : 'Preço sem IVA (só o gestor o altera)'} placeholder="Preço" className={inputClass + ' col-span-4 md:col-span-2 text-right'} />
                    <input value={l.note} onChange={(e) => updateLine(l.key, { note: e.target.value })} placeholder="Nota de produção (ex.: Parabéns Ana)" className={inputClass + ' col-span-12 md:col-span-3 order-last md:order-none'} />
                    <div className="col-span-4 md:col-span-1 text-right font-mono text-[13px] text-text-primary pt-2.5 whitespace-nowrap">{formatKz(amount)}</div>
                    <button type="button" disabled={locked || form.lines.length === 1} onClick={() => setForm((p) => ({ ...p, lines: p.lines.filter((x) => x.key !== l.key) }))}
                      className="col-span-1 inline-flex items-center justify-center h-[42px] rounded-md text-text-muted hover:text-danger disabled:opacity-30 cursor-pointer"><Trash2 size={15} /></button>
                  </div>
                );
              })}
            </div>
            {!locked && <button type="button" onClick={() => setForm((p) => ({ ...p, lines: [...p.lines, emptyLine()] }))} className="mt-2 inline-flex items-center gap-1.5 text-sm text-accent hover:underline cursor-pointer">
              <Plus size={14} /> Adicionar artigo
            </button>}
          </div>

          <div>
            <label className={labelClass}>Observações (opcional)</label>
            <textarea value={form.notes} onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))} rows={2} className={inputClass} />
          </div>

          <div className="flex items-end justify-between gap-4 border-t border-border pt-3 flex-wrap">
            <div className="text-sm text-text-muted font-mono">Sem IVA {formatKz(totals.subtotal)} · IVA {formatKz(totals.vat)}</div>
            <div className="text-right">
              <div className="text-[11px] uppercase tracking-wide text-text-muted">Total da encomenda</div>
              <div className="font-mono font-semibold text-2xl text-text-primary">{formatKz(totals.total)} Kz</div>
            </div>
          </div>
          <button type="submit" disabled={saving} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {saving ? 'A guardar...' : editing ? 'Guardar alterações' : 'Registar encomenda'}
          </button>
        </form>
      </Modal>

      <Modal open={!!viewing} onClose={() => setViewing(null)} title={viewing ? 'Encomenda ' + viewing.reference : ''} maxWidthClass="max-w-3xl">
        {viewing && (
          <div className="flex flex-col gap-3 text-sm">
            <div className="grid grid-cols-2 gap-x-6 gap-y-2">
              <div><span className="text-text-muted">Cliente: </span><span className="text-text-primary font-medium">{viewing.customer_name}</span></div>
              <div><span className="text-text-muted">Estado: </span><span className={'inline-block px-2 py-0.5 rounded text-[11.5px] font-medium ' + STATUS_STYLE[viewing.status]}>{viewing.status_label}</span></div>
              <div><span className="text-text-muted">Entrega: </span><span className="text-text-primary font-mono">{when(viewing.delivery_at)}</span></div>
              <div><span className="text-text-muted">{viewing.delivery_mode === 'ENTREGA' ? 'Morada: ' : 'Modo: '}</span><span className="text-text-primary">{viewing.delivery_mode === 'ENTREGA' ? viewing.delivery_address : 'Levanta na loja'}</span></div>
              {(viewing.contact_name || viewing.contact_phone) && <div className="col-span-2"><span className="text-text-muted">Contacto: </span><span className="text-text-primary">{[viewing.contact_name, viewing.contact_phone].filter(Boolean).join(' · ')}</span></div>}
              {viewing.invoice_id && (
                <div className="col-span-2"><span className="text-text-muted">Fatura: </span><span className="text-text-primary font-mono">{viewing.invoice_reference}</span>
                  <span className="text-text-muted"> · pago </span><span className="font-mono text-text-primary">{formatKz(viewing.paid)}</span>
                  <span className="text-text-muted"> · falta </span><span className="font-mono text-text-primary">{formatKz(viewing.due)}</span>
                  {viewing.credit_note_reference && <span className="text-text-muted"> · {viewing.credit_note_reference}</span>}
                </div>
              )}
              {viewing.cancel_reason && <div className="col-span-2 text-danger">Cancelada: {viewing.cancel_reason}{viewing.deposit_outcome ? ' · valor pago ' + viewing.deposit_outcome.toLowerCase() : ''}</div>}
            </div>
            <table className="w-full">
              <tbody>
                {viewing.lines.map((l) => (
                  <tr key={l.id} className="border-t border-border">
                    <td className="py-1.5 pr-2 text-text-primary">{l.quantity} × {l.description}{l.production_note && <div className="text-[12px] text-amber-500">{l.production_note}</div>}</td>
                    <td className="py-1.5 text-right font-mono text-text-primary whitespace-nowrap">{formatKz(l.total)} Kz</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {viewing.notes && <p className="text-text-muted">{viewing.notes}</p>}
            <div className="flex items-center justify-between border-t border-border pt-3">
              <div className="flex gap-1.5">{productionButtons(viewing, false)}</div>
              <span className="font-mono font-semibold text-xl text-text-primary">{formatKz(viewing.total)} Kz</span>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={!!cancelling} onClose={() => setCancelling(null)} title={cancelling ? 'Cancelar a encomenda ' + cancelling.reference : ''} maxWidthClass="max-w-xl">
        <form noValidate onSubmit={confirmCancel} className="flex flex-col gap-3">
          <p className="text-sm text-text-muted">{cancelling?.customer_name} · entrega {cancelling ? when(cancelling.delivery_at) : ''}</p>
          {!cancelInfo ? (
            <div className="flex items-center justify-center py-6 text-text-muted text-sm"><Loader2 size={16} className="animate-spin mr-2" />A carregar...</div>
          ) : cancelInfo.invoiced && !can('orders:cancel_invoiced') ? (
            <p className="text-sm text-amber-500">Esta encomenda já está faturada ({cancelling?.invoice_reference}): só o gestor a cancela - com a nota de crédito, e o valor pago devolvido ou retido.</p>
          ) : (
            <>
              {cancelInfo.invoiced && (
                <p className="text-[12.5px] text-text-muted">Faturada ({cancelling?.invoice_reference}): será emitida uma nota de crédito.</p>
              )}
              <div>
                <label className={labelClass}>Motivo *</label>
                <input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} autoFocus placeholder="Ex.: cliente desistiu" className={inputClass} />
              </div>
              {cancelInfo.invoiced && cancelInfo.paid > 0 && (
                <div className="flex flex-col gap-2.5">
                  <p className={labelClass + ' mb-0'}>O cliente pagou {formatKz(cancelInfo.paid)} Kz - esse valor é *</p>
                  <div className="grid grid-cols-2 gap-2">
                    {[['DEVOLVER', 'Devolvido ao cliente'], ['RETER', 'Retido pela empresa']].map(([value, label]) => (
                      <button key={value} type="button" onClick={() => setDeposit(value)}
                        className={'h-10 rounded-md border text-sm font-medium transition-colors cursor-pointer ' + (deposit === value ? 'border-accent bg-accent/10 text-accent' : 'border-border text-text-primary hover:border-accent')}>
                        {label}
                      </button>
                    ))}
                  </div>
                  {deposit === 'RETER' && <p className="text-[12px] text-text-muted">Só a parte não paga é creditada: a fatura fica com o valor pago.</p>}
                  {deposit === 'DEVOLVER' && (
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className={labelClass}>Como é devolvido *</label>
                        <Select value={refund.methodId} onChange={(v) => setRefund({ methodId: v, posId: '', bankId: '' })} placeholder="Escolher"
                          options={refundMethods.map((m) => ({ value: m.id, label: m.name }))} />
                      </div>
                      {refundMethod?.is_cash && (
                        <div>
                          <label className={labelClass}>Caixa de onde sai *</label>
                          <Select value={refund.posId} onChange={(v) => setRefund((r) => ({ ...r, posId: v }))} placeholder={cancelInfo.cash_points.length ? 'Escolher' : 'Nenhuma caixa aberta'}
                            options={cancelInfo.cash_points.map((c) => ({ value: c.pos_id, label: c.name + ' · ' + formatKz(c.available_cash) }))} />
                        </div>
                      )}
                      {refundMethod?.uses_bank_account && (
                        <div>
                          <label className={labelClass}>Conta de onde sai *</label>
                          <Select value={refund.bankId} onChange={(v) => setRefund((r) => ({ ...r, bankId: v }))} placeholder="Escolher"
                            options={bankAccounts.map((a) => ({ value: a.id, label: (banks.find((b) => b.id === a.bank_id)?.acronym || '?') + ' - ' + a.account_number }))} />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
              <button type="submit" disabled={busyId === cancelling?.id} className="bg-danger hover:opacity-90 disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 cursor-pointer">
                Cancelar a encomenda
              </button>
            </>
          )}
        </form>
      </Modal>
    </main>
  );
}

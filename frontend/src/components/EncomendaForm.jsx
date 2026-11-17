import { useState, useEffect, useMemo } from 'react';
import { Plus, Loader2, Trash2, Store, Truck } from 'lucide-react';
import Modal from './Modal';
import Select from './Select';
import DateInput from './DateInput';
import { getOrderOptions, createOrder, updateOrder } from '../api/orders';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';
import { useAuthStore } from '../store/authStore';

// The order form (Nova / Alterar encomenda), shared by the Encomendas page and the till's Encomendas panel.
// editing: the order changed (null: a new one). An invoiced order only changes its delivery, contact and notes.
// defaultActivityId: the till's activity, proposed when the company has several with the Encomendas.

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';

function isoDay(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function localParts(value) {
  const d = new Date(value);
  const p = (n) => String(n).padStart(2, '0');
  return { date: d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()), time: p(d.getHours()) + ':' + p(d.getMinutes()) };
}

const emptyLine = () => ({ key: Math.random().toString(36).slice(2), article: '', quantity: '1', price: '', note: '' });
const emptyForm = () => ({ customerId: '', activityId: '', date: isoDay(1), time: '10:00', mode: 'LOJA', address: '', contactName: '', contactPhone: '', notes: '', lines: [emptyLine()] });

export default function EncomendaForm({ open, onClose, editing = null, onSaved, defaultActivityId = null }) {
  const [options, setOptions] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const isGestor = useAuthStore((st) => st.user?.role) === 'GESTOR';
  // an invoiced order: its lines are those of its Fatura - only the delivery, the contact and the notes change
  const locked = !!editing?.lines_locked;

  useEffect(() => {
    if (!open) return;
    if (editing) {
      const { date, time } = localParts(editing.delivery_at);
      setForm({
        customerId: editing.customer_id, activityId: editing.activity_id, date, time, mode: editing.delivery_mode,
        address: editing.delivery_address || '', contactName: editing.contact_name || '', contactPhone: editing.contact_phone || '',
        notes: editing.notes || '',
        lines: editing.lines.map((l) => ({ key: l.id, article: (l.product_id ? 'product:' + l.product_id : 'service:' + l.service_id),
          quantity: String(l.quantity), price: String(l.unit_price), note: l.production_note || '' })),
      });
    } else {
      setForm(emptyForm());
    }
    getOrderOptions().then((data) => {
      setOptions(data);
      if (!data.activities.length) {
        toast.error('Nenhuma atividade da empresa tem as Encomendas');
        onClose();
        return;
      }
      if (!editing) {
        const proposed = data.activities.find((a) => a.id === defaultActivityId)?.id
          || (data.activities.length === 1 ? data.activities[0].id : '');
        setForm((p) => ({ ...p, activityId: proposed }));
      }
    }).catch((err) => {
      toast.error(extractErrorMessage(err, 'Erro ao abrir o formulário'));
      onClose();
    });
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

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
      if (onSaved) await onSaved(saved);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar a encomenda'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={editing ? 'Alterar encomenda ' + editing.reference : 'Nova encomenda'} maxWidthClass="max-w-5xl" stacked>
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
              <DateInput value={form.date} onChange={(e) => setForm((p) => ({ ...p, date: e.target.value }))} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Hora *</label>
              <input type="time" value={form.time} onChange={(e) => setForm((p) => ({ ...p, time: e.target.value }))} className={inputClass} />
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
              <input value={form.address} onChange={(e) => setForm((p) => ({ ...p, address: e.target.value }))} className={inputClass} />
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
  );
}

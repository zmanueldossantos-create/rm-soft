import { useState, useEffect } from 'react';
import { Loader2, Store, Truck, Banknote, PackageCheck, CakeSlice } from 'lucide-react';
import Modal from './Modal';
import TerminalPicker, { terminalMissing } from './TerminalPicker';
import { listOrders, payOrder, deliverOrder } from '../api/orders';
import { listPaymentMethodPreferences } from '../api/tesouraria';
import { listPosTerminals } from '../api/pos';
import { useCan } from '../utils/permissions';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// The Encomendas of this till's activity, at the till: receive a deposit (the order's Fatura and a Recibo) and hand
// the order over (a Recibo for the rest, a Fatura/Recibo for an order never invoiced, or «fica a dever»). Each
// document issued is shown and printed like any sale of the till (onDocument).

const STATUS_STYLE = {
  ENCOMENDADA: 'bg-sky-500/15 text-sky-400', EM_PRODUCAO: 'bg-amber-500/15 text-amber-500', PRONTA: 'bg-success/15 text-success',
};

function when(value) {
  const d = new Date(value);
  const p = (n) => String(n).padStart(2, '0');
  return p(d.getDate()) + '/' + p(d.getMonth() + 1) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}

export default function EncomendasPanel({ posId, activityId, onDocument }) {
  const can = useCan();
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [methods, setMethods] = useState([]);
  const [terminals, setTerminals] = useState([]);
  const [action, setAction] = useState(null); // { kind: 'pay' | 'deliver', order }
  const [methodId, setMethodId] = useState('');
  const [amount, setAmount] = useState('');
  const [onCredit, setOnCredit] = useState(false);
  const [terminalId, setTerminalId] = useState('');
  const [saving, setSaving] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setOrders(await listOrders({ status_filter: 'ABERTAS', activity_id: activityId || undefined }));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar as encomendas'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    listPaymentMethodPreferences().then((m) => setMethods(m.filter((x) => x.available_at_pos && x.allows_receipt))).catch(() => setMethods([]));
    if (posId) listPosTerminals(posId).then(setTerminals).catch(() => setTerminals([]));
  }, [posId, activityId]); // eslint-disable-line react-hooks/exhaustive-deps

  // what is still to pay: the Fatura's balance, or the whole order when it was never invoiced
  const dueOf = (o) => (o.due != null ? o.due : o.total);

  function open(kind, order) {
    setAction({ kind, order });
    setMethodId(methods.length === 1 ? methods[0].id : '');
    setAmount(kind === 'pay' ? '' : String(dueOf(order)));
    setOnCredit(false);
    setTerminalId('');
  }

  const payments = methodId ? [{ paymentMethodId: methodId, amount: Number(amount) || 0 }] : [];

  async function submit(e) {
    e.preventDefault();
    const o = action.order;
    const toPay = action.kind === 'deliver' ? dueOf(o) : Number(amount);
    const needsMoney = !(action.kind === 'deliver' && (onCredit || dueOf(o) <= 0.005));
    if (needsMoney && !methodId) {
      toast.error('Escolha a forma de pagamento');
      return;
    }
    if (action.kind === 'pay' && !(toPay > 0)) {
      toast.error('Indique o valor recebido');
      return;
    }
    if (needsMoney && terminalMissing(terminals, methods, payments, terminalId)) return;
    setSaving(true);
    try {
      const result = action.kind === 'pay'
        ? await payOrder(o.id, { pos_id: posId, amount: toPay, payment_method_id: methodId, terminal_id: terminalId || null })
        : await deliverOrder(o.id, { pos_id: posId, payment_method_id: needsMoney ? methodId : null, amount: needsMoney ? toPay : null,
          terminal_id: terminalId || null, on_credit: onCredit });
      toast.success(action.kind === 'pay' ? 'Sinal recebido: ' + result.reference : 'Encomenda entregue: ' + result.reference);
      setAction(null);
      await load();
      if (result.document_id && onDocument) await onDocument(result.document_id);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao registar'));
    } finally {
      setSaving(false);
    }
  }

  const btn = 'inline-flex items-center gap-1.5 h-9 px-3 rounded-md border text-[13px] font-medium transition-colors cursor-pointer disabled:opacity-40 ';

  return (
    <div className="flex flex-col gap-3">
      {loading ? (
        <div className="flex items-center justify-center py-12 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>
      ) : orders.length === 0 ? (
        <div className="bg-bg-inset border border-border rounded-lg p-8 text-center text-text-muted text-sm">
          <CakeSlice size={26} className="mx-auto mb-2" />Nenhuma encomenda por entregar
        </div>
      ) : orders.map((o) => {
        const late = new Date(o.delivery_at).getTime() < Date.now();
        return (
          <div key={o.id} className="bg-bg-elevated border border-border rounded-lg p-3.5 flex flex-wrap items-center gap-x-5 gap-y-2">
            <div className="min-w-[150px]">
              <div className={'font-mono text-[14px] ' + (late ? 'text-danger font-semibold' : 'text-text-primary')}>{when(o.delivery_at)}</div>
              <div className="text-[11.5px] text-text-muted flex items-center gap-1">
                {o.delivery_mode === 'ENTREGA' ? <><Truck size={12} /> Entrega</> : <><Store size={12} /> Levanta na loja</>}
              </div>
            </div>
            <div className="flex-1 min-w-[200px]">
              <div className="text-text-primary font-medium">{o.customer_name} <span className="font-mono text-[12px] text-text-muted">· {o.reference}</span></div>
              <div className="text-[12.5px] text-text-muted truncate">{o.lines.map((l) => l.quantity + ' × ' + l.description).join(', ')}</div>
            </div>
            <span className={'px-2 py-0.5 rounded text-[11.5px] font-medium ' + (STATUS_STYLE[o.status] || '')}>{o.status_label}</span>
            <div className="text-right min-w-[150px]">
              <div className="font-mono font-semibold text-[17px] text-text-primary">{formatKz(o.total)} Kz</div>
              <div className="text-[12px] font-mono text-text-muted">
                {o.invoice_id ? <>Pago {formatKz(o.paid)} · <span className={o.due > 0.005 ? 'text-amber-500' : 'text-success'}>Falta {formatKz(o.due)}</span></> : 'Sem sinal'}
              </div>
            </div>
            {can('orders:charge') && (
              <div className="flex gap-2">
                <button type="button" disabled={!!o.invoice_id && o.due <= 0.005} onClick={() => open('pay', o)} className={btn + 'border-border text-text-primary hover:border-accent hover:text-accent'}>
                  <Banknote size={14} /> Receber sinal
                </button>
                <button type="button" onClick={() => open('deliver', o)} className={btn + 'border-success/50 text-success hover:bg-success/10'}>
                  <PackageCheck size={14} /> Entregar
                </button>
              </div>
            )}
          </div>
        );
      })}

      <Modal open={!!action} onClose={() => setAction(null)} title={action ? (action.kind === 'pay' ? 'Receber sinal - ' : 'Entregar - ') + action.order.reference : ''} maxWidthClass="max-w-xl">
        {action && (
          <form noValidate onSubmit={submit} className="flex flex-col gap-3.5">
            <div className="grid grid-cols-3 gap-2 text-center">
              {[['Total', action.order.total], ['Pago', action.order.paid], ['Falta', dueOf(action.order)]].map(([label, value]) => (
                <div key={label} className="bg-bg-inset border border-border rounded-md py-2.5">
                  <div className="text-[11px] uppercase tracking-wide text-text-muted">{label}</div>
                  <div className={'font-mono font-semibold text-xl ' + (label === 'Falta' ? 'text-accent' : 'text-text-primary')}>{formatKz(value)}</div>
                </div>
              ))}
            </div>
            {action.kind === 'deliver' && dueOf(action.order) > 0.005 && (
              <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer select-none">
                <input type="checkbox" checked={onCredit} onChange={(e) => setOnCredit(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                Fica a dever (a fatura fica por receber)
              </label>
            )}
            {!(action.kind === 'deliver' && (onCredit || dueOf(action.order) <= 0.005)) && (
              <>
                {action.kind === 'pay' && (
                  <div>
                    <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Valor do sinal *</label>
                    <input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus
                      className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-lg font-mono text-right text-text-primary outline-none focus:border-accent" />
                  </div>
                )}
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5">Forma de pagamento *</p>
                  <div className="grid grid-cols-2 gap-2">
                    {methods.map((m) => (
                      <button key={m.id} type="button" onClick={() => setMethodId(m.id)}
                        className={'h-10 rounded-md border text-sm font-medium transition-colors cursor-pointer ' + (methodId === m.id ? 'border-accent bg-accent/10 text-accent' : 'border-border text-text-primary hover:border-accent')}>
                        {m.short_label || m.name}
                      </button>
                    ))}
                  </div>
                </div>
                <TerminalPicker terminals={terminals} methods={methods} payments={action.kind === 'pay' ? payments : (methodId ? [{ paymentMethodId: methodId, amount: dueOf(action.order) }] : [])} value={terminalId} onChange={setTerminalId} />
              </>
            )}
            <button type="submit" disabled={saving} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
              {saving && <Loader2 size={16} className="animate-spin" />}
              {action.kind === 'pay' ? 'Receber o sinal' : onCredit || dueOf(action.order) <= 0.005 ? 'Entregar' : 'Receber ' + formatKz(dueOf(action.order)) + ' Kz e entregar'}
            </button>
          </form>
        )}
      </Modal>
    </div>
  );
}

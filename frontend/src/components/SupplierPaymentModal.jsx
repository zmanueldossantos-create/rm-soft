import { useEffect, useState } from 'react';
import { Loader2, Wallet } from 'lucide-react';
import Modal from './Modal';
import Select from './Select';
import DateInput from './DateInput';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { paymentMethodsApi, banksApi } from '../api/catalogs';
import { getMyCompanyBankAccounts } from '../api/company';
import { getOpenCashPoints } from '../api/invoices';
import { createSupplierPayment } from '../api/supplierPayments';

// Pagar fornecedor (supplier_payment_service): one payment for invoices (FT) of one supplier - each with what it settles
// (what is owed, by default; never more). The method must allow payments: cash leaves a till (it must be open, today),
// a transfer or a cheque leaves one of the company's bank accounts.
const inputCls = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5 whitespace-nowrap';
const kz = (v) => formatKz(v) + ' Kz';
const round2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;
const todayIso = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Africa/Luanda' });

export default function SupplierPaymentModal({ invoices, onClose, onPaid }) {
  const open = !!invoices && invoices.length > 0;
  const [methods, setMethods] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [banks, setBanks] = useState([]);
  const [tills, setTills] = useState([]);
  const [amounts, setAmounts] = useState({});
  const [form, setForm] = useState({ methodId: '', bankAccountId: '', posId: '', date: todayIso(), reference: '', notes: '' });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setAmounts(Object.fromEntries(invoices.map((i) => [i.id, String(i.amount_due)])));
    setForm({ methodId: '', bankAccountId: '', posId: '', date: todayIso(), reference: '', notes: '' });
    setError('');
    paymentMethodsApi.list().then((d) => setMethods(d.filter((m) => m.is_active && m.allows_payment))).catch(() => setMethods([]));
    getMyCompanyBankAccounts().then((d) => setAccounts(d.filter((a) => a.is_active))).catch(() => setAccounts([]));
    banksApi.list().then(setBanks).catch(() => setBanks([]));
    getOpenCashPoints().then(setTills).catch(() => setTills([]));
  }, [invoices]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) return null;
  const method = methods.find((m) => m.id === form.methodId);
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));
  const total = round2(invoices.reduce((s, i) => s + (parseFloat(amounts[i.id]) || 0), 0));
  const over = invoices.find((i) => (parseFloat(amounts[i.id]) || 0) > i.amount_due + 0.005);
  const valid = total > 0 && !over && method && (!method.uses_bank_account || form.bankAccountId) && (!method.is_cash || form.posId) && form.date;
  const bankLabel = (a) => (banks.find((b) => b.id === a.bank_id)?.acronym || '?') + ' - ' + a.account_number;

  async function submit() {
    setSaving(true);
    setError('');
    try {
      const payment = await createSupplierPayment({
        supplier_id: invoices[0].supplier_id, payment_method_id: form.methodId, payment_date: form.date,
        bank_account_id: method.uses_bank_account ? form.bankAccountId : null, pos_id: method.is_cash ? form.posId : null,
        reference: form.reference || null, notes: form.notes || null,
        allocations: invoices.map((i) => ({ purchase_invoice_id: i.id, amount: parseFloat(amounts[i.id]) || 0 })).filter((a) => a.amount > 0),
      });
      onPaid(payment);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao registar o pagamento'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={'Pagar fornecedor - ' + invoices[0].supplier_name} maxWidthClass="max-w-4xl">
      <div className="flex flex-col gap-4">
        <div className="border border-border rounded-md overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border">
              <th className={th + ' text-left'}>Registo</th><th className={th + ' text-left'}>Documento</th><th className={th + ' text-left'}>Vencimento</th>
              <th className={th + ' text-right'}>Total</th><th className={th + ' text-right'}>Em dívida</th><th className={th + ' text-right w-44'}>A pagar</th>
            </tr></thead>
            <tbody>
              {invoices.map((i) => {
                const tooMuch = (parseFloat(amounts[i.id]) || 0) > i.amount_due + 0.005;
                return (
                  <tr key={i.id} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 font-mono text-text-muted">{i.reference}</td>
                    <td className="px-3 py-2 font-mono text-text-primary">{i.supplier_document}</td>
                    <td className={'px-3 py-2 font-mono text-[12px] ' + (i.overdue ? 'text-danger' : 'text-text-muted')}>{i.due_date ? new Date(i.due_date + 'T00:00:00').toLocaleDateString('pt-PT') : '-'}</td>
                    <td className="px-3 py-2 text-right font-mono text-text-muted whitespace-nowrap">{kz(i.total)}</td>
                    <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{kz(i.amount_due)}</td>
                    <td className="px-3 py-1.5">
                      <input type="number" step="0.01" min="0" max={i.amount_due} value={amounts[i.id] ?? ''} onChange={(e) => setAmounts((a) => ({ ...a, [i.id]: e.target.value }))}
                        className={inputCls + ' text-right font-mono' + (tooMuch ? ' border-danger' : '')} />
                    </td>
                  </tr>
                );
              })}
              <tr className="bg-bg-inset">
                <td colSpan={5} className="px-3 py-2 font-semibold text-text-primary">Total do pagamento</td>
                <td className="px-3 py-2 text-right font-mono font-semibold text-text-primary">{kz(total)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className={labelCls}>Método de pagamento *</label>
            <Select value={form.methodId} onChange={(v) => set({ methodId: v, bankAccountId: '', posId: '', date: methods.find((m) => m.id === v)?.is_cash ? todayIso() : form.date })}
              placeholder="Selecionar" options={methods.map((m) => ({ value: m.id, label: m.name }))} />
          </div>
          {method?.is_cash ? (
            <div>
              <label className={labelCls}>Caixa de saída *</label>
              {tills.length === 0
                ? <p className="text-[12px] text-danger py-2">Nenhuma caixa com sessão aberta - abra uma caixa para pagar em numerário</p>
                : <Select value={form.posId} onChange={(v) => set({ posId: v })} placeholder="Selecionar" options={tills.map((t) => ({ value: t.pos_id, label: t.name }))} />}
            </div>
          ) : (
            <div>
              <label className={labelCls}>Conta bancária{method?.uses_bank_account ? ' *' : ''}</label>
              <Select value={form.bankAccountId} onChange={(v) => set({ bankAccountId: v })} disabled={!method?.uses_bank_account}
                placeholder={method?.uses_bank_account ? 'Selecionar' : 'Não aplicável'} options={accounts.map((a) => ({ value: a.id, label: bankLabel(a) }))} />
            </div>
          )}
          <div>
            <label className={labelCls}>Data *</label>
            <DateInput value={form.date} max={todayIso()} readOnly={!!method?.is_cash} onChange={(e) => set({ date: e.target.value })}
              className={inputCls + (method?.is_cash ? ' opacity-60 cursor-not-allowed' : '')} />
          </div>
          <div>
            <label className={labelCls}>Referência</label>
            <input value={form.reference} onChange={(e) => set({ reference: e.target.value })} placeholder="Nº do cheque ou da transferência" className={inputCls} />
          </div>
          <div className="md:col-span-2">
            <label className={labelCls}>Observações</label>
            <input value={form.notes} onChange={(e) => set({ notes: e.target.value })} placeholder="Opcional" className={inputCls} />
          </div>
        </div>
        <p className="text-[12px] text-text-muted">
          {method?.is_cash ? 'O numerário sai hoje da caixa escolhida (uma saída automática «Pagamento a fornecedor»).' : 'O pagamento fica registado; as faturas pagas deixam de estar em dívida.'}
          {over ? ' O valor a pagar de ' + over.supplier_document + ' excede o que está em dívida.' : ''}
        </p>
        {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>}
        <button onClick={submit} disabled={saving || !valid} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
          {saving ? <Loader2 size={17} className="animate-spin" /> : <Wallet size={17} />} Registar pagamento de {kz(total)}
        </button>
      </div>
    </Modal>
  );
}

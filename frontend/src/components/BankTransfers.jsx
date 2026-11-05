import { useEffect, useState } from 'react';
import { ArrowRight, Clock } from 'lucide-react';
import Modal from './Modal';
import Select from './Select';
import DateInput from './DateInput';
import BankBalanceWarning, { bankShortfall } from './BankBalanceWarning';
import { createBankTransfer, listTransfersInTransit, confirmFundsAvailable } from '../api/tesouraria';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Tesouraria › Bancos: transfers between two bank accounts of the company. Within one bank the money is on the other
// account at once; between two banks it leaves the first account and stays «em trânsito» until someone confirms
// «Fundos disponíveis» with the day the second bank shows it.

const inputCls = 'bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';

function todayIso() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function day(value) {
  return value ? new Date(value + 'T00:00:00').toLocaleDateString('pt-PT') : '-';
}

const accountLabel = (b) => b.bank + ' · ' + b.account_number;

// The new transfer from `source` (a BankPosition) to another active account of the same currency.
export function TransferModal({ source, banks, onClose, onDone }) {
  const [form, setForm] = useState(null); // { toId, amount, date, reference, description, negativeOk }
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setForm(source ? { toId: '', amount: '', date: todayIso(), reference: '', description: '', negativeOk: false } : null);
  }, [source]);

  const targets = source ? banks.filter((b) => b.id !== source.id && b.is_active && b.currency === source.currency) : [];
  const target = form ? targets.find((b) => b.id === form.toId) : null;
  const sameBank = !!target && target.bank === source.bank;
  const shortfall = form ? bankShortfall(banks, source?.id, Number(form.amount || 0)) : null;
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  async function save() {
    setSaving(true);
    try {
      const t = await createBankTransfer(source.id, {
        to_account_id: form.toId, amount: Number(form.amount), transfer_date: form.date,
        reference: form.reference || null, description: form.description || null,
      });
      toast.success(t.status === 'EM_TRANSITO'
        ? 'Transferência ' + t.document + ' registada - em trânsito até confirmar «Fundos disponíveis»'
        : 'Transferência ' + t.document + ' registada - já disponível em ' + t.to_label);
      onDone();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao registar a transferência'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={!!source} onClose={onClose} title={'Transferência de ' + (source ? accountLabel(source) : '')} maxWidthClass="max-w-lg">
      {form && source && (
        <form onSubmit={(e) => { e.preventDefault(); save(); }} className="flex flex-col gap-4">
          <p className="text-text-muted text-[13px]">Dinheiro entre duas contas da empresa. No mesmo banco chega no próprio dia; entre dois bancos fica em trânsito até confirmar «Fundos disponíveis».</p>
          <div>
            <label className={labelCls}>Para a conta *</label>
            {targets.length === 0
              ? <p className="text-[12px] text-danger py-2">Nenhuma outra conta ativa na mesma moeda.</p>
              : <Select value={form.toId} onChange={(v) => set({ toId: v })} placeholder="Selecionar"
                  options={targets.map((b) => ({ value: b.id, label: accountLabel(b) + ' · ' + b.bank_name }))} />}
            {target && (
              <p className={'text-[12px] mt-1.5 ' + (sameBank ? 'text-success' : 'text-accent')}>
                {sameBank ? 'Mesmo banco: o dinheiro fica disponível na conta de destino no próprio dia.'
                  : 'Outro banco: o dinheiro sai hoje desta conta e fica em trânsito; confirme «Fundos disponíveis» quando o ' + target.bank + ' o mostrar.'}
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Valor ({source.currency === 'AOA' ? 'Kz' : source.currency}) *</label>
              <input type="number" step="0.01" min="0.01" required value={form.amount} onChange={(e) => set({ amount: e.target.value, negativeOk: false })} className={inputCls + ' w-full font-mono'} />
            </div>
            <div>
              <label className={labelCls}>Data *</label>
              <DateInput value={form.date} max={todayIso()} required onChange={(e) => set({ date: e.target.value })} className={inputCls + ' w-full'} />
            </div>
          </div>
          <div>
            <label className={labelCls}>Referência</label>
            <input value={form.reference} maxLength={60} onChange={(e) => set({ reference: e.target.value })} placeholder="Nº da operação no banco" className={inputCls + ' w-full'} />
          </div>
          <div>
            <label className={labelCls}>Descrição</label>
            <input value={form.description} maxLength={300} onChange={(e) => set({ description: e.target.value })} placeholder="Opcional" className={inputCls + ' w-full'} />
          </div>
          <BankBalanceWarning shortfall={shortfall} confirmed={form.negativeOk} onConfirm={(v) => set({ negativeOk: v })} />
          <button type="submit" disabled={saving || !form.toId || !(Number(form.amount) > 0) || (shortfall && !form.negativeOk)}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer">
            {saving ? 'A registar...' : 'Registar transferência'}
          </button>
        </form>
      )}
    </Modal>
  );
}

// The transfers between two banks still on their way, each with «Fundos disponíveis» (canManage). Nothing when none.
export function InTransitPanel({ reload, canManage, onChange }) {
  const [transfers, setTransfers] = useState([]);
  const [confirming, setConfirming] = useState(null); // { transfer, date }
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listTransfersInTransit().then(setTransfers).catch(() => setTransfers([]));
  }, [reload]);

  async function save() {
    setSaving(true);
    try {
      await confirmFundsAvailable(confirming.transfer.id, confirming.date);
      toast.success('Fundos de ' + confirming.transfer.document + ' disponíveis em ' + confirming.transfer.to_label);
      setConfirming(null);
      onChange();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao confirmar os fundos'));
    } finally {
      setSaving(false);
    }
  }

  if (transfers.length === 0) return null;
  const total = transfers.reduce((s, t) => s + t.amount, 0);
  return (
    <div className="bg-accent/5 border border-accent/40 rounded-lg px-5 py-4 mb-5">
      <p className="font-display font-semibold text-text-primary text-[14px] flex items-center gap-2">
        <Clock size={15} className="text-accent" /> Em trânsito: {formatKz(total)} Kz
      </p>
      <p className="text-[12px] text-text-muted mb-2">Transferências entre bancos que já saíram e ainda não chegaram. Confirme quando o banco de destino mostrar o dinheiro.</p>
      <div className="flex flex-col divide-y divide-border">
        {transfers.map((t) => (
          <div key={t.id} className="flex items-center gap-3 py-2.5">
            <div className="flex-1 min-w-0">
              <p className="text-[13px] text-text-primary flex items-center gap-1.5 flex-wrap">
                <span className="font-mono text-text-muted">{t.document}</span> {t.from_label} <ArrowRight size={13} className="text-text-muted" /> {t.to_label}
              </p>
              <p className="text-[12px] text-text-muted">Saiu em {day(t.transfer_date)}{t.reference ? ' · ' + t.reference : ''}</p>
            </div>
            <span className="font-mono text-[13px] text-text-primary whitespace-nowrap">{formatKz(t.amount)} Kz</span>
            {canManage && (
              <button type="button" onClick={() => setConfirming({ transfer: t, date: todayIso() })}
                className="border border-border hover:border-success text-text-primary hover:text-success text-[12px] font-semibold px-3 py-1.5 rounded-md transition-colors cursor-pointer whitespace-nowrap">
                Fundos disponíveis
              </button>
            )}
          </div>
        ))}
      </div>

      <Modal open={!!confirming} onClose={() => setConfirming(null)} title={'Fundos disponíveis - ' + (confirming?.transfer.document || '')} maxWidthClass="max-w-md">
        {confirming && (
          <form onSubmit={(e) => { e.preventDefault(); save(); }} className="flex flex-col gap-4">
            <p className="text-text-muted text-[13px]">
              {formatKz(confirming.transfer.amount)} Kz de {confirming.transfer.from_label} entram em {confirming.transfer.to_label} no dia em que o banco os mostra.
            </p>
            <div>
              <label className={labelCls}>Disponível desde *</label>
              <DateInput value={confirming.date} min={confirming.transfer.transfer_date} max={todayIso()} required
                onChange={(e) => setConfirming((c) => ({ ...c, date: e.target.value }))} className={inputCls + ' w-full'} />
            </div>
            <button type="submit" disabled={saving} className="bg-success hover:opacity-90 disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer">
              {saving ? 'A confirmar...' : 'Confirmar fundos disponíveis'}
            </button>
          </form>
        )}
      </Modal>
    </div>
  );
}

import { useEffect } from 'react';
import Select from './Select';
import { toast } from '../store/toastStore';

// The till's choice of the TPA / Multicaixa Express a card payment went through - its bank account receives the money
// (Tesouraria › Bancos). Shown only when several terminals of this point of sale receive the bank methods ticked:
// with one, the server takes it by itself; with none, the sale goes on without a bank.

// The terminals that receive every bank method of the payments (payments: [{ paymentMethodId, amount }]).
export function fittingTerminals(terminals, methods, payments) {
  const bankIds = (payments || [])
    .filter((p) => Number(p.amount) > 0 && (methods || []).find((m) => m.id === p.paymentMethodId)?.uses_bank_account)
    .map((p) => p.paymentMethodId);
  if (bankIds.length === 0) return [];
  return (terminals || []).filter((t) => bankIds.every((id) => t.payment_method_ids.includes(id)));
}

// true (and a toast) when the cashier must still choose the terminal - to check before sending the sale
export function terminalMissing(terminals, methods, payments, value) {
  if (fittingTerminals(terminals, methods, payments).length > 1 && !value) {
    toast.error('Escolha o terminal (TPA / Express) por onde passou o pagamento.');
    return true;
  }
  return false;
}

export default function TerminalPicker({ terminals, methods, payments, value, onChange }) {
  const fits = fittingTerminals(terminals, methods, payments);
  const stale = !!value && !fits.some((t) => t.id === value);
  useEffect(() => {
    if (stale) onChange(''); // the methods changed: the terminal chosen no longer receives them
  }, [stale]); // eslint-disable-line react-hooks/exhaustive-deps
  if (fits.length < 2) return null;
  return (
    <div className="flex flex-col gap-1.5 mt-1">
      <label className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Terminal (TPA / Express) *</label>
      <Select value={value} onChange={onChange} placeholder="Por onde passou o pagamento?"
        options={fits.map((t) => ({ value: t.id, label: t.name + ' · ' + t.bank_account_label }))} />
    </div>
  );
}

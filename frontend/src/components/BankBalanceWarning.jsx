import { AlertTriangle } from 'lucide-react';
import { formatKz } from '../utils/format';

// A bank account about to go below zero: warned, never blocked (an overdraft exists, and a balance without its
// opening balance may be incomplete) - the person ticks that they confirm. Used by every exit from a bank account.

// What the account will hold after an exit of `amount`, when that is below zero: { label, after, noOpening } - else null.
export function bankShortfall(positions, accountId, amount) {
  const account = (positions || []).find((b) => b.id === accountId);
  if (!account || !(amount > 0)) return null;
  const after = Math.round((account.balance - amount) * 100) / 100;
  if (after >= 0) return null;
  return { label: account.bank + ' · ' + account.account_number, after, noOpening: !account.opening_date };
}

export default function BankBalanceWarning({ shortfall, confirmed, onConfirm }) {
  if (!shortfall) return null;
  return (
    <div className="border border-amber-500/40 bg-amber-500/10 rounded-md px-3.5 py-3 flex flex-col gap-2">
      <p className="text-[13px] text-amber-500 flex items-start gap-2">
        <AlertTriangle size={15} className="shrink-0 mt-0.5" />
        <span>
          A conta {shortfall.label} fica com saldo negativo ({formatKz(shortfall.after)} Kz).
          {shortfall.noOpening && ' O saldo inicial desta conta está por definir - o saldo pode não estar correto (Tesouraria › Bancos).'}
        </span>
      </p>
      <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer select-none">
        <input type="checkbox" checked={confirmed} onChange={(e) => onConfirm(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
        Confirmo a saída com saldo negativo
      </label>
    </div>
  );
}

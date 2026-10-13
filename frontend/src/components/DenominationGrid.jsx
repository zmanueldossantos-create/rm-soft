// The notes and coins of a count - the Moedeiro drawer count, a transfer sent, a transfer received: the same grid
// everywhere. Two columns of cells, notes first, each cell "value × quantity = amount"; the denominations given
// stand out. quantities: { [denomination_id]: '2' }.
import { formatKz } from '../utils/format';

const quantityOf = (quantities, id) => parseInt(quantities[id] || '0', 10) || 0;

export function denominationTotal(denominations, quantities) {
  return denominations.reduce((sum, d) => sum + quantityOf(quantities, d.id) * Number(d.value), 0);
}

// The lines the API expects: only the denominations given, as integers.
export function denominationLines(denominations, quantities) {
  return denominations
    .map((d) => ({ denomination_id: d.id, quantity: quantityOf(quantities, d.id) }))
    .filter((l) => l.quantity > 0);
}

function Group({ items, label, quantities, onChange }) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">{label}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
        {items.map((d) => {
          const quantity = quantityOf(quantities, d.id);
          const given = quantity > 0;
          return (
            <label
              key={d.id}
              className={'grid grid-cols-[5.5rem_auto_1fr] items-center gap-2 rounded-md border px-2.5 py-1.5 transition-colors cursor-text '
                + (given ? 'border-accent bg-accent/5' : 'border-border bg-bg-inset')}
            >
              <span className={'font-mono text-[12px] ' + (given ? 'text-text-primary font-semibold' : 'text-text-muted')}>
                {formatKz(d.value)}
              </span>
              <span className="flex items-center gap-1">
                <span className="text-[11px] text-text-muted">×</span>
                <input
                  type="number" min="0" step="1" inputMode="numeric"
                  value={quantities[d.id] || ''}
                  onChange={(e) => onChange(d.id, e.target.value)}
                  onFocus={(e) => e.target.select()}
                  placeholder="0"
                  className="w-14 bg-bg-elevated border border-border rounded px-1.5 py-0.5 text-right text-sm text-text-primary font-mono outline-none focus:border-accent"
                />
              </span>
              <span className={'text-right font-mono text-[12px] ' + (given ? 'text-text-primary' : 'text-text-muted/60')}>
                = {formatKz(quantity * Number(d.value))}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

export default function DenominationGrid({ denominations, quantities, onChange }) {
  return (
    <div className="flex flex-col gap-3">
      <Group items={denominations.filter((d) => d.denomination_type === 'NOTA')} label="Notas" quantities={quantities} onChange={onChange} />
      <Group items={denominations.filter((d) => d.denomination_type === 'MOEDA')} label="Moedas" quantities={quantities} onChange={onChange} />
    </div>
  );
}

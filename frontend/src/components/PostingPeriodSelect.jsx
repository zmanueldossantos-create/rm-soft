import { useEffect, useState } from 'react';
import Select from './Select';
import { getPostingPeriods } from '../api/fiscal';

// The period an INTERNAL entry is booked in (reception, transfer, loss, adjustment, production, internal consumption).
// Always shown. With a single open period it is greyed and empty: the server books the entry in the active period.
// With a soft-closed period next to the active one it is enabled, empty and REQUIRED: the user chooses explicitly
// (the soft-closed month for a late entry). onChoice(true|false) tells the form whether a choice is required.
export default function PostingPeriodSelect({ value, onChange, onChoice, onPeriods, className = '' }) {
  const [periods, setPeriods] = useState([]);

  useEffect(() => {
    getPostingPeriods()
      .then((data) => {
        setPeriods(data);
        onChoice?.(data.length > 1);
        onPeriods?.(data); // the form bounds its date with them
      })
      .catch(() => {
        setPeriods([]);
        onChoice?.(false);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const hasChoice = periods.length > 1;
  const active = periods.find((p) => p.status === 'ABERTO');
  const labelOf = (p) => p.label;
  const hint = hasChoice
    ? 'Escolha o periodo do lancamento: o mes em fecho parcial para um lancamento tardio'
    : 'So existe um periodo aberto: o lancamento vai para ' + (active ? active.label : 'o periodo ativo');

  return (
    <div className={className + (hasChoice ? '' : ' opacity-60 pointer-events-none')} title={hint}>
      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Periodo{hasChoice ? ' *' : ''}</label>
      <Select
        value={hasChoice ? value : ''}
        onChange={onChange}
        options={periods.map((p) => ({ value: p.id, label: labelOf(p) }))}
        placeholder={hasChoice ? 'Selecionar' : (active ? labelOf(active) : 'Sem periodo aberto')}
      />
    </div>
  );
}

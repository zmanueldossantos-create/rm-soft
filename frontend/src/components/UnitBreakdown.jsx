import { useState } from 'react';
import { breakDown } from '../utils/stockUnits';

// The stock of a product read in its units (50 KG -> 2 SC; 31 UN -> 1 CX + 1 UN). A click reads it starting from the
// next smaller unit (31 UN: CX -> MCX -> DZ -> back to CX). Display only: the stock stays counted in base units.
export default function UnitBreakdown({ quantity, baseCode, units }) {
  const usable = (units || []).filter((u) => Number(u.factor) > 1).sort((a, b) => b.factor - a.factor);
  const [start, setStart] = useState(0);
  if (!usable.length || !(Number(quantity) > 0)) return <span className="text-text-muted">-</span>;
  const from = usable[start % usable.length];
  const text = breakDown(quantity, baseCode, usable.filter((u) => u.factor <= from.factor));
  const several = usable.length > 1;
  return (
    <button
      type="button"
      onClick={() => setStart((s) => (s + 1) % usable.length)}
      title={several ? 'Clique para ler a partir de outra unidade' : ''}
      className={'font-mono text-[13px] text-text-primary ' + (several ? 'cursor-pointer hover:text-accent underline decoration-dotted underline-offset-4' : 'cursor-default')}
    >
      {text}
    </button>
  );
}

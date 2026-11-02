// A base quantity broken down into the product's units, largest first: 50 (KG) with SC=25 -> "2 SC";
// 31 (UN) with CX=30 -> "1 CX + 1 UN"; the rest stays in the base unit. Display only - stock is counted in base units.
export function breakDown(quantity, baseCode, units) {
  let rest = Number(quantity) || 0;
  const parts = [];
  for (const u of [...units].sort((a, b) => b.factor - a.factor)) {
    const n = Math.floor((rest + 1e-9) / u.factor);
    if (n > 0) {
      parts.push(n + ' ' + u.code);
      rest -= n * u.factor;
    }
  }
  if (rest > 1e-6) parts.push(rest.toLocaleString('pt-PT', { maximumFractionDigits: 3 }) + (baseCode ? ' ' + baseCode : ''));
  return parts.join(' + ');
}

// Below one kilo or one litre, the everyday unit beside it for readability: 0,4 KG -> "400 g", 0,5 L -> "50 cl",
// 0,005 L -> "5 ml". Display only (null when not a fraction of KG / L) - the stock is still counted in KG / L.
export function smallUnitHint(quantity, code) {
  const q = Math.abs(Number(quantity) || 0);
  if (!q || q >= 1) return null;
  const fmt = (n) => (Math.round(n * 10) / 10).toLocaleString('pt-PT', { maximumFractionDigits: 1 });
  const unit = (code || '').toUpperCase();
  if (unit === 'KG') return fmt(q * 1000) + ' g';
  if (unit === 'L') {
    const cl = q * 100;
    return Math.abs(cl - Math.round(cl)) < 1e-6 ? fmt(cl) + ' cl' : fmt(q * 1000) + ' ml';
  }
  return null;
}

// A quantity in the pt-PT way followed by its unit, and the everyday unit when below 1 KG / 1 L: "0,4 KG (400 g)"
export function qtyWithUnit(quantity, code) {
  const text = Number(quantity).toLocaleString('pt-PT', { maximumFractionDigits: 3 }) + (code ? ' ' + code : '');
  const hint = smallUnitHint(quantity, code);
  return hint ? text + ' (' + hint + ')' : text;
}

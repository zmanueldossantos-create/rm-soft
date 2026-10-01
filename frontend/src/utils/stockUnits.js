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

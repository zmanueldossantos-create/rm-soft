// Amounts as everywhere in RM Soft, screens and PDFs alike: 5 000,00 - a space between the thousands from 1 000
// on (the browser's pt-PT format leaves 5000,00 ungrouped under 10 000), a comma for the decimals. The space is a
// non-breaking one: an amount is never cut at the end of a line.
export function formatKz(value) {
  const n = Number(value || 0);
  const [int, dec] = Math.abs(n).toFixed(2).split('.');
  return (n < 0 ? '-' : '') + int.replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0') + ',' + dec;
}

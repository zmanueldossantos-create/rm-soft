// Payment terms - the one due-date computation for Faturas and the Caixa.
// A fixed-day term (fixed_days) falls on day `days` of the document month plus `months_fixed_day` months (31, or any day
// past the month's end, is that month's last day). Any other term is the document date plus `days`.
export function dueDateFor(term, documentDate) {
  if (!term || !documentDate) return documentDate || '';
  const [y, m, d] = documentDate.split('-').map(Number);
  if (term.fixed_days) {
    const month = m - 1 + (Number(term.months_fixed_day) || 0);
    const lastDay = new Date(Date.UTC(y, month + 1, 0)).getUTCDate();
    return new Date(Date.UTC(y, month, Math.min(Number(term.days) || 1, lastDay))).toISOString().slice(0, 10);
  }
  return new Date(Date.UTC(y, m - 1, d + (Number(term.days) || 0))).toISOString().slice(0, 10);
}

// "Pronto pagamento": the 0-day term that is not a fixed day - what a document paid on issue always carries.
export const isProntoTerm = (term) => !!term && !term.fixed_days && Number(term.days) === 0;

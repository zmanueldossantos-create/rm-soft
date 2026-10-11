import { isPessoaColetiva } from './customerType';

// The withholding at the source a document will carry - the invoice's own rule (invoice_service.create_invoice):
// only on a service line whose service has a withholding tax, only for a pessoa coletiva customer; per line,
// on the line's amount before VAT, rounded to the cent. The customer pays the total minus this amount.
//   lines: [{ service_id, subtotal }]
export function withholdingOf(lines, { services = [], withholdingTaxes = [], customer = null } = {}) {
  if (!isPessoaColetiva(customer)) return 0;
  const total = lines.reduce((sum, l) => {
    if (!l.service_id) return sum;
    const service = services.find((s) => s.id === l.service_id);
    const rate = Number(withholdingTaxes.find((w) => w.id === service?.withholding_tax_id)?.rate || 0);
    return sum + Math.round(Number(l.subtotal || 0) * rate) / 100;
  }, 0);
  return Math.round(total * 100) / 100;
}

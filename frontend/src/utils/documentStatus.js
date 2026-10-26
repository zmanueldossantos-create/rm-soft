// The state shown for a document. A working document (pro-forma, orçamento) is not fiscal: it never goes to the AGT, so
// it never shows an AGT submission state (PENDENTE...) - only «Não fiscal», «Faturado» (converted) or «Expirado».

export const WORKING_TYPES = ['PRO_FORMA', 'ORCAMENTO'];

const todayIsoDate = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Africa/Luanda' });

// an orçamento past its validity date and not converted: no longer converted into an invoice
export const isExpired = (inv) => !!inv.valid_until && !inv.converted_to_invoice_id && inv.valid_until < todayIsoDate();

// { label, className } for a working document; null for a fiscal one (its AGT state is shown instead)
export function workingDocumentState(inv) {
  if (!WORKING_TYPES.includes(inv.invoice_type)) return null;
  if (isExpired(inv)) return { label: 'Expirado', className: 'bg-danger/10 text-danger' };
  return { label: inv.converted_to_invoice_id ? 'Faturado' : 'Não fiscal', className: 'bg-text-muted/10 text-text-muted' };
}

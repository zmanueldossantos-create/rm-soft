import { useEffect, useMemo, useState } from 'react';
import { documentRulesApi } from '../api/catalogs';

// Document types the Caixa offers, from the document type catalog ("issuable at POS" rule): [stored type, code, label]
const TYPES = [['FACTURA_RECIBO', 'FR', 'Fatura/Recibo'], ['FACTURA', 'FT', 'Fatura'], ['PRO_FORMA', 'FP', 'Pro-forma']];
const FALLBACK = TYPES.map(([value, , label]) => ({ value, label }));
const FALLBACK_LIQUIDATION = FALLBACK.filter((o) => o.value !== 'PRO_FORMA');

// The type paid on issue offered by the catalog at the till (first by code); the Fatura/Recibo when there is none.
function defaultPaid(docTypes) {
  const d = docTypes
    .filter((x) => x.is_active && x.paid_on_issue && x.issuable_at_pos && x.saft_section === 'INVOICES' && TYPES.some(([, code]) => code === x.code))
    .sort((a, b) => a.code.localeCompare(b.code))[0];
  const found = d && TYPES.find(([, code]) => code === d.code);
  return found ? found[0] : 'FACTURA_RECIBO';
}

export default function usePosDocumentTypes() {
  const [docTypes, setDocTypes] = useState(null);
  useEffect(() => {
    // A user who cannot read the catalog keeps the default lists; the server enforces the rules anyway.
    documentRulesApi.list().then(setDocTypes).catch(() => {});
  }, []);
  return useMemo(() => {
    if (!docTypes) return { typeOptions: FALLBACK, liquidationOptions: FALLBACK_LIQUIDATION, defaultPaidType: 'FACTURA_RECIBO' };
    const offered = (test) => TYPES
      .filter(([, code]) => { const d = docTypes.find((x) => x.code === code); return d && d.is_active && test(d); })
      .map(([value, , label]) => ({ value, label }));
    const typeOptions = offered((d) => d.issuable_at_pos);
    const liquidationOptions = offered((d) => d.issuable_at_pos && d.saft_section === 'INVOICES');
    return {
      typeOptions: typeOptions.length ? typeOptions : FALLBACK,
      liquidationOptions: liquidationOptions.length ? liquidationOptions : FALLBACK_LIQUIDATION,
      defaultPaidType: defaultPaid(docTypes),
    };
  }, [docTypes]);
}
import { useEffect, useMemo, useState } from 'react';
import { documentTypesApi } from '../api/catalogs';

// Document types the Caixa offers, from the document type catalog ("issuable at POS" rule): [stored type, code, label]
const TYPES = [['FACTURA_RECIBO', 'FR', 'Fatura/Recibo'], ['FACTURA', 'FT', 'Fatura'], ['PRO_FORMA', 'FP', 'Pro-forma']];
const FALLBACK = TYPES.map(([value, , label]) => ({ value, label }));
const FALLBACK_LIQUIDATION = FALLBACK.filter((o) => o.value !== 'PRO_FORMA');

export default function usePosDocumentTypes() {
  const [docTypes, setDocTypes] = useState(null);
  useEffect(() => {
    // A user who cannot read the catalog keeps the default lists; the server enforces the rules anyway.
    documentTypesApi.list().then(setDocTypes).catch(() => {});
  }, []);
  return useMemo(() => {
    if (!docTypes) return { typeOptions: FALLBACK, liquidationOptions: FALLBACK_LIQUIDATION };
    const offered = (test) => TYPES
      .filter(([, code]) => { const d = docTypes.find((x) => x.code === code); return d && d.is_active && test(d); })
      .map(([value, , label]) => ({ value, label }));
    const typeOptions = offered((d) => d.issuable_at_pos);
    const liquidationOptions = offered((d) => d.issuable_at_pos && d.saft_section === 'INVOICES');
    return {
      typeOptions: typeOptions.length ? typeOptions : FALLBACK,
      liquidationOptions: liquidationOptions.length ? liquidationOptions : FALLBACK_LIQUIDATION,
    };
  }, [docTypes]);
}
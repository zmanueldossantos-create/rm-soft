import { useEffect, useState } from 'react';
import { documentRulesApi } from '../api/catalogs';

// Stored invoice type -> catalog code (the same mapping the server uses)
export const DOC_CODE_BY_TYPE = {
  FACTURA: 'FT', FACTURA_RECIBO: 'FR', NOTA_CREDITO: 'NC', NOTA_DEBITO: 'ND', RECIBO: 'RC', PRO_FORMA: 'FP',
};

// Default behaviour when the catalog is not readable by the user (the server enforces the rules anyway)
const DEFAULTS = {
  accepts_credit_note: ['FACTURA', 'FACTURA_RECIBO'],
  accepts_debit_note: ['FACTURA', 'FACTURA_RECIBO'],
  accepts_receipt: ['FACTURA'],
  paid_on_issue: ['FACTURA_RECIBO'],
};

// Reads the rules of the document type catalog once; ruleOf(type, rule) answers from the catalog.
export default function useDocumentRules() {
  const [docTypes, setDocTypes] = useState(null);
  useEffect(() => {
    documentRulesApi.list().then(setDocTypes).catch(() => {});
  }, []);
  return (invoiceType, rule) => {
    const row = docTypes && docTypes.find((d) => d.code === DOC_CODE_BY_TYPE[invoiceType]);
    return row ? !!row[rule] : (DEFAULTS[rule] || []).includes(invoiceType);
  };
}
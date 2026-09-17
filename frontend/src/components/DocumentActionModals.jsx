import { useState, forwardRef, useImperativeHandle } from 'react';
import { X, Loader2, AlertTriangle } from 'lucide-react';
import Modal from './Modal';
import { getInvoiceDetail, createCreditNote, createDebitNote, createReceipt } from '../api/invoices';
import { extractErrorMessage } from '../utils/errors';

// Self-contained NC/ND/RC action modals against an already-issued invoice, usable
// from any screen (Caixa's "Consultar documentos", Invoices.jsx) without leaving
// the page - see discussion on keeping the cashier inside Caixa. Exposes
// open{Nc,Nd,Rc}(invoiceId) via props.onReady(api) so the parent can trigger them,
// and calls props.onSuccess() after a successful creation so the parent can refresh
// its own document list.
const DocumentActionModals = forwardRef(function DocumentActionModals({ onSuccess }, ref) {
  const [ncModalOpen, setNcModalOpen] = useState(false);
  const [ncInvoice, setNcInvoice] = useState(null);
  const [ncLines, setNcLines] = useState([]);
  const [ncReason, setNcReason] = useState('ANL');
  const [ncCause, setNcCause] = useState('');
  const [ncSaving, setNcSaving] = useState(false);
  const [ncError, setNcError] = useState('');

  const [ndModalOpen, setNdModalOpen] = useState(false);
  const [ndInvoice, setNdInvoice] = useState(null);
  const [ndLines, setNdLines] = useState([{ item_type: 'product', product_id: '', service_id: '', quantity: '1', discount_percent: '0' }]);
  const [ndDocumentReference, setNdDocumentReference] = useState('');
  const [ndObservations, setNdObservations] = useState('');
  const [ndSaving, setNdSaving] = useState(false);
  const [ndError, setNdError] = useState('');

  const [rcModalOpen, setRcModalOpen] = useState(false);
  const [rcInvoice, setRcInvoice] = useState(null);
  const [rcAmount, setRcAmount] = useState('');
  const [rcDocumentReference, setRcDocumentReference] = useState('');
  const [rcObservations, setRcObservations] = useState('');
  const [rcSaving, setRcSaving] = useState(false);
  const [rcError, setRcError] = useState('');

  const INVOICE_TYPE_CODE = { FACTURA: 'FT', FACTURA_RECIBO: 'FR', PRO_FORMA: 'FP' };

  async function openNc(invoiceId) {
    const data = await getInvoiceDetail(invoiceId);
    setNcInvoice(data);
    setNcLines(data.lines.map((l) => ({
      invoice_line_id: l.id,
      product_name: l.product_name_snapshot,
      original_quantity: l.quantity,
      selected: true,
      quantity: String(l.quantity),
    })));
    setNcReason('ANL');
    setNcCause('');
    setNcError('');
    setNcModalOpen(true);
  }

  async function openNd(invoiceId) {
    const data = await getInvoiceDetail(invoiceId);
    setNdInvoice(data);
    setNdLines([{ item_type: 'product', product_id: '', service_id: '', quantity: '1', discount_percent: '0' }]);
    setNdDocumentReference((INVOICE_TYPE_CODE[data.invoice_type] || data.invoice_type) + ' ' + data.series + '/' + data.number);
    setNdObservations('');
    setNdError('');
    setNdModalOpen(true);
  }

  async function openRc(invoiceId) {
    const data = await getInvoiceDetail(invoiceId);
    setRcInvoice(data);
    setRcAmount('');
    setRcDocumentReference((INVOICE_TYPE_CODE[data.invoice_type] || data.invoice_type) + ' ' + data.series + '/' + data.number);
    setRcObservations('');
    setRcError('');
    setRcModalOpen(true);
  }

  useImperativeHandle(ref, () => ({ openNc, openNd, openRc }));

  async function handleNcSubmit(e) {
    e.preventDefault();
    setNcError('');
    const selectedLines = ncLines.filter((l) => l.selected);
    if (selectedLines.length === 0) {
      setNcError('Selecione pelo menos uma linha');
      return;
    }
    if (!ncCause.trim()) {
      setNcError('A causa e obrigatoria');
      return;
    }
    setNcSaving(true);
    try {
      await createCreditNote({
        activity_id: ncInvoice.activity_id,
        reference_invoice_id: ncInvoice.id,
        credit_note_reason: ncReason,
        credit_note_cause: ncCause.trim(),
        lines: selectedLines.map((l) => ({ invoice_line_id: l.invoice_line_id, quantity: parseFloat(l.quantity) })),
      });
      setNcModalOpen(false);
      if (onSuccess) onSuccess();
    } catch (err) {
      setNcError(extractErrorMessage(err, 'Erro ao emitir nota de credito'));
    } finally {
      setNcSaving(false);
    }
  }

  async function handleNdSubmit(e) {
    e.preventDefault();
    setNdError('');
    setNdSaving(true);
    try {
      await createDebitNote({
        activity_id: ndInvoice.activity_id,
        reference_invoice_id: ndInvoice.id,
        customer_id: ndInvoice.customer_id || null,
        document_reference: ndDocumentReference || null,
        observations: ndObservations || null,
        lines: ndLines.filter((l) => (l.item_type === 'product' ? l.product_id : l.service_id)).map((l) => ({
          item_type: l.item_type,
          product_id: l.item_type === 'product' ? l.product_id : null,
          service_id: l.item_type === 'service' ? l.service_id : null,
          quantity: parseFloat(l.quantity || '1'),
          discount_percent: parseFloat(l.discount_percent || '0'),
        })),
      });
      setNdModalOpen(false);
      if (onSuccess) onSuccess();
    } catch (err) {
      setNdError(extractErrorMessage(err, 'Erro ao emitir nota de debito'));
    } finally {
      setNdSaving(false);
    }
  }

  async function handleRcSubmit(e) {
    e.preventDefault();
    setRcError('');
    if (!rcAmount || parseFloat(rcAmount) <= 0) {
      setRcError('Indique um valor valido');
      return;
    }
    setRcSaving(true);
    try {
      await createReceipt({
        activity_id: rcInvoice.activity_id,
        reference_invoice_id: rcInvoice.id,
        amount: parseFloat(rcAmount),
        document_reference: rcDocumentReference || null,
        observations: rcObservations || null,
      });
      setRcModalOpen(false);
      if (onSuccess) onSuccess();
    } catch (err) {
      setRcError(extractErrorMessage(err, 'Erro ao emitir recibo'));
    } finally {
      setRcSaving(false);
    }
  }

  return (
    <>
      <Modal open={ncModalOpen} onClose={() => setNcModalOpen(false)} title="Emitir Nota de Credito">
        {ncInvoice && (
          <form onSubmit={handleNcSubmit} className="flex flex-col gap-4">
            <p className="text-[12px] text-text-muted">
              Referente a <span className="font-mono text-text-primary">{INVOICE_TYPE_CODE[ncInvoice.invoice_type] || ncInvoice.invoice_type} {ncInvoice.series}/{ncInvoice.number}</span>
            </p>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Linhas a creditar</label>
              <div className="flex flex-col gap-1.5 max-h-[220px] overflow-y-auto scrollbar-thin">
                {ncLines.map((l, idx) => (
                  <div key={l.invoice_line_id} className="flex items-center gap-2 bg-bg-inset border border-border rounded-md px-3 py-2">
                    <input
                      type="checkbox" checked={l.selected}
                      onChange={(e) => setNcLines((prev) => prev.map((x, i) => (i === idx ? { ...x, selected: e.target.checked } : x)))}
                    />
                    <span className="text-[12px] text-text-primary flex-1 truncate">{l.product_name}</span>
                    <input
                      type="number" step="0.01" min="0" max={l.original_quantity}
                      value={l.quantity}
                      onChange={(e) => setNcLines((prev) => prev.map((x, i) => (i === idx ? { ...x, quantity: e.target.value } : x)))}
                      className="w-20 bg-bg-elevated border border-border rounded px-2 py-1 text-[12px] text-text-primary font-mono outline-none focus:border-accent"
                    />
                  </div>
                ))}
              </div>
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Motivo</label>
              <select value={ncReason} onChange={(e) => setNcReason(e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent">
                <option value="ANL">Anulacao</option>
                <option value="RTF">Devolucao</option>
              </select>
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Causa *</label>
              <input value={ncCause} onChange={(e) => setNcCause(e.target.value)} maxLength={60} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent" />
            </div>
            {ncError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{ncError}</div>}
            <button type="submit" disabled={ncSaving} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
              {ncSaving && <Loader2 size={16} className="animate-spin" />}
              {ncSaving ? 'A emitir...' : 'Emitir nota de credito'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={ndModalOpen} onClose={() => setNdModalOpen(false)} title="Emitir Nota de Debito">
        {ndInvoice && (
          <form onSubmit={handleNdSubmit} className="flex flex-col gap-4">
            <p className="text-[12px] text-text-muted">
              Referente a <span className="font-mono text-text-primary">{INVOICE_TYPE_CODE[ndInvoice.invoice_type] || ndInvoice.invoice_type} {ndInvoice.series}/{ndInvoice.number}</span>
            </p>
            <div className="bg-accent/10 border-l-2 border-accent text-text-primary px-3.5 py-2.5 text-[12px] rounded-r flex items-start gap-2">
              <AlertTriangle size={14} className="shrink-0 mt-0.5 text-accent" />
              Adicione manualmente os artigos ou servicos a debitar - nao pre-preenchido a partir do documento original.
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Referencia do documento</label>
              <input value={ndDocumentReference} onChange={(e) => setNdDocumentReference(e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Observacoes</label>
              <input value={ndObservations} onChange={(e) => setNdObservations(e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent" />
            </div>
            {ndError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{ndError}</div>}
            <button type="submit" disabled={ndSaving} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
              {ndSaving && <Loader2 size={16} className="animate-spin" />}
              {ndSaving ? 'A emitir...' : 'Emitir nota de debito'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={rcModalOpen} onClose={() => setRcModalOpen(false)} title="Emitir Recibo">
        {rcInvoice && (
          <form onSubmit={handleRcSubmit} className="flex flex-col gap-4">
            <p className="text-[12px] text-text-muted">
              Referente a <span className="font-mono text-text-primary">{INVOICE_TYPE_CODE[rcInvoice.invoice_type] || rcInvoice.invoice_type} {rcInvoice.series}/{rcInvoice.number}</span>
            </p>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Valor *</label>
              <input type="number" step="0.01" min="0.01" value={rcAmount} onChange={(e) => setRcAmount(e.target.value)} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Referencia do documento</label>
              <input value={rcDocumentReference} onChange={(e) => setRcDocumentReference(e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Observacoes</label>
              <input value={rcObservations} onChange={(e) => setRcObservations(e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent" />
            </div>
            {rcError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{rcError}</div>}
            <button type="submit" disabled={rcSaving} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
              {rcSaving && <Loader2 size={16} className="animate-spin" />}
              {rcSaving ? 'A emitir...' : 'Emitir recibo'}
            </button>
          </form>
        )}
      </Modal>
    </>
  );
});

export default DocumentActionModals;

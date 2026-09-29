import { useState, useEffect, forwardRef, useImperativeHandle } from 'react';
import { X, Loader2, AlertTriangle } from 'lucide-react';
import Modal from './Modal';
import Select from './Select';
import { getInvoiceDetail, createDebitNote, createReceipt, getOpenCashPoints } from '../api/invoices';
import { getMyCompanyBankAccounts } from '../api/company';
import { extractErrorMessage } from '../utils/errors';
import { paymentMethodsApi } from '../api/catalogs';

// Self-contained ND/RC action modals against an already-issued invoice - the ONE receipt modal of the app, used
// from any screen (Caixa's "Consultar documentos" with its own cash point, Faturas choosing one) without leaving
// the page - see discussion on keeping the cashier inside Caixa. Exposes
// open{Nd,Rc}(invoiceId) via props.onReady(api) so the parent can trigger them,
// and calls props.onSuccess() after a successful creation so the parent can refresh
// its own document list.
const DocumentActionModals = forwardRef(function DocumentActionModals({ onSuccess, cashPosId }, ref) {

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
  const [rcPaymentMethodId, setRcPaymentMethodId] = useState('');
  const [rcCashPosId, setRcCashPosId] = useState('');
  const [rcBankAccountId, setRcBankAccountId] = useState('');
  const [rcCashPoints, setRcCashPoints] = useState([]);
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [bankAccounts, setBankAccounts] = useState([]);

  useEffect(() => {
    paymentMethodsApi.list().then((data) => setPaymentMethods(data.filter((m) => m.is_active))).catch(() => {});
    getMyCompanyBankAccounts().then((data) => setBankAccounts(data.filter((b) => b.is_active))).catch(() => {});
  }, []);

  // Same rules as the invoice form: cash enters a cash point (is_cash), a bank method names the account
  // (uses_bank_account). At the Caixa the cash point is the screen's own (cashPosId), shown locked.
  const rcMethod = paymentMethods.find((m) => m.id === rcPaymentMethodId);
  const rcIsCash = rcMethod?.is_cash === true;
  const rcUsesBank = rcMethod?.uses_bank_account === true;
  const rcFixedPos = !!cashPosId;

  const INVOICE_TYPE_CODE = { FACTURA: 'FT', FACTURA_RECIBO: 'FR', PRO_FORMA: 'FP' };

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
    const due = Number(data.amount_due || 0);
    setRcAmount(due > 0 ? due.toFixed(2) : '');
    setRcPaymentMethodId(paymentMethods.find((m) => m.code === 'NU')?.id || '');
    setRcCashPosId(cashPosId || '');
    setRcBankAccountId('');
    setRcDocumentReference((INVOICE_TYPE_CODE[data.invoice_type] || data.invoice_type) + ' ' + data.series + '/' + data.number);
    setRcObservations('');
    setRcError('');
    getOpenCashPoints().then(setRcCashPoints).catch(() => setRcCashPoints([]));
    setRcModalOpen(true);
  }

  useImperativeHandle(ref, () => ({ openNd, openRc }));

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
    if (!rcPaymentMethodId) {
      setRcError('Selecione o metodo de pagamento');
      return;
    }
    if (rcIsCash) {
      // The list may be stale - a cash point closed since the modal opened: reload it before sending.
      const points = await getOpenCashPoints().catch(() => []);
      setRcCashPoints(points);
      if (!rcCashPosId || !points.some((p) => p.pos_id === rcCashPosId)) {
        setRcError(rcFixedPos ? 'Esta caixa nao tem sessao aberta - abra a caixa antes de receber' : 'Selecione uma caixa com sessao aberta');
        return;
      }
    }
    setRcSaving(true);
    try {
      await createReceipt({
        activity_id: rcInvoice.activity_id,
        reference_invoice_id: rcInvoice.id,
        amount: parseFloat(rcAmount),
        document_reference: rcDocumentReference || null,
        observations: rcObservations || null,
        payment_method_id: rcPaymentMethodId,
        cash_pos_id: rcIsCash ? rcCashPosId : null,
        bank_account_id: rcUsesBank ? (rcBankAccountId || null) : null,
      });
      setRcModalOpen(false);
      setRcPaymentMethodId('');
      if (onSuccess) onSuccess();
    } catch (err) {
      setRcError(extractErrorMessage(err, 'Erro ao emitir recibo'));
    } finally {
      setRcSaving(false);
    }
  }

  return (
    <>
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

      <Modal open={rcModalOpen} onClose={() => setRcModalOpen(false)} title="Emitir Recibo" maxWidthClass="max-w-2xl">
        {rcInvoice && (
          <form onSubmit={handleRcSubmit} className="flex flex-col gap-4">
            <p className="text-[12px] text-text-muted">
              Referente a <span className="font-mono text-text-primary">{INVOICE_TYPE_CODE[rcInvoice.invoice_type] || rcInvoice.invoice_type} {rcInvoice.series}/{rcInvoice.number}</span>
              {Number(rcInvoice.amount_due || 0) > 0 && <span> - a pagar: <span className="font-mono text-text-primary">{Number(rcInvoice.amount_due).toFixed(2)}</span></span>}
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Valor recebido *</label>
                <input type="number" step="0.01" min="0.01" value={rcAmount} onChange={(e) => setRcAmount(e.target.value)} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent font-mono" />
              </div>
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Metodo de pagamento *</label>
                <Select value={rcPaymentMethodId} onChange={setRcPaymentMethodId} options={paymentMethods.map((m) => ({ value: m.id, label: m.name }))} placeholder="Selecionar" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className={rcUsesBank ? '' : 'opacity-60 pointer-events-none'}>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Conta bancaria</label>
                <Select value={rcUsesBank ? rcBankAccountId : ''} onChange={setRcBankAccountId} options={bankAccounts.map((b) => ({ value: b.id, label: b.account_number }))} placeholder={rcUsesBank ? 'Selecionar' : 'Nao aplicavel a este metodo'} />
              </div>
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Referencia</label>
                <input value={rcDocumentReference} disabled className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent font-mono opacity-70 cursor-not-allowed" />
              </div>
            </div>
            <div className={rcIsCash ? '' : 'opacity-60 pointer-events-none'}>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Caixa de entrada{rcIsCash ? ' *' : ''}</label>
              {rcFixedPos ? (
                <input value={rcIsCash ? (rcCashPoints.find((cp) => cp.pos_id === cashPosId)?.name || 'Caixa sem sessao aberta') : 'Sem recebimento em numerario'} disabled className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent opacity-70 cursor-not-allowed" />
              ) : rcIsCash && rcCashPoints.length === 0 ? (
                <p className="text-[12px] text-danger">Nenhuma caixa com sessao aberta - abra uma caixa para receber em numerario</p>
              ) : (
                <Select value={rcIsCash ? rcCashPosId : ''} onChange={setRcCashPosId} options={rcCashPoints.map((cp) => ({ value: cp.pos_id, label: cp.name }))} placeholder={rcIsCash ? 'Selecionar' : 'Sem recebimento em numerario'} />
              )}
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Observacoes</label>
              <input value={rcObservations} onChange={(e) => setRcObservations(e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent" />
            </div>
            {rcError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{rcError}</div>}
            <button type="submit" disabled={rcSaving || !(parseFloat(rcAmount) > 0) || !rcPaymentMethodId || (rcIsCash && !rcCashPosId)} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
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

import { useEffect, useState } from 'react';
import { HandCoins, Loader2, Eye, FileText, Ban } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import DateInput from '../components/DateInput';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { useCan } from '../utils/permissions';
import { listSuppliers } from '../api/suppliers';
import { listSupplierPayments, getSupplierPayment, cancelSupplierPayment, fetchSupplierPaymentPdfBlob } from '../api/supplierPayments';
import { useToastState } from '../components/Toaster';

// Pagamentos a fornecedores (supplier_payment_service): the payments made from Faturas de compra ("Pagar") - each with
// the invoices it settled; never deleted: cancelled with a reason (the invoices are owed again, cash goes back to its till).
const inputCls = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5 whitespace-nowrap';
const kz = (v) => formatKz(v) + ' Kz';
const day = (iso) => (iso ? new Date(iso + 'T00:00:00').toLocaleDateString('pt-PT') : '-');
const when = (v) => (v ? new Date(v).toLocaleString('pt-PT', { timeZone: 'Africa/Luanda' }) : '-');
const todayIso = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Africa/Luanda' });
const STATUS = { REGISTADO: ['Registado', 'text-success bg-success/10'], ANULADO: ['Anulado', 'text-danger bg-danger/10'] };

export default function PagamentosFornecedores() {
  const can = useCan();
  const [payments, setPayments] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useToastState('error');
  const [filters, setFilters] = useState({ supplierId: '', status: '', dateFrom: todayIso().slice(0, 8) + '01', dateTo: todayIso() });
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useToastState('error');
  const [cancelReason, setCancelReason] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [pdf, setPdf] = useState(null);

  async function load() {
    setLoading(true);
    setError('');
    try {
      setPayments(await listSupplierPayments(filters));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar os pagamentos'));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { load(); }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { listSuppliers().then(setSuppliers).catch(() => {}); }, []);

  async function openDetail(id) {
    setDetailError('');
    setCancelReason('');
    try {
      setDetail(await getSupplierPayment(id));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao abrir o pagamento'));
    }
  }

  async function cancel() {
    setCancelling(true);
    setDetailError('');
    try {
      setDetail(await cancelSupplierPayment(detail.id, cancelReason));
      setCancelReason('');
      load();
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao anular o pagamento'));
    } finally {
      setCancelling(false);
    }
  }

  async function openPdf() {
    try {
      setPdf(await fetchSupplierPaymentPdfBlob(detail.id));
    } catch (err) {
      setDetailError(extractErrorMessage(err, 'Erro ao gerar o PDF'));
    }
  }

  const total = payments.filter((p) => p.status === 'REGISTADO').reduce((s, p) => s + p.amount, 0);

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="mb-6">
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
          <HandCoins size={22} className="text-accent" /> Pagamentos a fornecedores
        </h2>
        <p className="text-text-muted text-sm">Os pagamentos das faturas de compra - registam-se em Faturas de compra, marcando as faturas em dívida e «Pagar»</p>
      </div>

      <div className="flex items-end gap-2.5 mb-5 flex-wrap">
        <div className="w-64">
          <label className={labelCls}>Fornecedor</label>
          <Select value={filters.supplierId} onChange={(v) => setFilters((f) => ({ ...f, supplierId: v }))} placeholder="Todos"
            options={[{ value: '', label: 'Todos' }, ...suppliers.map((s) => ({ value: s.id, label: s.name }))]} />
        </div>
        <div className="w-40">
          <label className={labelCls}>Estado</label>
          <Select value={filters.status} onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
            options={[{ value: '', label: 'Todos' }, { value: 'REGISTADO', label: 'Registado' }, { value: 'ANULADO', label: 'Anulado' }]} />
        </div>
        <div>
          <label className={labelCls}>De</label>
          <DateInput value={filters.dateFrom} onChange={(e) => setFilters((f) => ({ ...f, dateFrom: e.target.value }))} className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Até</label>
          <DateInput value={filters.dateTo} min={filters.dateFrom || undefined} onChange={(e) => setFilters((f) => ({ ...f, dateTo: e.target.value }))} className={inputCls} />
        </div>
        <div className="ml-auto bg-bg-elevated border border-border rounded-lg px-5 py-2.5">
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Total pago no período</p>
          <p className="font-mono font-semibold text-lg text-text-primary">{kz(total)}</p>
        </div>
      </div>


      <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
        {loading ? (
          <div className="flex justify-center py-12"><Loader2 size={18} className="animate-spin text-accent" /></div>
        ) : payments.length === 0 ? (
          <p className="text-text-muted text-[13px] text-center py-12">Nenhum pagamento neste período</p>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-border">
              <th className={th + ' text-left'}>Número</th><th className={th + ' text-left'}>Data</th><th className={th + ' text-left'}>Fornecedor</th>
              <th className={th + ' text-left'}>Método</th><th className={th + ' text-left'}>Saída de</th><th className={th + ' text-left'}>Referência</th>
              <th className={th + ' text-right'}>Valor</th><th className={th + ' text-left'}>Estado</th><th className={th + ' text-right'}>Ações</th>
            </tr></thead>
            <tbody>
              {payments.map((p) => (
                <tr key={p.id} className={'border-b border-border last:border-0 ' + (p.status === 'ANULADO' ? 'opacity-50' : '')}>
                  <td className="px-3 py-2.5 font-mono text-text-primary whitespace-nowrap">{p.reference}</td>
                  <td className="px-3 py-2.5 font-mono text-[12px] text-text-muted">{day(p.payment_date)}</td>
                  <td className="px-3 py-2.5 text-text-primary">{p.supplier_name}</td>
                  <td className="px-3 py-2.5 text-text-muted">{p.method}</td>
                  <td className="px-3 py-2.5 text-text-muted">{p.source || '-'}</td>
                  <td className="px-3 py-2.5 font-mono text-[12px] text-text-muted">{p.reference_text || '-'}</td>
                  <td className="px-3 py-2.5 text-right font-mono font-semibold text-text-primary whitespace-nowrap">{kz(p.amount)}</td>
                  <td className="px-3 py-2.5"><span className={'text-[11px] font-semibold uppercase tracking-wide px-2 py-1 rounded ' + STATUS[p.status][1]}>{STATUS[p.status][0]}</span></td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => openDetail(p.id)} className="inline-flex items-center gap-1.5 border border-border hover:border-accent hover:text-accent text-text-primary text-[12px] font-medium px-2.5 py-1.5 rounded-md cursor-pointer">
                      <Eye size={14} /> Ver
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail ? 'Pagamento ' + detail.reference : ''} maxWidthClass="max-w-4xl">
        {detail && (
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-[13px]">
              <div><p className={labelCls}>Fornecedor</p><p className="text-text-primary">{detail.supplier_name}</p><p className="font-mono text-[11px] text-text-muted">{detail.supplier_nif || ''}</p></div>
              <div><p className={labelCls}>Data</p><p className="text-text-primary">{day(detail.payment_date)}</p></div>
              <div><p className={labelCls}>Método</p><p className="text-text-primary">{detail.method}</p><p className="text-[11px] text-text-muted">{detail.source || ''}</p></div>
              <div><p className={labelCls}>Referência</p><p className="font-mono text-text-primary">{detail.reference_text || '-'}</p></div>
            </div>
            {detail.status === 'ANULADO' && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
                Anulado por {detail.cancelled_by || '-'} em {when(detail.cancelled_at)}: {detail.cancel_reason}
              </div>
            )}
            <div className="border border-border rounded-md overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-border">
                  <th className={th + ' text-left'}>Registo</th><th className={th + ' text-left'}>Documento</th><th className={th + ' text-left'}>Data</th>
                  <th className={th + ' text-right'}>Total da fatura</th><th className={th + ' text-right'}>Pago</th>
                </tr></thead>
                <tbody>
                  {detail.allocations.map((a) => (
                    <tr key={a.purchase_invoice_id} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 font-mono text-text-muted">{a.reference}</td>
                      <td className="px-3 py-2 font-mono text-text-primary">{a.supplier_document}</td>
                      <td className="px-3 py-2 font-mono text-[12px] text-text-muted">{day(a.document_date)}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-muted">{kz(a.invoice_total)}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-primary">{kz(a.amount)}</td>
                    </tr>
                  ))}
                  <tr className="bg-bg-inset">
                    <td colSpan={4} className="px-3 py-2 font-semibold text-text-primary">Total pago</td>
                    <td className="px-3 py-2 text-right font-mono font-semibold text-text-primary">{kz(detail.amount)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between gap-3 flex-wrap text-[12px] text-text-muted">
              <p>Registado por {detail.created_by || '-'} em {when(detail.created_at)}{detail.notes ? ' · ' + detail.notes : ''}</p>
              <button onClick={openPdf} className="inline-flex items-center gap-1.5 border border-border hover:border-accent hover:text-accent text-text-primary text-[12px] font-medium px-3 py-1.5 rounded-md cursor-pointer">
                <FileText size={14} /> Ver PDF
              </button>
            </div>
            {detail.status === 'REGISTADO' && can('purchases:pay') && (
              <div className="flex items-end gap-2 border-t border-border pt-4">
                <div className="flex-1">
                  <label className={labelCls}>Motivo da anulação</label>
                  <input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="Ex: valor errado" className={inputCls} />
                </div>
                <button onClick={cancel} disabled={cancelling || !cancelReason.trim()} className="flex items-center gap-1.5 border border-danger/60 text-danger hover:bg-danger/10 disabled:opacity-50 text-[13px] font-medium px-4 py-2 rounded-md cursor-pointer">
                  {cancelling ? <Loader2 size={14} className="animate-spin" /> : <Ban size={14} />} Anular
                </button>
              </div>
            )}
          </div>
        )}
      </Modal>

      <Modal open={!!pdf} onClose={() => { if (pdf) URL.revokeObjectURL(pdf); setPdf(null); }} title={detail ? 'Pagamento ' + detail.reference : ''} maxWidthClass="max-w-3xl" stacked>
        {pdf && <iframe src={pdf} title="Pagamento" className="w-full h-[70vh] rounded-md border border-border" />}
      </Modal>
    </main>
  );
}

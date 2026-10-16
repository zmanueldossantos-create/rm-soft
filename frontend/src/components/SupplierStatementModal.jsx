import { useEffect, useState } from 'react';
import { FileText, Loader2 } from 'lucide-react';
import Modal from './Modal';
import DateInput from './DateInput';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { getSupplierStatement, fetchSupplierStatementPdfBlob } from '../api/supplierPayments';

// Conta corrente of a supplier (supplier_payment_service.supplier_statement): its invoices raise what the company owes,
// its credit notes and the payments lower it - with the running balance, from the balance before the period.
const inputCls = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5 whitespace-nowrap';
const kz = (v) => formatKz(v) + ' Kz';
const day = (iso) => (iso ? new Date(iso + 'T00:00:00').toLocaleDateString('pt-PT') : '-');
const yearStart = () => new Date().getFullYear() + '-01-01';
const todayIso = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Africa/Luanda' });

export default function SupplierStatementModal({ supplier, onClose }) {
  const [range, setRange] = useState({ from: yearStart(), to: todayIso() });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [pdf, setPdf] = useState(null);

  useEffect(() => {
    if (!supplier) return;
    setLoading(true);
    setError('');
    getSupplierStatement(supplier.id, range.from, range.to).then(setData)
      .catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar a conta corrente')))
      .finally(() => setLoading(false));
  }, [supplier, range]);

  async function openPdf() {
    try {
      setPdf(await fetchSupplierStatementPdfBlob(supplier.id, range.from, range.to));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao gerar o PDF'));
    }
  }

  return (
    <>
      <Modal open={!!supplier} onClose={onClose} title={supplier ? 'Conta corrente - ' + supplier.name : ''} maxWidthClass="max-w-5xl">
        {supplier && (
          <div className="flex flex-col gap-4">
            <div className="flex items-end gap-3 flex-wrap">
              <div><label className={labelCls}>De</label><DateInput value={range.from} onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))} className={inputCls} /></div>
              <div><label className={labelCls}>Até</label><DateInput value={range.to} min={range.from || undefined} onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))} className={inputCls} /></div>
              <button onClick={openPdf} disabled={!data} className="ml-auto inline-flex items-center gap-1.5 border border-border hover:border-accent hover:text-accent text-text-primary text-[13px] font-medium px-3.5 py-2 rounded-md cursor-pointer disabled:opacity-50">
                <FileText size={14} /> Ver PDF
              </button>
            </div>
            {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>}
            {loading || !data ? (
              <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-accent" /></div>
            ) : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {[['Saldo anterior', data.opening_balance], ['Débitos (pagamentos, NC)', data.total_debit], ['Créditos (faturas)', data.total_credit], ['Saldo em dívida', data.closing_balance]].map(([label, value]) => (
                    <div key={label} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5">
                      <p className="text-[10px] uppercase tracking-wide text-text-muted">{label}</p>
                      <p className="font-mono font-semibold text-text-primary">{kz(value)}</p>
                    </div>
                  ))}
                </div>
                <div className="border border-border rounded-md overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="border-b border-border">
                      <th className={th + ' text-left'}>Data</th><th className={th + ' text-left'}>Documento</th><th className={th + ' text-left'}>Descrição</th>
                      <th className={th + ' text-right'}>Débito</th><th className={th + ' text-right'}>Crédito</th><th className={th + ' text-right'}>Saldo</th>
                    </tr></thead>
                    <tbody>
                      {data.lines.length === 0 && <tr><td colSpan={6} className="text-center text-text-muted text-[13px] py-8">Nenhum movimento neste período</td></tr>}
                      {data.lines.map((l, k) => (
                        <tr key={k} className="border-b border-border last:border-0">
                          <td className="px-3 py-2 font-mono text-[12px] text-text-muted whitespace-nowrap">{day(l.date)}</td>
                          <td className="px-3 py-2 font-mono text-text-primary whitespace-nowrap">{l.document}<span className="block text-[11px] text-text-muted">{l.internal !== l.document ? l.internal : ''}</span></td>
                          <td className="px-3 py-2 text-text-muted">{l.description}</td>
                          <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{l.debit ? kz(l.debit) : ''}</td>
                          <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{l.credit ? kz(l.credit) : ''}</td>
                          <td className="px-3 py-2 text-right font-mono font-semibold text-text-primary whitespace-nowrap">{kz(l.balance)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="text-[12px] text-text-muted">O saldo é o valor em dívida ao fornecedor: uma fatura aumenta-o, uma nota de crédito ou um pagamento diminui-o; uma fatura-recibo é paga na emissão.</p>
              </>
            )}
          </div>
        )}
      </Modal>
      <Modal open={!!pdf} onClose={() => { if (pdf) URL.revokeObjectURL(pdf); setPdf(null); }} title={supplier ? 'Conta corrente - ' + supplier.name : ''} maxWidthClass="max-w-3xl" stacked>
        {pdf && <iframe src={pdf} title="Conta corrente" className="w-full h-[70vh] rounded-md border border-border" />}
      </Modal>
    </>
  );
}

import { useEffect, useState } from 'react';
import { Loader2, Printer } from 'lucide-react';
import Modal from './Modal';
import { traceLot, fetchLotTracePdf } from '../api/pharmacy';
import { extractErrorMessage } from '../utils/errors';
import { useToastState } from './Toaster';

const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-3 py-2.5';
const qty = (v) => (v == null ? '' : Number(v).toLocaleString('pt-PT', { maximumFractionDigits: 3 }));
const when = (iso) => new Date(iso).toLocaleDateString('pt-PT');

// Where one lot came from and where it went - its entry, its transfers, every sale (with the customer and the receita),
// guide and loss - and what is left in each warehouse. What a recall by the manufacturer or the ARMED needs.
export default function LotTraceModal({ lot, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useToastState('error');
  const [pdf, setPdf] = useState(null);

  useEffect(() => {
    if (!lot) return;
    setData(null);
    setError('');
    traceLot(lot.id).then(setData).catch((err) => setError(extractErrorMessage(err, 'Erro ao rastrear o lote')));
  }, [lot]);

  async function openPdf() {
    try {
      setPdf(await fetchLotTracePdf(lot.id));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao gerar o PDF'));
    }
  }

  return (
    <>
      <Modal open={!!lot} onClose={onClose} stacked maxWidthClass="max-w-6xl"
        title={data ? 'Rastrear lote - ' + data.product_name + ' · ' + data.label : 'Rastrear lote'}>
        {!error && !data && <div className="flex justify-center py-10"><Loader2 size={22} className="animate-spin text-accent" /></div>}
        {data && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div className="flex gap-6 text-[13px]">
                <span className="text-text-muted">Vendido <span className="font-mono text-text-primary">{qty(data.sold_total)}</span></span>
                <span className="text-text-muted">Em stock <span className="font-mono text-text-primary">{qty(data.remaining_total)}</span>
                  {data.remaining.length > 0 && <span className="ml-1">({data.remaining.map((r) => r.warehouse + ': ' + qty(r.quantity)).join(' · ')})</span>}
                </span>
              </div>
              <button type="button" onClick={openPdf} className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[13px] font-medium rounded-md px-3 py-2 cursor-pointer">
                <Printer size={14} /> Imprimir
              </button>
            </div>
            <div className="border border-border rounded-md overflow-x-auto max-h-[60vh] overflow-y-auto scrollbar-thin">
              <table className="w-full text-sm min-w-[900px]">
                <thead className="sticky top-0 bg-bg-elevated"><tr className="border-b border-border">
                  <th className={th + ' text-left'}>Data</th><th className={th + ' text-left'}>Movimento</th><th className={th + ' text-left'}>Documento</th>
                  <th className={th + ' text-left'}>Armazém</th><th className={th + ' text-left'}>Cliente / origem / motivo</th><th className={th + ' text-left'}>Receita</th>
                  <th className={th + ' text-right'}>Entrada</th><th className={th + ' text-right'}>Saída</th>
                </tr></thead>
                <tbody>
                  {data.movements.map((m, i) => (
                    <tr key={i} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 font-mono text-text-muted whitespace-nowrap">{when(m.date)}</td>
                      <td className="px-3 py-2 text-text-primary">{m.type}</td>
                      <td className="px-3 py-2 font-mono text-text-primary whitespace-nowrap">{m.reference || '-'}</td>
                      <td className="px-3 py-2 text-text-muted">{m.warehouse}</td>
                      <td className="px-3 py-2 text-text-primary">{m.detail || '-'}</td>
                      <td className="px-3 py-2 font-mono text-text-primary">{m.prescription || ''}</td>
                      <td className="px-3 py-2 font-mono text-success text-right">{qty(m.quantity_in)}</td>
                      <td className="px-3 py-2 font-mono text-danger text-right">{qty(m.quantity_out)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Modal>
      <Modal open={!!pdf} onClose={() => { URL.revokeObjectURL(pdf); setPdf(null); }} title="Rastreabilidade do lote" maxWidthClass="max-w-5xl" stacked>
        {pdf && <iframe src={pdf} title="Rastreabilidade do lote" className="w-full h-[75vh] rounded-md border border-border" />}
      </Modal>
    </>
  );
}

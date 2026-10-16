import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import Modal from './Modal';
import { listProductLots } from '../api/stock';
import { extractErrorMessage } from '../utils/errors';

const th = 'text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2.5';
const qty = (v) => Number(v || 0).toLocaleString('pt-PT', { maximumFractionDigits: 3 });
const day = (iso) => (iso ? new Date(iso + 'T00:00:00').toLocaleDateString('pt-PT') : '-');

// The state of a lot: expired (never sold - to write off), expiring soon, or fine.
function LotState({ lot }) {
  if (lot.expiry_date == null) return <span className="text-[12px] text-text-muted">Sem validade</span>;
  if (lot.expired) {
    return <span className="inline-flex bg-danger/10 text-danger text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded">Expirado</span>;
  }
  const soon = lot.days_left <= 30;
  const text = lot.days_left === 0 ? 'Expira hoje' : lot.days_left === 1 ? 'Expira amanhã' : 'Expira em ' + lot.days_left + ' dias';
  return (
    <span className={'inline-flex text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded ' + (soon ? 'bg-amber-500/10 text-amber-500' : 'bg-success/10 text-success')}>
      {text}
    </span>
  );
}

// The lots of a product followed by lot / expiry still holding stock, in every warehouse - in the order the sales take
// them (the first to expire first).
export default function StockLotsModal({ product, onClose }) {
  const [lots, setLots] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!product) return;
    setLots(null);
    setError('');
    listProductLots(product.product_id)
      .then(setLots)
      .catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar os lotes')));
  }, [product]);

  const total = (lots || []).reduce((s, l) => s + l.quantity, 0);

  return (
    <Modal open={!!product} onClose={onClose} title={product ? 'Lotes - ' + product.product_name : ''} maxWidthClass="max-w-4xl">
      {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>}
      {!error && lots === null && <div className="flex justify-center py-10"><Loader2 size={22} className="animate-spin text-accent" /></div>}
      {!error && lots && lots.length === 0 && <p className="text-sm text-text-muted py-6 text-center">Nenhum lote com stock.</p>}
      {!error && lots && lots.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="border border-border rounded-md overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-border">
                <th className={th + ' text-left'}>Armazém</th><th className={th + ' text-left'}>Lote</th>
                <th className={th + ' text-left'}>Validade</th><th className={th + ' text-right'}>Quantidade</th><th className={th + ' text-left'}>Estado</th>
              </tr></thead>
              <tbody>
                {lots.map((l) => (
                  <tr key={l.id} className={'border-b border-border last:border-0 ' + (l.expired ? 'bg-danger/5' : '')}>
                    <td className="px-4 py-2.5 text-text-primary">{l.warehouse_name}</td>
                    <td className="px-4 py-2.5 font-mono text-text-primary">{l.lot_number || (l.expiry_date ? '-' : 'Sem lote')}</td>
                    <td className="px-4 py-2.5 font-mono text-text-muted">{day(l.expiry_date)}</td>
                    <td className="px-4 py-2.5 font-mono text-text-primary text-right">{qty(l.quantity)}</td>
                    <td className="px-4 py-2.5"><LotState lot={l} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[12px] text-text-muted">
            Total <span className="font-mono text-text-primary">{qty(total)}</span> · as vendas e consumos usam primeiro o lote que expira primeiro; um lote expirado nunca é vendido (registe a perda).
          </p>
        </div>
      )}
    </Modal>
  );
}

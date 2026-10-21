import { useEffect, useState } from 'react';
import { useToastState } from './Toaster';
import { Loader2, TrendingUp, TrendingDown } from 'lucide-react';
import DateInput from './DateInput';
import { getCostHistory } from '../api/products';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';

// Histórico do custo (cost_history_service): every entry that moved the product's weighted average cost - a priced
// reception, a production - with its unit cost and the cost before and after. The tab of the Produto and
// Matéria-prima sheets. The history starts with the version that records it.
const KIND_LABELS = { RECEPCAO: 'Receção', PRODUCAO: 'Produção' };
const inputCls = 'bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const th = 'px-3 py-2 whitespace-nowrap';

function cost(value) {
  return value == null ? '-' : formatKz(value) + ' Kz';
}

function Tile({ label, value }) {
  return (
    <div className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5">
      <p className="text-[10px] uppercase tracking-wide text-text-muted">{label}</p>
      <p className="font-mono font-semibold text-text-primary mt-0.5">{value}</p>
    </div>
  );
}

export default function CostHistory({ productId }) {
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [history, setHistory] = useState(null);
  const [error, setError] = useToastState('error');

  useEffect(() => {
    let cancelled = false;
    setError('');
    getCostHistory(productId, { dateFrom, dateTo })
      .then((data) => { if (!cancelled) setHistory(data); })
      .catch((err) => { if (!cancelled) setError(extractErrorMessage(err, 'Erro ao carregar o histórico do custo')); });
    return () => { cancelled = true; };
  }, [productId, dateFrom, dateTo]);

  if (error) return null;
  if (!history) return <div className="flex justify-center py-10"><Loader2 size={18} className="animate-spin text-accent" /></div>;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Tile label="Custo médio atual" value={cost(history.current_cost)} />
        <Tile label="Último preço de compra" value={cost(history.last_purchase_price)} />
        <Tile label="Custo mais baixo" value={cost(history.min_unit_cost)} />
        <Tile label="Custo mais alto" value={cost(history.max_unit_cost)} />
      </div>

      <div className="flex items-end gap-2 flex-wrap">
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">De</label>
          <DateInput value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Até</label>
          <DateInput value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} className={inputCls} />
        </div>
      </div>

      {history.entries.length === 0 ? (
        <p className="text-text-muted text-[13px] text-center py-8">
          Nenhuma entrada com custo {dateFrom || dateTo ? 'neste período' : 'registada ainda'} - o histórico regista as receções com preço e as produções.
        </p>
      ) : (
        <div className="border border-border rounded-md overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-[10px] uppercase tracking-wide text-text-muted">
                <th className={th + ' text-left'}>Data</th>
                <th className={th + ' text-left'}>Origem</th>
                <th className={th + ' text-left'}>Armazém</th>
                <th className={th + ' text-right'}>Quantidade</th>
                <th className={th + ' text-right'}>Custo unitário</th>
                <th className={th + ' text-right'}>Custo médio</th>
                <th className={th + ' text-right'}>Variação</th>
              </tr>
            </thead>
            <tbody>
              {history.entries.map((e) => {
                const up = e.change_pct != null && e.change_pct > 0;
                const down = e.change_pct != null && e.change_pct < 0;
                return (
                  <tr key={e.id} className="border-b border-border last:border-0">
                    <td className={th + ' font-mono text-[12px] text-text-muted whitespace-nowrap'}>{new Date(e.date + 'T00:00:00').toLocaleDateString('pt-PT')}</td>
                    <td className={th + ' text-[12px] text-text-primary'}>
                      {KIND_LABELS[e.kind] || e.kind}{e.reference ? ' ' + e.reference : ''}
                      {e.supplier && <span className="block text-[11px] text-text-muted">{e.supplier}</span>}
                    </td>
                    <td className={th + ' text-[12px] text-text-muted'}>{e.warehouse || '-'}</td>
                    <td className={th + ' text-right font-mono text-[12px] text-text-primary'}>{e.quantity.toLocaleString('pt-PT')}</td>
                    <td className={th + ' text-right font-mono text-[12px] text-text-primary whitespace-nowrap'}>{cost(e.unit_cost)}</td>
                    <td className={th + ' text-right font-mono text-[12px] whitespace-nowrap'}>
                      <span className="text-text-muted">{e.cost_before == null ? '-' : formatKz(e.cost_before)} → </span>
                      <span className="text-text-primary font-semibold">{cost(e.cost_after)}</span>
                    </td>
                    <td className={th + ' text-right font-mono text-[12px] whitespace-nowrap ' + (up ? 'text-danger' : down ? 'text-success' : 'text-text-muted')}>
                      {e.change_pct == null ? '-' : (
                        <span className="inline-flex items-center gap-1 justify-end">
                          {up && <TrendingUp size={12} />}{down && <TrendingDown size={12} />}
                          {(e.change_pct > 0 ? '+' : '') + e.change_pct.toLocaleString('pt-PT') + ' %'}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

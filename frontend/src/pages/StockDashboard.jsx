import { useState, useEffect } from 'react';
import { Gauge, Loader2, AlertTriangle, Package2, Wallet, Search } from 'lucide-react';
import apiClient from '../api/client';
import Select from '../components/Select';
import UnitBreakdown from '../components/UnitBreakdown';
import { extractErrorMessage } from '../utils/errors';

// Without a period: the current stock; with one: the stock at the end of that fiscal period (from the ledger).
async function getStockDashboard(periodId) {
  const res = await apiClient.get('/stock/dashboard', { params: periodId ? { fiscal_period_id: periodId } : {} });
  return res.data;
}

function formatMoney(v) {
  return Number(v || 0).toLocaleString('pt-AO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Kz';
}

function formatQty(v) {
  return Number(v).toLocaleString('pt-AO', { minimumFractionDigits: 0, maximumFractionDigits: 3 });
}

export default function StockDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('todos'); // todos | baixo | zero
  const [periodId, setPeriodId] = useState(''); // '' = the current stock
  const [periods, setPeriods] = useState([]);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError('');
      try {
        const summary = await getStockDashboard(periodId);
        setData(summary);
        setPeriods(summary.periods || []);
      } catch (err) {
        setError(extractErrorMessage(err, 'Erro ao carregar o resumo de stock'));
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [periodId]);

  const items = (data?.items || []).filter((item) => {
    if (filter === 'baixo' && !item.is_low) return false;
    if (filter === 'zero' && !item.is_zero) return false;
    if (search && !(item.code + ' ' + item.name).toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Gauge size={22} className="text-accent" />
        Resumo de Stock
      </h2>
      <p className="text-text-muted text-sm mb-6">Visão consolidada do stock em todos os armazéns</p>
      {data?.period_label && <p className="text-accent text-sm -mt-4 mb-6">Stock no fim de {data.period_label}, calculado pelos movimentos</p>}

      {loading && (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      )}

      {error && (
        <div className="px-6 py-4 text-danger text-sm bg-danger/10 rounded-lg mb-6">{error}</div>
      )}

      {!loading && !error && data && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
            <div className="bg-bg-elevated border border-border rounded-lg p-4">
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5 mb-1.5"><Package2 size={12} />Produtos ativos</p>
              <p className="font-display font-semibold text-2xl text-text-primary">{data.total_products}</p>
            </div>
            <button
              type="button"
              onClick={() => setFilter(filter === 'baixo' ? 'todos' : 'baixo')}
              className={'text-left bg-bg-elevated border rounded-lg p-4 transition-colors cursor-pointer ' + (filter === 'baixo' ? 'border-[#f59e0b]' : 'border-border hover:border-[#f59e0b]/50')}
            >
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5 mb-1.5"><AlertTriangle size={12} className="text-[#f59e0b]" />Stock baixo</p>
              <p className="font-display font-semibold text-2xl text-[#f59e0b]">{data.low_stock_count}</p>
            </button>
            <button
              type="button"
              onClick={() => setFilter(filter === 'zero' ? 'todos' : 'zero')}
              className={'text-left bg-bg-elevated border rounded-lg p-4 transition-colors cursor-pointer ' + (filter === 'zero' ? 'border-danger' : 'border-border hover:border-danger/50')}
            >
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5 mb-1.5"><AlertTriangle size={12} className="text-danger" />Stock zero</p>
              <p className="font-display font-semibold text-2xl text-danger">{data.zero_stock_count}</p>
            </button>
            <div className="bg-bg-elevated border border-border rounded-lg p-4">
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5 mb-1.5"><Wallet size={12} />Valor em stock (custo)</p>
              <p className="font-display font-semibold text-2xl text-text-primary">{formatMoney(data.total_cost_value)}</p>
            </div>
            <div className="bg-bg-elevated border border-border rounded-lg p-4">
              <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide flex items-center gap-1.5 mb-1.5"><Wallet size={12} />Valor em stock (venda)</p>
              <p className="font-display font-semibold text-2xl text-text-primary">{formatMoney(data.total_sale_value)}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 mb-4 flex-wrap">
            <div className="relative max-w-sm w-full sm:w-auto sm:min-w-[260px]">
              <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Pesquisar produto..."
                className="w-full bg-bg-inset border border-border rounded-md pl-10 pr-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
              />
            </div>
            <div className="w-full sm:w-64">
              <Select
                value={periodId || 'atual'}
                onChange={(v) => setPeriodId(v === 'atual' ? '' : v)}
                options={[{ value: 'atual', label: 'Stock atual' }, ...periods.map((p) => ({ value: p.id, label: 'Fim de ' + p.label }))]}
              />
            </div>
            {filter !== 'todos' && (
              <button type="button" onClick={() => setFilter('todos')} className="text-[13px] text-text-muted hover:text-text-primary underline transition-colors cursor-pointer">
                Limpar filtro
              </button>
            )}
          </div>

          <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
            {items.length === 0 ? (
              <p className="text-text-muted text-[13px] text-center py-16">Nenhum produto encontrado</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Código</th>
                      <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Nome</th>
                      <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Stock total</th>
                      <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Equivalência</th>
                      <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Limite mínimo</th>
                      <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Valor (custo)</th>
                      <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Valor (venda)</th>
                      <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <tr key={item.product_id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                        <td className="px-6 py-3.5 font-mono text-text-muted">{item.code}</td>
                        <td className="px-6 py-3.5 font-display font-medium text-text-primary">
                          {item.name}
                          {item.is_raw_material && <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-text-muted bg-bg-inset px-1.5 py-0.5 rounded">MP</span>}
                        </td>
                        <td className="px-6 py-3.5 text-right font-mono text-text-primary">{formatQty(item.total_quantity)} <span className="text-text-muted text-[11px]">{item.unit_code}</span></td>
                        <td className="px-6 py-3.5"><UnitBreakdown quantity={item.total_quantity} baseCode={item.unit_code} units={item.sale_units} /></td>
                        <td className="px-6 py-3.5 text-right font-mono text-text-muted">{formatQty(item.min_stock_threshold)}</td>
                        <td className="px-6 py-3.5 text-right font-mono text-text-muted">{formatMoney(item.cost_value)}</td>
                        <td className="px-6 py-3.5 text-right font-mono text-text-muted">{formatMoney(item.sale_value)}</td>
                        <td className="px-6 py-3.5">
                          {item.is_zero ? (
                            <span className="text-[11px] font-semibold uppercase tracking-wide text-danger bg-danger/10 px-2 py-1 rounded">Zero</span>
                          ) : item.is_low ? (
                            <span className="text-[11px] font-semibold uppercase tracking-wide text-[#f59e0b] bg-[#f59e0b]/10 px-2 py-1 rounded">Baixo</span>
                          ) : (
                            <span className="text-[11px] font-semibold uppercase tracking-wide text-success bg-success/10 px-2 py-1 rounded">OK</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </main>
  );
}

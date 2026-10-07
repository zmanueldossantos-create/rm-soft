import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { History, Loader2, Search, ArrowDownToLine, ArrowUpFromLine, SlidersHorizontal, ClipboardList, ArrowRightLeft, Trash2, Factory, Plus } from 'lucide-react';
import { listStockMovements, getMovementPeriods, listWarehouses } from '../api/stock';
import PeriodFilter from '../components/PeriodFilter';
import { listProducts } from '../api/products';
import { extractErrorMessage } from '../utils/errors';

const MOVEMENT_STYLE = {
  RECEPCAO: { icon: ArrowDownToLine, color: 'text-success', bg: 'bg-success/10', label: 'Receção' },
  SAIDA: { icon: ArrowUpFromLine, color: 'text-danger', bg: 'bg-danger/10', label: 'Saída' },
  AJUSTE: { icon: SlidersHorizontal, color: 'text-accent', bg: 'bg-accent/10', label: 'Ajuste' },
  INVENTARIO: { icon: ClipboardList, color: 'text-text-muted', bg: 'bg-text-muted/10', label: 'Inventário' },
  TRANSFERENCIA: { icon: ArrowRightLeft, color: 'text-text-muted', bg: 'bg-text-muted/10', label: 'Transferência' },
  PERDA: { icon: Trash2, color: 'text-danger', bg: 'bg-danger/10', label: 'Perda' },
  PRODUCAO: { icon: Factory, color: 'text-accent', bg: 'bg-accent/10', label: 'Produção' },
};

const LOSS_CATEGORY_LABEL = {
  EXPIRACAO: 'Expiração',
  QUEBRA: 'Quebra',
  ROUBO: 'Roubo',
  OUTRO: 'Outro',
};

function formatQty(value) {
  return value % 1 === 0 ? String(value) : String(value).replace('.', ',');
}

function formatDateTime(iso) {
  return new Date(iso).toLocaleString('pt-AO', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

// Pairs up the two TRANSFERENCIA rows created by a single transfer (same
// product, quantity, reason, and timestamp - see stock_service.transfer_stock)
// into one displayable row showing "Source -> Destination".
// Each TRANSFERENCIA row now explicitly carries is_transfer_source and
// counterpart_warehouse_id (see StockMovement model) - no more guessing
// direction from row order, which is unreliable since both legs of a
// transfer share the exact same created_at timestamp.
function groupTransfers(movements) {
  return movements
    .filter((m) => m.movement_type !== 'TRANSFERENCIA' || m.is_transfer_source === true)
    .map((m) => {
      if (m.movement_type === 'TRANSFERENCIA' && m.is_transfer_source) {
        return { ...m, _transferFrom: m.warehouse_id, _transferTo: m.counterpart_warehouse_id };
      }
      return m;
    });
}

export default function StockMovements() {
  const navigate = useNavigate();
  const [movements, setMovements] = useState([]);
  const [products, setProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  const [periods, setPeriods] = useState([]);
  const [filters, setFilters] = useState({ year: '', month: '', dateFrom: '', dateTo: '' });
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const PAGE_SIZE = 50;

  async function loadMovementsPage(currentFilters, currentOffset, append) {
    const data = await listStockMovements({
      year: currentFilters.year || undefined,
      month: currentFilters.month || undefined,
      dateFrom: currentFilters.dateFrom || undefined,
      dateTo: currentFilters.dateTo || undefined,
      limit: PAGE_SIZE,
      offset: currentOffset,
    });
    setMovements((prev) => (append ? [...prev, ...data] : data));
    setHasMore(data.length === PAGE_SIZE);
  }

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      const [periodsData, productsData, warehousesData] = await Promise.all([getMovementPeriods(), listProducts(), listWarehouses()]);
      setPeriods(periodsData);
      const initialFilters = periodsData.length > 0
        ? { year: String(periodsData[0].year), month: '', dateFrom: '', dateTo: '' }
        : { year: '', month: '', dateFrom: '', dateTo: '' };
      setFilters(initialFilters);
      setOffset(0);
      await loadMovementsPage(initialFilters, 0, false);
      setProducts(productsData);
      setWarehouses(warehousesData);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar movimentos de stock'));
    } finally {
      setLoading(false);
    }
  }

  async function handleFilterChange(newFilters) {
    setFilters(newFilters);
    setOffset(0);
    setLoading(true);
    try {
      await loadMovementsPage(newFilters, 0, false);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar movimentos de stock'));
    } finally {
      setLoading(false);
    }
  }

  async function handleLoadMore() {
    const nextOffset = offset + PAGE_SIZE;
    setLoadingMore(true);
    try {
      await loadMovementsPage(filters, nextOffset, true);
      setOffset(nextOffset);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar mais movimentos'));
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const productById = useMemo(() => {
    const map = {};
    products.forEach((p) => { map[p.id] = p; });
    return map;
  }, [products]);

  const warehouseById = useMemo(() => {
    const map = {};
    warehouses.forEach((w) => { map[w.id] = w; });
    return map;
  }, [warehouses]);

  const groupedMovements = useMemo(() => groupTransfers(movements), [movements]);

  const filteredMovements = useMemo(() => {
    if (!search.trim()) return groupedMovements;
    const q = search.toLowerCase();
    return groupedMovements.filter((m) => {
      const product = productById[m.product_id];
      return (
        (product?.name || '').toLowerCase().includes(q) ||
        (product?.code || '').toLowerCase().includes(q) ||
        (m.reference || '').toLowerCase().includes(q) ||
        (m.reason || '').toLowerCase().includes(q)
      );
    });
  }, [groupedMovements, productById, search]);

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <History size={22} className="text-accent" />
        Histórico de Movimentos
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Rasto completo de todas as entradas, saídas, transferências e perdas de stock
      </p>

      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <div className="relative max-w-sm w-full sm:w-auto sm:min-w-[240px]">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Pesquisar por produto, referência ou motivo..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
          />
        </div>
        <PeriodFilter periods={periods} onChange={handleFilterChange} />
      </div>

      <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
        {loading && (
          <div className="flex items-center justify-center py-16 text-text-muted text-sm">
            <Loader2 size={18} className="animate-spin mr-2" />
            A carregar...
          </div>
        )}

        {error && (
          <div className="px-6 py-4 text-danger text-sm bg-danger/10">{error}</div>
        )}

        {!loading && !error && filteredMovements.length === 0 && (
          <div className="text-center py-16 text-text-muted text-sm">
            <span className="flex flex-col items-center gap-3">
              {search ? 'Nenhum movimento encontrado' : 'Nenhum movimento de stock registado ainda'}
              <Search size={22} className="text-text-muted/40 mt-1" />
            </span>
          </div>
        )}

        {!loading && !error && filteredMovements.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[760px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Tipo</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Armazém</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Produto</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Quantidade</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Motivo / Referência</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Data</th>
                </tr>
              </thead>
              <tbody>
                {filteredMovements.map((m) => {
                  const style = MOVEMENT_STYLE[m.movement_type] || MOVEMENT_STYLE.AJUSTE;
                  const Icon = style.icon;
                  const product = productById[m.product_id];
                  const isOutgoing = m.movement_type === 'SAIDA' || m.movement_type === 'PERDA' || (m.movement_type === 'AJUSTE' && m.quantity < 0) || (m.movement_type === 'PRODUCAO' && m.is_production_output === false);
                  const isTransfer = m.movement_type === 'TRANSFERENCIA' && m.is_transfer_source;

                  let reasonCell = m.reason || m.reference || '-';
                  if (m.movement_type === 'PERDA' && m.loss_category) {
                    reasonCell = LOSS_CATEGORY_LABEL[m.loss_category] + (m.reason ? ' - ' + m.reason : '');
                  }

                  return (
                    <tr key={m.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                      <td className="px-6 py-4">
                        <span className={'inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded ' + style.bg + ' ' + style.color}>
                          <Icon size={12} />
                          {style.label}
                        </span>
                      </td>
                      <td className="px-6 py-4 font-mono text-text-muted text-[13px]">
                        {isTransfer
                          ? (warehouseById[m._transferFrom]?.name || '-') + ' → ' + (warehouseById[m._transferTo]?.name || '-')
                          : (warehouseById[m.warehouse_id]?.name || '-')}
                      </td>
                      <td className="px-6 py-4 font-display font-medium text-text-primary">
                        {product ? product.name : m.product_id}
                      </td>
                      <td className={'px-6 py-4 font-mono text-right ' + (isOutgoing ? 'text-danger' : 'text-success')}>
                        {isOutgoing ? '-' : '+'}{formatQty(Math.abs(m.quantity))}
                      </td>
                      <td className="px-6 py-4 font-mono text-text-muted text-[13px]">
                        {reasonCell}
                      </td>
                      <td className="px-6 py-4 font-mono text-text-muted text-[13px]">
                        {formatDateTime(m.created_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {!loading && !error && movements.length > 0 && hasMore && (
          <div className="flex justify-center py-4 border-t border-border">
            <button
              onClick={handleLoadMore}
              disabled={loadingMore}
              className="flex items-center gap-2 text-accent hover:text-accent-hover font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50"
            >
              {loadingMore && <Loader2 size={14} className="animate-spin" />}
              {loadingMore ? 'A carregar...' : 'Carregar mais'}
            </button>
          </div>
        )}
      </div>
    </main>
  );
}

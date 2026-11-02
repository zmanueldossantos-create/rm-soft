import { formatKz } from '../utils/format';
import { qtyWithUnit as formatQtyUnit } from '../utils/stockUnits';
import DateInput from '../components/DateInput';
import { useState, useEffect } from 'react';
import { ClipboardList, Loader2 } from 'lucide-react';
import Select from '../components/Select';
import { getProductionHistory } from '../api/stock';
import { listFiscalYears, listFiscalPeriods } from '../api/fiscal';
import { extractErrorMessage } from '../utils/errors';

const MONTH_NAMES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const TODAY = new Date().toISOString().slice(0, 10);

// a quantity followed by its unit (and the everyday unit below 1 KG / 1 L): 5 KG, 0,05 KG (50 g), 100 UN
function qtyWithUnit(entry) {
  return formatQtyUnit(entry.quantity, entry.unit_code);
}

export default function ProductionHistory() {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [fiscalYears, setFiscalYears] = useState([]);
  const [fiscalPeriods, setFiscalPeriods] = useState([]);
  const [yearId, setYearId] = useState('');
  const [month, setMonth] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Load real fiscal years - current (open) + closed previous ones - instead of a
  // guessed "last 3 years" list.
  useEffect(() => {
    listFiscalYears()
      .then((years) => {
        setFiscalYears(years);
        const current = years.find((y) => y.is_open) || years[0];
        if (current) setYearId(current.id);
      })
      .catch(() => setFiscalYears([]));
  }, []);

  // Load real periods (months) for the selected fiscal year - current (open) + closed ones.
  useEffect(() => {
    if (!yearId) {
      setFiscalPeriods([]);
      return;
    }
    setMonth('');
    listFiscalPeriods(yearId)
      .then(setFiscalPeriods)
      .catch(() => setFiscalPeriods([]));
  }, [yearId]);

  const selectedYear = fiscalYears.find((y) => y.id === yearId);

  async function loadHistory() {
    setLoading(true);
    setError('');
    try {
      const data = await getProductionHistory({
        year: selectedYear?.year || '',
        month,
        dateFrom,
        dateTo,
      });
      setBatches(data);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar o resumo de produção'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [yearId, month, dateFrom, dateTo]);

  function clearFilters() {
    const current = fiscalYears.find((y) => y.is_open) || fiscalYears[0];
    setYearId(current?.id || '');
    setMonth('');
    setDateFrom('');
    setDateTo('');
  }

  const yearOptions = fiscalYears.map((y) => ({ value: y.id, label: String(y.year) + (y.is_open ? ' (atual)' : ' (fechado)') }));
  const monthOptions = fiscalPeriods.map((p) => ({ value: String(p.month), label: MONTH_NAMES[p.month - 1] + (p.is_open ? ' (atual)' : ' (fechado)') }));

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <ClipboardList size={22} className="text-accent" />
        Resumo de Produção
      </h2>
      <p className="text-text-muted text-sm mb-6">Histórico de lotes produzidos e matérias-primas consumidas</p>

      <div className="bg-bg-elevated border border-border rounded-lg p-4 mb-5 flex flex-wrap items-end gap-3">
        <div className="w-40">
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Ano</label>
          <Select value={yearId} onChange={setYearId} options={yearOptions} placeholder="Selecionar" />
        </div>
        <div className="w-44">
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Período</label>
          <Select value={month} onChange={setMonth} options={monthOptions} placeholder="Todos" />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Intervalo - de</label>
          <DateInput value={dateFrom} max={dateTo || TODAY} onChange={(e) => setDateFrom(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">até</label>
          <DateInput value={dateTo} min={dateFrom || undefined} max={TODAY} onChange={(e) => setDateTo(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
        </div>
        <button type="button" onClick={clearFilters} className="text-[13px] text-text-muted hover:text-text-primary underline transition-colors cursor-pointer">
          Limpar filtros
        </button>
      </div>

      <div className={batches.length > 0 && !loading && !error ? '' : 'bg-bg-elevated border border-border rounded-lg overflow-hidden'}>
        {loading && (
          <div className="flex items-center justify-center py-16 text-text-muted text-sm">
            <Loader2 size={18} className="animate-spin mr-2" />
            A carregar...
          </div>
        )}
        {error && (
          <div className="px-6 py-4 text-danger text-sm bg-danger/10">{error}</div>
        )}
        {!loading && !error && batches.length === 0 && (
          <p className="text-text-muted text-[13px] text-center py-16">Nenhuma produção encontrada para este filtro</p>
        )}
        {!loading && !error && batches.length > 0 && <BatchList batches={batches} />}
      </div>
    </main>
  );
}


// The batches of the filter: a few totals, then one card per production - what was made, where and when, a table of
// what it consumed (quantity, average cost, cost) and its cost per unit.
function BatchList({ batches }) {
  const kz = (v) => formatKz(v) + ' Kz';
  const costed = batches.filter((b) => b.output && b.output.unit_cost != null);
  const totalCost = costed.reduce((t, b) => t + b.output.unit_cost * b.output.quantity, 0);
  const th = 'text-[10.5px] uppercase tracking-wide text-text-muted font-medium px-3 py-2';
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {[['Produções', String(batches.length)], ['Custo total das produções', kz(totalCost)],
          ['Produtos diferentes', String(new Set(batches.map((b) => b.output?.product_code)).size)]].map(([label, value]) => (
          <div key={label} className="bg-bg-elevated border border-border rounded-lg px-4 py-3">
            <p className="text-[11px] uppercase tracking-wide text-text-muted">{label}</p>
            <p className="font-mono text-[18px] text-text-primary mt-1">{value}</p>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {batches.map((batch, idx) => {
          const out = batch.output;
          return (
            <div key={idx} className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
              <div className="px-4 py-3 border-b border-border flex items-start justify-between gap-3 flex-wrap">
                <div>
                  <p className="font-display font-semibold text-text-primary text-[15px] flex items-center gap-2 flex-wrap">
                    {out ? out.product_name : 'Produção'}
                    {out && <span className="font-mono text-[12px] font-semibold text-accent bg-accent/10 px-2 py-0.5 rounded">+{qtyWithUnit(out)}</span>}
                  </p>
                  <p className="text-[12px] text-text-muted mt-0.5">{batch.warehouse_name}</p>
                </div>
                <p className="text-[12px] text-text-muted font-mono">{new Date(batch.created_at).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</p>
              </div>
              <table className="w-full text-[13px]">
                <thead><tr className="border-b border-border bg-bg-inset/40">
                  <th className={th + ' text-left'}>Consumiu</th><th className={th + ' text-right'}>Quantidade</th>
                  <th className={th + ' text-right'}>Custo médio</th><th className={th + ' text-right'}>Custo</th>
                </tr></thead>
                <tbody>
                  {batch.ingredients.map((i, k) => (
                    <tr key={k} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 text-text-primary">{i.product_name}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{qtyWithUnit(i)}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-muted whitespace-nowrap">{i.unit_cost == null ? '-' : kz(i.unit_cost) + '/' + (i.unit_code || 'un')}</td>
                      <td className="px-3 py-2 text-right font-mono text-text-primary whitespace-nowrap">{i.unit_cost == null ? '-' : kz(i.unit_cost * i.quantity)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {out && (out.unit_cost != null ? (
                <div className="px-4 py-2.5 border-t border-border bg-bg-inset/40 flex items-center justify-between gap-3 flex-wrap font-mono text-[13px]">
                  <span className="text-text-muted">Custo total <strong className="text-text-primary">{kz(out.unit_cost * out.quantity)}</strong></span>
                  <span className="text-text-muted">Custo por {out.unit_code || 'un'} <strong className="text-accent text-[14px]">{kz(out.unit_cost)}</strong></span>
                </div>
              ) : (
                <p className="px-4 py-2.5 border-t border-border text-[12px] text-amber-500">Custo incompleto (um ingrediente sem custo)</p>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

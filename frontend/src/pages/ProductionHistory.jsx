import { useState, useEffect } from 'react';
import { ClipboardList, Loader2 } from 'lucide-react';
import Select from '../components/Select';
import { getProductionHistory } from '../api/stock';
import { listFiscalYears, listFiscalPeriods } from '../api/fiscal';
import { extractErrorMessage } from '../utils/errors';

const MONTH_NAMES = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const TODAY = new Date().toISOString().slice(0, 10);

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
          <input type="date" value={dateFrom} max={dateTo || TODAY} onChange={(e) => setDateFrom(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">até</label>
          <input type="date" value={dateTo} min={dateFrom || undefined} max={TODAY} onChange={(e) => setDateTo(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
        </div>
        <button type="button" onClick={clearFilters} className="text-[13px] text-text-muted hover:text-text-primary underline transition-colors cursor-pointer">
          Limpar filtros
        </button>
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
        {!loading && !error && batches.length === 0 && (
          <p className="text-text-muted text-[13px] text-center py-16">Nenhuma produção encontrada para este filtro</p>
        )}
        {!loading && !error && batches.length > 0 && (
          <div className="divide-y divide-border">
            {batches.map((batch, idx) => (
              <div key={idx} className="px-6 py-4">
                <div className="flex items-center justify-between mb-1.5 flex-wrap gap-1">
                  <p className="font-display font-medium text-text-primary">
                    {batch.output ? batch.output.quantity + ' × ' + batch.output.product_name : 'Produção'}
                  </p>
                  <p className="text-[12px] text-text-muted">{new Date(batch.created_at).toLocaleString('pt-AO')}</p>
                </div>
                <p className="text-[12px] text-text-muted">{batch.warehouse_name}</p>
                <p className="text-[12px] text-text-muted mt-1">
                  Consumiu: {batch.ingredients.map((i) => i.quantity + ' ' + i.product_name).join(', ')}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

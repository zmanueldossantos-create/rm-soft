import { useState, useMemo, useEffect } from 'react';
import { Calendar, X } from 'lucide-react';
import Select from './Select';

const MONTH_LABELS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];

// Renders Ano/Mes selects (populated only with periods that actually have
// data - see available-periods backend endpoints) plus an optional custom
// date-range mode. Calls onChange({ year, month, dateFrom, dateTo }) - the
// caller decides how to refetch; this component only manages the filter UI.
export default function PeriodFilter({ periods, onChange }) {
  const [mode, setMode] = useState('period'); // 'period' | 'range'
  const [year, setYear] = useState('');
  const [month, setMonth] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const todayStr = new Date().toISOString().slice(0, 10);

  const years = useMemo(() => {
    const unique = [...new Set(periods.map((p) => p.year))].sort((a, b) => b - a);
    return unique;
  }, [periods]);

  const monthsForYear = useMemo(() => {
    if (!year) return [];
    return periods.filter((p) => p.year === parseInt(year)).map((p) => p.month).sort((a, b) => a - b);
  }, [periods, year]);

  // Default to the most recent year available once periods load, and
  // within that year, the most recent month with data (naturally the
  // current month whenever this month already has activity).
  useEffect(() => {
    if (years.length > 0 && !year) {
      const defaultYear = years[0];
      const monthsInYear = periods.filter((p) => p.year === defaultYear).map((p) => p.month);
      const defaultMonth = monthsInYear.length > 0 ? Math.max(...monthsInYear) : '';
      setYear(String(defaultYear));
      setMonth(defaultMonth ? String(defaultMonth) : '');
      onChange({ year: String(defaultYear), month: defaultMonth ? String(defaultMonth) : '', dateFrom: '', dateTo: '' });
    }
  }, [years]);

  function emitChange(next) {
    if (mode === 'period') {
      onChange({ year: next.year ?? year, month: next.month ?? month, dateFrom: '', dateTo: '' });
    } else {
      onChange({ year: '', month: '', dateFrom: next.dateFrom ?? dateFrom, dateTo: next.dateTo ?? dateTo });
    }
  }

  function handleYearChange(v) {
    setYear(v);
    setMonth('');
    emitChange({ year: v, month: '' });
  }

  function handleMonthChange(v) {
    setMonth(v);
    emitChange({ month: v });
  }

  function handleModeToggle(newMode) {
    setMode(newMode);
    if (newMode === 'period') {
      setDateFrom('');
      setDateTo('');
      onChange({ year, month, dateFrom: '', dateTo: '' });
    } else {
      setYear('');
      setMonth('');
      onChange({ year: '', month: '', dateFrom, dateTo });
    }
  }

  function handleDateFromChange(v) {
    setDateFrom(v);
    emitChange({ dateFrom: v });
  }

  function handleDateToChange(v) {
    setDateTo(v);
    emitChange({ dateTo: v });
  }

  function clearAll() {
    if (mode === 'period') {
      const defaultYear = years[0] ? String(years[0]) : '';
      setYear(defaultYear);
      setMonth('');
      onChange({ year: defaultYear, month: '', dateFrom: '', dateTo: '' });
    } else {
      setDateFrom('');
      setDateTo('');
      onChange({ year: '', month: '', dateFrom: '', dateTo: '' });
    }
  }

  const hasActiveFilter = mode === 'range' ? (dateFrom || dateTo) : (month !== '');

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center bg-bg-elevated border border-border rounded-md p-0.5">
        <button
          type="button"
          onClick={() => handleModeToggle('period')}
          className={'px-3 py-1.5 rounded text-[12px] font-medium transition-colors cursor-pointer ' + (mode === 'period' ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}
        >
          Por período
        </button>
        <button
          type="button"
          onClick={() => handleModeToggle('range')}
          className={'px-3 py-1.5 rounded text-[12px] font-medium transition-colors cursor-pointer ' + (mode === 'range' ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}
        >
          Intervalo
        </button>
      </div>

      {mode === 'period' ? (
        <>
          <div className="w-28">
            <Select
              value={year}
              onChange={handleYearChange}
              options={years.map((y) => ({ value: String(y), label: String(y) }))}
              placeholder="Ano"
            />
          </div>
          <div className="w-40">
            <Select
              value={month}
              onChange={handleMonthChange}
              options={[{ value: '', label: 'Todos' }, ...monthsForYear.map((m) => ({ value: String(m), label: MONTH_LABELS[m - 1] }))]}
              placeholder="Mês"
            />
          </div>
        </>
      ) : (
        <>
          <div className="flex items-center gap-1.5">
            <Calendar size={14} className="text-text-muted" />
            <input
              type="date"
              value={dateFrom}
              max={dateTo || todayStr}
              onChange={(e) => handleDateFromChange(e.target.value)}
              className="bg-bg-elevated border border-border rounded-md px-2.5 py-2 text-[12px] text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          <span className="text-text-muted text-[12px]">até</span>
          <input
            type="date"
            value={dateTo}
            min={dateFrom || undefined}
            max={todayStr}
            disabled={!dateFrom}
            onChange={(e) => handleDateToChange(e.target.value)}
            className="bg-bg-elevated border border-border rounded-md px-2.5 py-2 text-[12px] text-text-primary font-mono outline-none focus:border-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </>
      )}

      {hasActiveFilter && (
        <button
          type="button"
          onClick={clearAll}
          aria-label="Limpar filtro"
          className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger hover:border-danger transition-colors cursor-pointer"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
}

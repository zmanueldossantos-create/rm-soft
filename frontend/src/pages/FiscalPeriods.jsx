import { useState, useEffect } from 'react';
import { Calendar, CalendarDays, Plus, Loader2, Lock, LockOpen, CheckCircle2, Minus, X } from 'lucide-react';
import ConfirmDialog from '../components/ConfirmDialog';
import {
  getNextFiscalYear,
  listFiscalYears,
  createFiscalYear,
  closeFiscalYear,
  getNextFiscalMonth,
  listFiscalPeriods,
  createFiscalPeriod,
  closeFiscalPeriod,
} from '../api/fiscal';
import { extractErrorMessage } from '../utils/errors';

const MONTH_ABBR = ['', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
const MONTH_NAMES = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

function formatDateFull(d) {
  if (!d) return '-';
  return new Date(d).toLocaleString('pt-AO', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function PeriodCell({ period, month, isSkipped }) {
  const isOpen = period && period.is_open;
  const isClosed = period && !period.is_open;

  return (
    <div className={
      'relative rounded-lg border p-2.5 transition-all flex flex-col gap-1 ' +
      (isOpen ? 'border-success/40 bg-success/5' : isClosed ? 'border-border bg-bg-inset/40' : isSkipped ? 'border-border/30 bg-bg-primary/10' : 'border-border/50 bg-bg-primary/30')
    }>
      <div className="flex items-center justify-between">
        <span className={'text-sm font-bold ' + (isOpen ? 'text-success' : period ? 'text-text-primary' : isSkipped ? 'text-text-muted/50' : 'text-text-muted')}>
          {MONTH_ABBR[month]}
        </span>
        {isOpen && <span className="w-2 h-2 rounded-full bg-success animate-pulse" />}
        {isClosed && <CheckCircle2 size={13} className="text-text-muted" />}
        {!period && isSkipped && <X size={12} className="text-text-muted/40" />}
        {!period && !isSkipped && <Minus size={12} className="text-text-muted/40" />}
      </div>
    </div>
  );
}

export default function FiscalPeriods() {
  const [years, setYears] = useState([]);
  const [nextYear, setNextYear] = useState(null);
  const [activeYear, setActiveYear] = useState(null);
  const [periods, setPeriods] = useState([]);
  const [nextMonth, setNextMonth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);

  async function loadAll() {
    setLoading(true);
    setError('');
    try {
      const [yearsData, nextYearData] = await Promise.all([listFiscalYears(), getNextFiscalYear()]);
      setYears(yearsData);
      setNextYear(nextYearData.next_year);

      const open = yearsData.find((y) => y.is_open) || yearsData[0] || null;
      setActiveYear(open);

      if (open) {
        const [periodsData, nextMonthData] = await Promise.all([
          listFiscalPeriods(open.id),
          getNextFiscalMonth(open.id),
        ]);
        setPeriods(periodsData);
        setNextMonth(nextMonthData.next_month);
      } else {
        setPeriods([]);
        setNextMonth(null);
      }
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar dados fiscais'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function handleCreateYear() {
    setBusy(true);
    try {
      await createFiscalYear();
      await loadAll();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao abrir ano fiscal'));
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  async function handleCloseYear() {
    setBusy(true);
    try {
      await closeFiscalYear(activeYear.id);
      await loadAll();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao fechar ano fiscal'));
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  async function handleOpenMonth() {
    setBusy(true);
    try {
      await createFiscalPeriod(activeYear.id);
      await loadAll();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao abrir período'));
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  async function handleCloseMonth() {
    setBusy(true);
    try {
      await closeFiscalPeriod(currentOpenPeriod.id);
      await loadAll();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao fechar período'));
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  const openCount = periods.filter((p) => p.is_open).length;
  const closedCount = periods.filter((p) => !p.is_open).length;
  const monthsTouched = periods.map((p) => p.month);
  const currentRealMonth = new Date().getMonth() + 1;
  const startMonth = monthsTouched.length
    ? Math.min(...monthsTouched)
    : (activeYear && activeYear.year === new Date().getFullYear() ? currentRealMonth : 1);
  const lastMonthTouched = monthsTouched.length ? Math.max(...monthsTouched) : startMonth - 1;
  const skippedCount = startMonth - 1;
  const pendingCount = 12 - lastMonthTouched;
  const currentOpenPeriod = periods.find((p) => p.is_open);
  const nextMonthName = nextMonth ? MONTH_NAMES[nextMonth - 1] : null;
  const canOpenYear = nextYear !== null;
  const canCloseYear = activeYear?.is_open && !currentOpenPeriod && periods.length > 0;
  const canOpenMonth = activeYear?.is_open && !currentOpenPeriod && nextMonth !== null;
  const canCloseMonth = !!currentOpenPeriod;

  if (loading) {
    return (
      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
        <div className="flex justify-center items-center h-64">
          <Loader2 size={24} className="animate-spin text-accent" />
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="mb-6">
        <h1 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
          <Calendar size={22} className="text-accent" />
          Períodos Fiscais
        </h1>
        <p className="text-text-muted text-sm mt-0.5">
          Gestão de anos fiscais e períodos mensais
        </p>
      </div>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-sm rounded-r mb-5">
          {error}
        </div>
      )}

      {!activeYear && (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed border-border rounded-lg">
          <Calendar size={40} className="text-text-muted mb-4" />
          <h2 className="font-display font-semibold text-text-primary mb-1.5">Nenhum ano fiscal ativo</h2>
          <p className="text-text-muted text-sm mb-6">
            Crie o ano fiscal {nextYear} para começar a gerir os períodos.
          </p>
          <button
            onClick={() => setConfirmAction('open-year')}
            className="flex items-center gap-2 px-6 py-3 rounded-md bg-accent hover:bg-accent-hover text-white font-semibold text-sm transition-colors cursor-pointer"
          >
            <Plus size={17} /> Abrir ano fiscal {nextYear}
          </button>
        </div>
      )}

      {activeYear && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 items-stretch">
          <div className="lg:col-span-1">
            <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden flex flex-col h-full">
              <div className="bg-gradient-to-br from-bg-inset to-bg-primary px-6 py-5 border-b border-border">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-text-muted text-[11px] font-semibold uppercase tracking-widest">Ano Fiscal</span>
                  <span className={'text-[11px] font-bold px-2.5 py-0.5 rounded-full ' + (activeYear.is_open ? 'bg-success/15 text-success' : 'bg-text-muted/15 text-text-muted')}>
                    {activeYear.is_open ? 'Aberto' : 'Fechado'}
                  </span>
                </div>
                <h2 className="font-display font-bold text-5xl text-text-primary mt-1">{activeYear.year}</h2>
                <p className="text-text-muted text-xs mt-2">Criado em {formatDateFull(activeYear.created_at)}</p>
              </div>

              <div className="px-6 py-4 grid grid-cols-4 gap-1.5">
                <div className="text-center p-2 rounded-md bg-bg-inset/50">
                  <p className="text-lg font-bold text-success">{openCount}</p>
                  <p className="text-[9px] text-text-muted font-medium mt-0.5">Abertos</p>
                </div>
                <div className="text-center p-2 rounded-md bg-bg-inset/50">
                  <p className="text-lg font-bold text-text-primary">{closedCount}</p>
                  <p className="text-[9px] text-text-muted font-medium mt-0.5">Fechados</p>
                </div>
                <div className="text-center p-2 rounded-md bg-bg-inset/50">
                  <p className="text-lg font-bold text-text-primary">{pendingCount}</p>
                  <p className="text-[9px] text-text-muted font-medium mt-0.5">Por abrir</p>
                </div>
                <div className="text-center p-2 rounded-md bg-bg-inset/50">
                  <p className="text-lg font-bold text-text-muted">{skippedCount}</p>
                  <p className="text-[9px] text-text-muted font-medium mt-0.5">Não aplicável</p>
                </div>
              </div>

              <div className="px-6 flex-1">
                <div className={'h-[80px] p-3 rounded-md border transition-all ' + (currentOpenPeriod ? 'bg-success/5 border-success/30' : 'bg-bg-inset/40 border-border')}>
                  {currentOpenPeriod ? (
                    <>
                      <p className="text-[11px] text-success font-semibold uppercase tracking-wide mb-1">Período ativo</p>
                      <p className="font-display font-bold text-text-primary text-sm">{MONTH_NAMES[currentOpenPeriod.month - 1]} {activeYear.year}</p>
                    </>
                  ) : (
                    <div className="h-full flex items-center">
                      <p className="text-xs text-text-muted">Nenhum período ativo</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="px-6 pb-5 mt-4 space-y-2 border-t border-border pt-4">
                <button
                  onClick={() => setConfirmAction('open-year')}
                  disabled={!canOpenYear || busy}
                  title={!canOpenYear ? 'Feche o ano atual primeiro' : ''}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-md bg-bg-inset hover:bg-border/40 disabled:opacity-40 disabled:cursor-not-allowed text-text-primary text-sm font-medium transition-colors cursor-pointer border border-border"
                >
                  <Plus size={15} /> Abrir ano {nextYear ?? ''}
                </button>
                <button
                  onClick={() => setConfirmAction('close-year')}
                  disabled={!canCloseYear || busy}
                  title={!canCloseYear ? 'Feche todos os períodos primeiro' : ''}
                  className={
                    'w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-md border text-sm font-medium transition-colors ' +
                    (canCloseYear ? 'bg-danger/10 border-danger/30 text-danger hover:bg-danger/15 cursor-pointer' : 'bg-bg-inset/40 border-border text-text-muted cursor-not-allowed opacity-50')
                  }
                >
                  <Lock size={15} /> Fechar ano {activeYear.year}
                </button>
              </div>
            </div>
          </div>

          <div className="lg:col-span-2">
            <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden flex flex-col h-full">
              <div className="flex items-center justify-between px-5 py-4 border-b border-border">
                <div className="flex items-center gap-2">
                  <CalendarDays size={18} className="text-text-muted" />
                  <h3 className="font-display font-semibold text-text-primary text-base">Calendário {activeYear.year}</h3>
                </div>
                <div className="hidden sm:flex items-center gap-3 text-[11px] text-text-muted">
                  <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-success animate-pulse" />Aberto</span>
                  <span className="flex items-center gap-1.5"><CheckCircle2 size={11} className="text-text-muted" />Fechado</span>
                  <span className="flex items-center gap-1.5"><Minus size={11} className="text-text-muted/40" />Por abrir</span>
                  <span className="flex items-center gap-1.5"><X size={11} className="text-text-muted/40" />Não aplicável</span>
                </div>
              </div>

              <div className="p-5 grid grid-cols-3 sm:grid-cols-4 gap-2.5 flex-1">
                {Array.from({ length: 12 }, (_, idx) => idx + 1).map((month) => (
                  <PeriodCell
                    key={month}
                    month={month}
                    period={periods.find((p) => p.month === month)}
                    isSkipped={month < startMonth}
                  />
                ))}
              </div>

              <div className="border-t border-border px-5 py-4">
                <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-3">Ações do período</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => setConfirmAction('open-month')}
                    disabled={!canOpenMonth || busy}
                    title={!canOpenMonth ? (currentOpenPeriod ? 'Feche o período atual primeiro' : 'Nenhum período seguinte disponível') : ''}
                    className={
                      'flex items-center gap-2 px-4 py-2 rounded-md border text-sm font-medium transition-colors ' +
                      (canOpenMonth ? 'bg-success/10 border-success/30 text-success hover:bg-success/15 cursor-pointer' : 'bg-bg-inset/40 border-border text-text-muted cursor-not-allowed opacity-50')
                    }
                  >
                    <LockOpen size={14} /> Abrir {canOpenMonth ? nextMonthName : 'período'}
                  </button>
                  <button
                    onClick={() => setConfirmAction('close-month')}
                    disabled={!canCloseMonth || busy}
                    title={!canCloseMonth ? 'Nenhum período ativo para fechar' : ''}
                    className={
                      'flex items-center gap-2 px-4 py-2 rounded-md border text-sm font-medium transition-colors ' +
                      (canCloseMonth ? 'bg-danger/10 border-danger/30 text-danger hover:bg-danger/15 cursor-pointer' : 'bg-bg-inset/40 border-border text-text-muted cursor-not-allowed opacity-50')
                    }
                  >
                    <Lock size={14} /> Fechar {canCloseMonth ? MONTH_NAMES[currentOpenPeriod.month - 1] : 'período'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmAction === 'open-year'}
        title="Abrir ano fiscal"
        message={'Abrir o ano fiscal ' + nextYear + '?'}
        confirmLabel="Abrir ano"
        onConfirm={handleCreateYear}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'close-year'}
        title="Fechar ano fiscal"
        message={activeYear ? 'Tem a certeza que deseja fechar o ano ' + activeYear.year + '? Esta ação bloqueia novas operações datadas neste ano.' : ''}
        confirmLabel="Fechar ano"
        danger
        onConfirm={handleCloseYear}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'open-month'}
        title="Abrir período"
        message={activeYear ? 'Abrir o período de ' + nextMonthName + ' ' + activeYear.year + '?' : ''}
        confirmLabel="Abrir período"
        onConfirm={handleOpenMonth}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'close-month'}
        title="Fechar período"
        message={currentOpenPeriod ? 'Tem a certeza que deseja fechar ' + MONTH_NAMES[currentOpenPeriod.month - 1] + '? Novas operações datadas neste mês serão bloqueadas.' : ''}
        confirmLabel="Fechar período"
        danger
        onConfirm={handleCloseMonth}
        onCancel={() => setConfirmAction(null)}
      />
    </main>
  );
}

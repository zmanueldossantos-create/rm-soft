import { useState, useEffect } from 'react';
import { Calendar, CalendarDays, Plus, Loader2, Lock, LockOpen, CheckCircle2, Minus, X, Hourglass } from 'lucide-react';
import ConfirmDialog from '../components/ConfirmDialog';
import {
  getNextFiscalYear,
  listFiscalYears,
  createFiscalYear,
  closeFiscalYear,
  partialCloseFiscalYear,
  getNextFiscalMonth,
  listFiscalPeriods,
  createFiscalPeriod,
  closeFiscalPeriod,
  partialCloseFiscalPeriod,
} from '../api/fiscal';
import { extractErrorMessage } from '../utils/errors';

const MONTH_ABBR = ['', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];
const MONTH_NAMES = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

// Three states (see fiscal_period_service): ABERTO = the active one (every operation); FECHO_PARCIAL = soft-closed
// (internal late entries only: reception, transfer, loss, adjustment...); FECHADO = final, never reopened.
const STATUS_LABEL = { ABERTO: 'Aberto', FECHO_PARCIAL: 'Fecho parcial', FECHADO: 'Fechado' };
const STATUS_BADGE = {
  ABERTO: 'bg-success/15 text-success',
  FECHO_PARCIAL: 'bg-amber-500/15 text-amber-500',
  FECHADO: 'bg-text-muted/15 text-text-muted',
};

function formatDateFull(d) {
  if (!d) return '-';
  return new Date(d).toLocaleString('pt-AO', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function PeriodCell({ period, month, isSkipped }) {
  const status = period?.status;
  const box = status === 'ABERTO' ? 'border-success/40 bg-success/5'
    : status === 'FECHO_PARCIAL' ? 'border-amber-500/40 bg-amber-500/5'
    : status === 'FECHADO' ? 'border-border bg-bg-inset/40'
    : isSkipped ? 'border-border/30 bg-bg-primary/10' : 'border-border/50 bg-bg-primary/30';
  const text = status === 'ABERTO' ? 'text-success'
    : status === 'FECHO_PARCIAL' ? 'text-amber-500'
    : period ? 'text-text-primary' : isSkipped ? 'text-text-muted/50' : 'text-text-muted';
  return (
    <div className={'relative rounded-lg border p-2.5 transition-all flex flex-col gap-1 ' + box}>
      <div className="flex items-center justify-between">
        <span className={'text-sm font-bold ' + text}>{MONTH_ABBR[month]}</span>
        {status === 'ABERTO' && <span className="w-2 h-2 rounded-full bg-success animate-pulse" />}
        {status === 'FECHO_PARCIAL' && <Hourglass size={12} className="text-amber-500" />}
        {status === 'FECHADO' && <CheckCircle2 size={13} className="text-text-muted" />}
        {!period && isSkipped && <X size={12} className="text-text-muted/40" />}
        {!period && !isSkipped && <Minus size={12} className="text-text-muted/40" />}
      </div>
      {status === 'FECHO_PARCIAL' && <span className="text-[10px] text-amber-500 leading-tight">Fecho parcial</span>}
    </div>
  );
}

function ActionButton({ enabled, busy, onClick, title, tone, icon, children }) {
  const tones = {
    success: 'bg-success/10 border-success/30 text-success hover:bg-success/15',
    warning: 'bg-amber-500/10 border-amber-500/30 text-amber-500 hover:bg-amber-500/15',
    danger: 'bg-danger/10 border-danger/30 text-danger hover:bg-danger/15',
    neutral: 'bg-bg-inset border-border text-text-primary hover:bg-border/40',
  };
  return (
    <button
      onClick={onClick}
      disabled={!enabled || busy}
      title={enabled ? '' : title}
      className={'flex items-center justify-center gap-2 px-4 py-2 rounded-md border text-sm font-medium transition-colors '
        + (enabled ? tones[tone] + ' cursor-pointer' : 'bg-bg-inset/40 border-border text-text-muted cursor-not-allowed opacity-50')}
    >
      {icon}{children}
    </button>
  );
}

export default function FiscalPeriods() {
  const [years, setYears] = useState([]);
  const [nextYear, setNextYear] = useState(null);
  const [selectedYearId, setSelectedYearId] = useState(null);
  const [periods, setPeriods] = useState([]);
  const [nextMonth, setNextMonth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);

  async function loadYear(year) {
    if (!year) {
      setPeriods([]);
      setNextMonth(null);
      return;
    }
    const [periodsData, nextMonthData] = await Promise.all([listFiscalPeriods(year.id), getNextFiscalMonth(year.id)]);
    setPeriods(periodsData);
    setNextMonth(nextMonthData.next_month);
  }

  // Shown year: the one kept on screen, else the ABERTO one, else the soft-closed one, else the latest.
  async function loadAll(keepYearId = null) {
    setLoading(true);
    setError('');
    try {
      const [yearsData, nextYearData] = await Promise.all([listFiscalYears(), getNextFiscalYear()]);
      setYears(yearsData);
      setNextYear(nextYearData.next_year);
      const chosen = yearsData.find((y) => y.id === keepYearId)
        || yearsData.find((y) => y.status === 'ABERTO')
        || yearsData.find((y) => y.status === 'FECHO_PARCIAL')
        || yearsData[0] || null;
      setSelectedYearId(chosen ? chosen.id : null);
      await loadYear(chosen);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar dados fiscais'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function selectYear(year) {
    setSelectedYearId(year.id);
    setError('');
    try {
      await loadYear(year);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar os periodos'));
    }
  }

  async function run(action, fallback) {
    setBusy(true);
    try {
      await action();
      await loadAll(selectedYearId);
    } catch (err) {
      setError(extractErrorMessage(err, fallback));
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  const activeYear = years.find((y) => y.id === selectedYearId) || null;
  const yearStatus = activeYear?.status;
  const openPeriod = periods.find((p) => p.status === 'ABERTO');
  const partialPeriod = periods.find((p) => p.status === 'FECHO_PARCIAL');
  const finalTarget = partialPeriod || openPeriod; // a final close goes to the soft-closed month first
  const countOf = (status) => periods.filter((p) => p.status === status).length;
  const monthName = (p) => (p ? MONTH_NAMES[p.month - 1] : '');

  const monthsTouched = periods.map((p) => p.month);
  const currentRealMonth = new Date().getMonth() + 1;
  const startMonth = monthsTouched.length
    ? Math.min(...monthsTouched)
    : (activeYear && activeYear.year === new Date().getFullYear() ? currentRealMonth : 1);
  const lastMonthTouched = monthsTouched.length ? Math.max(...monthsTouched) : startMonth - 1;
  const pendingCount = 12 - lastMonthTouched;
  const nextMonthName = nextMonth ? MONTH_NAMES[nextMonth - 1] : null;

  const canOpenYear = nextYear !== null;
  // A year is soft-closed only to move on to the next one: once December is no longer ABERTO (server rule too).
  const canPartialCloseYear = yearStatus === 'ABERTO' && !openPeriod && periods.some((p) => p.month === 12 && p.status !== 'ABERTO');
  const canCloseYear = !!activeYear && yearStatus !== 'FECHADO' && periods.length > 0 && periods.every((p) => p.status === 'FECHADO');
  const canOpenMonth = yearStatus === 'ABERTO' && !openPeriod && nextMonth !== null;
  const canPartialCloseMonth = !!openPeriod && !partialPeriod;
  const canCloseMonth = !!finalTarget;

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
      <div className="mb-6 flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
            <Calendar size={22} className="text-accent" />
            Períodos Fiscais
          </h1>
          <p className="text-text-muted text-sm mt-0.5">Gestão de anos fiscais e períodos mensais</p>
        </div>
        {years.length > 1 && (
          <div className="flex gap-1.5 flex-wrap">
            {years.map((y) => (
              <button
                key={y.id}
                onClick={() => selectYear(y)}
                className={'flex items-center gap-2 px-3 py-1.5 rounded-md border text-sm transition-colors cursor-pointer '
                  + (y.id === selectedYearId ? 'border-accent bg-accent/5 text-text-primary' : 'border-border text-text-muted hover:border-accent')}
              >
                <span className="font-semibold">{y.year}</span>
                <span className={'text-[10px] font-bold px-1.5 py-0.5 rounded-full ' + STATUS_BADGE[y.status]}>{STATUS_LABEL[y.status]}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-sm rounded-r mb-5">{error}</div>
      )}

      {!activeYear && (
        <div className="flex flex-col items-center justify-center py-16 border border-dashed border-border rounded-lg">
          <Calendar size={40} className="text-text-muted mb-4" />
          <h2 className="font-display font-semibold text-text-primary mb-1.5">Nenhum ano fiscal ativo</h2>
          <p className="text-text-muted text-sm mb-6">Crie o ano fiscal {nextYear} para começar a gerir os períodos.</p>
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
                  <span className={'text-[11px] font-bold px-2.5 py-0.5 rounded-full ' + STATUS_BADGE[yearStatus]}>{STATUS_LABEL[yearStatus]}</span>
                </div>
                <h2 className="font-display font-bold text-5xl text-text-primary mt-1">{activeYear.year}</h2>
                <p className="text-text-muted text-xs mt-2">Criado em {formatDateFull(activeYear.created_at)}</p>
              </div>

              <div className="px-6 py-4 grid grid-cols-4 gap-1.5">
                {[['ABERTO', 'Abertos', 'text-success'], ['FECHO_PARCIAL', 'Parciais', 'text-amber-500'], ['FECHADO', 'Fechados', 'text-text-primary']].map(([status, label, color]) => (
                  <div key={status} className="text-center p-2 rounded-md bg-bg-inset/50">
                    <p className={'text-lg font-bold ' + color}>{countOf(status)}</p>
                    <p className="text-[9px] text-text-muted font-medium mt-0.5">{label}</p>
                  </div>
                ))}
                <div className="text-center p-2 rounded-md bg-bg-inset/50">
                  <p className="text-lg font-bold text-text-muted">{pendingCount}</p>
                  <p className="text-[9px] text-text-muted font-medium mt-0.5">Por abrir</p>
                </div>
              </div>

              <div className="px-6 flex-1 flex flex-col gap-2">
                <div className={'p-3 rounded-md border ' + (openPeriod ? 'bg-success/5 border-success/30' : 'bg-bg-inset/40 border-border')}>
                  {openPeriod ? (
                    <>
                      <p className="text-[11px] text-success font-semibold uppercase tracking-wide mb-1">Período ativo</p>
                      <p className="font-display font-bold text-text-primary text-sm">{monthName(openPeriod)} {activeYear.year}</p>
                    </>
                  ) : (
                    <p className="text-xs text-text-muted">Nenhum período ativo neste ano</p>
                  )}
                </div>
                {partialPeriod && (
                  <div className="p-3 rounded-md border bg-amber-500/5 border-amber-500/30 cursor-help" title="Só lançamentos internos tardios (entradas de stock, transferências, perdas, ajustes).">
                    <p className="text-[11px] text-amber-500 font-semibold uppercase tracking-wide mb-1">Fecho parcial</p>
                    <p className="font-display font-bold text-text-primary text-sm">{monthName(partialPeriod)} {activeYear.year}</p>
                  </div>
                )}
              </div>

              <div className="px-6 pb-5 mt-4 flex flex-col gap-2 border-t border-border pt-4">
                <ActionButton enabled={canOpenYear} busy={busy} onClick={() => setConfirmAction('open-year')} title="Feche o ano atual (parcial ou definitivamente) primeiro" tone="neutral" icon={<Plus size={15} />}>
                  Abrir ano {nextYear ?? ''}
                </ActionButton>
                <ActionButton enabled={canPartialCloseYear} busy={busy} onClick={() => setConfirmAction('partial-year')} title="Só depois de Dezembro: feche parcialmente Dezembro primeiro" tone="warning" icon={<Hourglass size={15} />}>
                  Fechar parcialmente {activeYear.year}
                </ActionButton>
                <ActionButton enabled={canCloseYear} busy={busy} onClick={() => setConfirmAction('close-year')} title="Feche definitivamente todos os períodos primeiro" tone="danger" icon={<Lock size={15} />}>
                  Fechar definitivamente {activeYear.year}
                </ActionButton>
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
                  <span className="flex items-center gap-1.5"><Hourglass size={11} className="text-amber-500" />Fecho parcial</span>
                  <span className="flex items-center gap-1.5"><CheckCircle2 size={11} className="text-text-muted" />Fechado</span>
                  <span className="flex items-center gap-1.5"><Minus size={11} className="text-text-muted/40" />Por abrir</span>
                  <span className="flex items-center gap-1.5"><X size={11} className="text-text-muted/40" />Não aplicável</span>
                </div>
              </div>

              <div className="p-5 grid grid-cols-3 sm:grid-cols-4 gap-2.5 flex-1">
                {Array.from({ length: 12 }, (_, idx) => idx + 1).map((month) => (
                  <PeriodCell key={month} month={month} period={periods.find((p) => p.month === month)} isSkipped={month < startMonth} />
                ))}
              </div>

              <div className="border-t border-border px-5 py-4">
                <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-3">Ações do período</p>
                <div className="flex flex-wrap gap-2">
                  <ActionButton enabled={canOpenMonth} busy={busy} onClick={() => setConfirmAction('open-month')} title={openPeriod ? 'Feche (parcial ou definitivamente) o período ativo primeiro' : 'Nenhum período seguinte disponível'} tone="success" icon={<LockOpen size={14} />}>
                    Abrir {canOpenMonth ? nextMonthName : 'período'}
                  </ActionButton>
                  <ActionButton enabled={canPartialCloseMonth} busy={busy} onClick={() => setConfirmAction('partial-month')} title={partialPeriod ? 'Feche definitivamente ' + monthName(partialPeriod) + ' primeiro' : 'Nenhum período ativo'} tone="warning" icon={<Hourglass size={14} />}>
                    Fechar parcialmente {openPeriod ? monthName(openPeriod) : 'período'}
                  </ActionButton>
                  <ActionButton enabled={canCloseMonth} busy={busy} onClick={() => setConfirmAction('close-month')} title="Nenhum período para fechar" tone="danger" icon={<Lock size={14} />}>
                    Fechar definitivamente {finalTarget ? monthName(finalTarget) : 'período'}
                  </ActionButton>
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
        onConfirm={() => run(createFiscalYear, 'Erro ao abrir ano fiscal')}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'partial-year'}
        title="Fechar parcialmente o ano"
        message={activeYear ? 'Fechar parcialmente o ano ' + activeYear.year + '? Permite abrir o ano seguinte. Os lançamentos internos tardios continuam possíveis no mês em fecho parcial até ao fecho definitivo.' : ''}
        confirmLabel="Fechar parcialmente"
        onConfirm={() => run(() => partialCloseFiscalYear(activeYear.id), 'Erro ao fechar parcialmente o ano')}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'close-year'}
        title="Fechar definitivamente o ano"
        message={activeYear ? 'Fechar definitivamente o ano ' + activeYear.year + '? Nenhuma operação poderá voltar a ser lançada neste ano. Esta ação não pode ser desfeita.' : ''}
        confirmLabel="Fechar definitivamente"
        danger
        onConfirm={() => run(() => closeFiscalYear(activeYear.id), 'Erro ao fechar ano fiscal')}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'open-month'}
        title="Abrir período"
        message={activeYear ? 'Abrir o período de ' + nextMonthName + ' ' + activeYear.year + '? Passa a ser o período ativo (vendas, faturas, caixas).' : ''}
        confirmLabel="Abrir período"
        onConfirm={() => run(() => createFiscalPeriod(activeYear.id), 'Erro ao abrir período')}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'partial-month'}
        title="Fechar parcialmente o período"
        message={openPeriod ? 'Fechar parcialmente ' + monthName(openPeriod) + '? Vendas, faturas e caixas deixam de ser possíveis neste mês. Os lançamentos internos tardios (entradas de stock, transferências, perdas, ajustes) continuam possíveis até ao fecho definitivo. Depois, abra o mês seguinte.' : ''}
        confirmLabel="Fechar parcialmente"
        onConfirm={() => run(() => partialCloseFiscalPeriod(openPeriod.id), 'Erro ao fechar parcialmente o período')}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmDialog
        open={confirmAction === 'close-month'}
        title="Fechar definitivamente o período"
        message={finalTarget ? 'Fechar definitivamente ' + monthName(finalTarget) + '? Nenhuma operação poderá voltar a ser lançada neste mês. Esta ação não pode ser desfeita.' : ''}
        confirmLabel="Fechar definitivamente"
        danger
        onConfirm={() => run(() => closeFiscalPeriod(finalTarget.id), 'Erro ao fechar período')}
        onCancel={() => setConfirmAction(null)}
      />
    </main>
  );
}

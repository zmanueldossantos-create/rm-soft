import { formatKz } from '../utils/format';
import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import DateInput from '../components/DateInput';
import Select from '../components/Select';
import { History, Loader2 } from 'lucide-react';
import { listActivities } from '../api/activity';
import { listResources, getResourceHistory } from '../api/booking';
import { extractErrorMessage } from '../utils/errors';

// The history of the resources (resource_history_service): every use of a room, a table or a practitioner over a
// period - a stay, a passage, a marcação, a reservation, a table's account - with its document and what it brought in
// (documents minus credit notes), and a summary per resource. Cancellations and no-shows are listed apart.
const KIND_LABELS = { ESTADIA: 'Estadia', PASSAGEM: 'Passagem', MARCACAO: 'Marcação', RESERVA: 'Reserva', CONTA: 'Conta' };
const STATUS_LABELS = {
  PENDENTE: 'Pendente', CONFIRMADA: 'Confirmada', EM_CURSO: 'Em curso', CONCLUIDA: 'Concluída',
  CANCELADA: 'Cancelada', NO_SHOW: 'Não compareceu',
};
const STATUS_COLORS = {
  PENDENTE: 'text-accent bg-accent/10', CONFIRMADA: 'text-success bg-success/10', EM_CURSO: 'text-accent bg-accent/10',
  CONCLUIDA: 'text-text-muted bg-bg-inset', CANCELADA: 'text-danger bg-danger/10', NO_SHOW: 'text-danger bg-danger/10',
};
const NOT_A_USE = ['CANCELADA', 'NO_SHOW'];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function monthStartIso() {
  return todayIso().slice(0, 8) + '01';
}

function formatMinutes(minutes) {
  if (!minutes) return '-';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? h + ' h ' + String(m).padStart(2, '0') + ' min' : m + ' min';
}

function formatDate(iso) {
  if (!iso) return '-';
  return new Date(iso).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Luanda' });
}

const inputCls = 'bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';

export default function HistoricoRecursos() {
  const [searchParams] = useSearchParams();  // ?activity=...&resource=... from the Histórico button of Recursos
  const [activities, setActivities] = useState([]);
  const [selectedActivityId, setSelectedActivityId] = useState(searchParams.get('activity') || '');
  const [resources, setResources] = useState([]);
  const [resourceId, setResourceId] = useState(searchParams.get('resource') || '');
  const [dateFrom, setDateFrom] = useState(monthStartIso());
  const [dateTo, setDateTo] = useState(todayIso());
  const [showNotUses, setShowNotUses] = useState(true);
  const [history, setHistory] = useState({ entries: [], summary: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    listActivities().then((data) => {
      const active = data.filter((a) => a.is_active);
      setActivities(active);
      if (!selectedActivityId && active.length === 1) setSelectedActivityId(active[0].id);
      else if (!selectedActivityId) setLoading(false);
    }).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar atividades')));
  }, []);

  useEffect(() => {
    if (!selectedActivityId) return;
    listResources(selectedActivityId).then(setResources).catch(() => setResources([]));
  }, [selectedActivityId]);

  useEffect(() => {
    if (!selectedActivityId) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    const filters = { activityId: selectedActivityId };
    if (resourceId) filters.resourceId = resourceId;
    if (dateFrom) filters.dateFrom = dateFrom + 'T00:00:00';
    if (dateTo) filters.dateTo = dateTo + 'T23:59:59';
    getResourceHistory(filters)
      .then((data) => { if (!cancelled) setHistory(data); })
      .catch((err) => { if (!cancelled) setError(extractErrorMessage(err, 'Erro ao carregar o histórico')); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [selectedActivityId, resourceId, dateFrom, dateTo]);

  function chooseActivity(id) {
    setSelectedActivityId(id);
    setResourceId('');
  }

  function handleDateFromChange(value) {
    setDateFrom(value);
    setDateTo((prevTo) => (prevTo && prevTo < value ? value : prevTo));
  }

  // the hotel's columns (real departure, overstay) only where the activity has the hotel stay
  const capabilities = activities.find((a) => a.id === selectedActivityId)?.capabilities || [];
  const hasStay = capabilities.includes('HOTEL_STAY');
  const entries = showNotUses ? history.entries : history.entries.filter((e) => !NOT_A_USE.includes(e.status));
  const summary = history.summary.filter((s) => !resourceId || s.resource_id === resourceId);
  const totals = summary.reduce((t, s) => ({
    uses: t.uses + s.uses, occupied: t.occupied + s.occupied_minutes, revenue: t.revenue + s.revenue,
    cancelled: t.cancelled + s.cancelled, noShow: t.noShow + s.no_show, planned: t.planned + s.planned,
  }), { uses: 0, occupied: 0, revenue: 0, cancelled: 0, noShow: 0, planned: 0 });

  const th = 'px-4 py-2.5';
  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <History size={22} className="text-accent" />
        Histórico dos recursos
      </h2>
      <p className="text-text-muted text-sm mb-6">Cada utilização dos quartos, mesas e praticantes, com o documento e a receita (documentos menos notas de crédito)</p>

      {activities.length > 1 && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          {activities.map((a) => (
            <button
              key={a.id}
              onClick={() => chooseActivity(a.id)}
              className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (selectedActivityId === a.id ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
            >
              {a.name}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2.5 mb-5 flex-wrap">
        <div className="w-56">
          <label className={labelCls}>Recurso</label>
          <Select value={resourceId} onChange={setResourceId} options={[{ value: '', label: 'Todos os recursos' }, ...resources.map((r) => ({ value: r.id, label: r.name }))]} placeholder="Todos os recursos" />
        </div>
        <div>
          <label className={labelCls}>De</label>
          <DateInput value={dateFrom} onChange={(e) => handleDateFromChange(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>Até</label>
          <DateInput value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} className={inputCls} />
        </div>
        <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer select-none pb-2.5">
          <input type="checkbox" checked={showNotUses} onChange={(e) => setShowNotUses(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
          Mostrar canceladas e ausências
        </label>
      </div>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {!selectedActivityId ? (
        <p className="text-text-muted text-[13px]">Selecione uma atividade</p>
      ) : loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : (
        <>
          <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto mb-5">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
                  <th className={th + ' text-left'}>Recurso</th>
                  <th className={th + ' text-right'}>Utilizações</th>
                  <th className={th + ' text-right'}>Tempo ocupado</th>
                  <th className={th + ' text-right'} title="Reservas pendentes ou confirmadas - ainda não são utilizações">Previstas</th>
                  <th className={th + ' text-right'}>Canceladas</th>
                  <th className={th + ' text-right'}>Não compareceu</th>
                  <th className={th + ' text-right'}>Receita</th>
                </tr>
              </thead>
              <tbody>
                {summary.map((s) => (
                  <tr key={s.resource_id} className="border-b border-border last:border-0">
                    <td className={th + ' text-text-primary font-medium'}>{s.resource_name}</td>
                    <td className={th + ' text-right font-mono'}>{s.uses}</td>
                    <td className={th + ' text-right font-mono text-text-muted'}>{formatMinutes(s.occupied_minutes)}</td>
                    <td className={th + ' text-right font-mono text-text-muted'}>{s.planned}</td>
                    <td className={th + ' text-right font-mono ' + (s.cancelled ? 'text-danger' : 'text-text-muted')}>{s.cancelled}</td>
                    <td className={th + ' text-right font-mono ' + (s.no_show ? 'text-danger' : 'text-text-muted')}>{s.no_show}</td>
                    <td className={th + ' text-right font-mono text-text-primary font-semibold'}>{formatKz(s.revenue)} Kz</td>
                  </tr>
                ))}
              </tbody>
              {summary.length > 1 && (
                <tfoot>
                  <tr className="border-t border-border bg-bg-inset font-semibold">
                    <td className={th + ' text-text-primary'}>Total</td>
                    <td className={th + ' text-right font-mono'}>{totals.uses}</td>
                    <td className={th + ' text-right font-mono'}>{formatMinutes(totals.occupied)}</td>
                    <td className={th + ' text-right font-mono'}>{totals.planned}</td>
                    <td className={th + ' text-right font-mono'}>{totals.cancelled}</td>
                    <td className={th + ' text-right font-mono'}>{totals.noShow}</td>
                    <td className={th + ' text-right font-mono text-accent'}>{formatKz(totals.revenue)} Kz</td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>

          {entries.length === 0 ? (
            <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
              <History size={28} className="text-text-muted mx-auto mb-3" />
              <p className="text-text-primary font-medium mb-1">Nenhuma utilização neste período</p>
            </div>
          ) : (
            <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
                    <th className={th + ' text-left'}>Recurso</th>
                    <th className={th + ' text-left'}>Tipo</th>
                    <th className={th + ' text-left'}>Cliente</th>
                    <th className={th + ' text-left'}>Início</th>
                    <th className={th + ' text-left'}>Fim</th>
                    {hasStay && <th className={th + ' text-left'}>Saída real</th>}
                    {hasStay && <th className={th + ' text-left'}>Excedido</th>}
                    <th className={th + ' text-left'}>Estado</th>
                    <th className={th + ' text-left'}>Documento</th>
                    <th className={th + ' text-right'}>Receita</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <tr key={(e.booking_id || e.account_id)} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                      <td className={th + ' text-text-primary font-medium'}>{e.resource_name}</td>
                      <td className={th + ' text-text-muted'}>{KIND_LABELS[e.kind] || e.kind}</td>
                      <td className={th + ' text-text-muted'}>{[e.guest_name, e.customer_name].filter(Boolean).join(' - ') || '-'}{e.party_size ? ' (' + e.party_size + ' pax)' : ''}</td>
                      <td className={th + ' font-mono text-[12px] text-text-muted'}>{formatDate(e.starts_at)}</td>
                      <td className={th + ' font-mono text-[12px] text-text-muted'}>{formatDate(e.ends_at)}</td>
                      {hasStay && <td className={th + ' font-mono text-[12px] text-text-muted'}>{e.kind === 'CONTA' ? '-' : formatDate(e.real_end_at)}</td>}
                      {hasStay && <td className={th + ' font-mono text-[12px] ' + (e.overstay_minutes > 0 ? 'text-danger font-semibold' : 'text-text-muted')}>{formatMinutes(e.overstay_minutes)}</td>}
                      <td className={th}>
                        <span className={'text-[11px] font-semibold px-2.5 py-1 rounded-full whitespace-nowrap ' + (STATUS_COLORS[e.status] || '')}>{STATUS_LABELS[e.status] || e.status}</span>
                      </td>
                      <td className={th + ' font-mono text-[12px] text-text-muted'}>
                        {e.invoice_label || '-'}
                        {e.credited > 0 && <span className="block text-danger text-[11px]">NC - {formatKz(e.credited)} Kz</span>}
                      </td>
                      <td className={th + ' text-right font-mono text-text-primary font-semibold'}>{e.invoice_total != null ? formatKz(e.revenue) + ' Kz' : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </main>
  );
}

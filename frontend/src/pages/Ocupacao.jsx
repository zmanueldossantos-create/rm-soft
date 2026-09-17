import { useState, useEffect } from 'react';
import { History, Loader2 } from 'lucide-react';
import { listActivities } from '../api/activity';
import { getOccupancyHistory } from '../api/hotel';
import { extractErrorMessage } from '../utils/errors';

const STATUS_LABELS = { EM_CURSO: 'Em curso', CONCLUIDA: 'Concluida' };
const STATUS_COLORS = { EM_CURSO: 'text-accent bg-accent/10', CONCLUIDA: 'text-text-muted bg-bg-inset' };

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function formatKz(v) {
  return Number(v || 0).toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDate(iso) {
  return new Date(iso).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Luanda' });
}

export default function Ocupacao() {
  const [activities, setActivities] = useState([]);
  const [selectedActivityId, setSelectedActivityId] = useState('');
  const [dateFrom, setDateFrom] = useState(todayIso());
  const [dateTo, setDateTo] = useState(todayIso());
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    listActivities().then((data) => {
      const active = data.filter((a) => a.is_active);
      setActivities(active);
      if (active.length > 0) setSelectedActivityId(active[0].id);
    }).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar atividades')));
  }, []);

  useEffect(() => {
    if (!selectedActivityId) return;
    loadHistory();
  }, [selectedActivityId, dateFrom, dateTo]);

  async function loadHistory() {
    setLoading(true);
    setError('');
    try {
      const filters = { activityId: selectedActivityId };
      if (dateFrom) filters.dateFrom = dateFrom + 'T00:00:00';
      if (dateTo) filters.dateTo = dateTo + 'T23:59:59';
      setEntries(await getOccupancyHistory(filters));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar historico'));
    } finally {
      setLoading(false);
    }
  }

  function handleDateFromChange(value) {
    // Same auto-bump pattern as the booking form (Reservas.jsx) - if "De" moves
    // past the current "Ate", pull "Ate" forward with it instead of leaving an
    // impossible from > to combination silently in place.
    setDateFrom(value);
    setDateTo((prevTo) => (prevTo && prevTo < value ? value : prevTo));
  }

  const totalFaturado = entries.reduce((sum, e) => sum + (e.invoice_total || 0), 0);

  const revenueByRoom = Object.values(
    entries.reduce((acc, e) => {
      if (!acc[e.resource_name]) acc[e.resource_name] = { resource_name: e.resource_name, total: 0, stays: 0 };
      acc[e.resource_name].total += e.invoice_total || 0;
      acc[e.resource_name].stays += 1;
      return acc;
    }, {})
  ).sort((a, b) => b.total - a.total);

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <History size={22} className="text-accent" />
        Ocupação
      </h2>
      <p className="text-text-muted text-sm mb-6">Histórico de estadias - reservas com check-in efetuado ou já concluídas</p>

      {activities.length > 1 && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          {activities.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelectedActivityId(a.id)}
              className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (selectedActivityId === a.id ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
            >
              {a.name}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2.5 mb-5 flex-wrap">
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">De</label>
          <input type="date" value={dateFrom} onChange={(e) => handleDateFromChange(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Até</label>
          <input type="date" value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
        </div>
        {entries.length > 0 && (
          <div className="ml-auto bg-bg-elevated border border-border rounded-md px-4 py-2.5">
            <p className="text-[10px] text-text-muted uppercase tracking-wide">Total faturado</p>
            <p className="font-mono text-accent font-semibold text-sm">{formatKz(totalFaturado)} Kz</p>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : entries.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <History size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium mb-1">Nenhuma estadia neste período</p>
        </div>
      ) : (
        <>
          {revenueByRoom.length > 1 && (
            <div className="bg-bg-elevated border border-border rounded-lg p-4 mb-5">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-3">Faturação por quarto</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                {revenueByRoom.map((r) => (
                  <div key={r.resource_name} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5">
                    <p className="text-text-primary font-medium text-sm truncate">{r.resource_name}</p>
                    <p className="text-text-muted text-[11px] mt-0.5">{r.stays} estadia{r.stays !== 1 ? 's' : ''}</p>
                    <p className="font-mono text-accent font-semibold text-sm mt-1">{formatKz(r.total)} Kz</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
                  <th className="text-left px-4 py-2.5">Quarto</th>
                  <th className="text-left px-4 py-2.5">Hóspede</th>
                  <th className="text-left px-4 py-2.5">Entrada</th>
                  <th className="text-left px-4 py-2.5">Saída</th>
                  <th className="text-left px-4 py-2.5">Estado</th>
                  <th className="text-left px-4 py-2.5">Fatura</th>
                  <th className="text-right px-4 py-2.5">Total</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.booking_id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                    <td className="px-4 py-2.5 text-text-primary font-medium">{e.resource_name}</td>
                    <td className="px-4 py-2.5 text-text-muted">{e.customer_name || '-'}</td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-text-muted">{formatDate(e.starts_at)}</td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-text-muted">{formatDate(e.ends_at)}</td>
                    <td className="px-4 py-2.5">
                      <span className={'text-[11px] font-semibold px-2.5 py-1 rounded-full ' + (STATUS_COLORS[e.status] || '')}>{STATUS_LABELS[e.status] || e.status}</span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-text-muted">
                      {e.invoice_series ? e.invoice_series + '/' + e.invoice_number : '-'}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-text-primary font-semibold">
                      {e.invoice_total != null ? formatKz(e.invoice_total) + ' Kz' : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </main>
  );
}

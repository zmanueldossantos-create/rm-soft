import { useEffect, useState } from 'react';
import { History, Loader2, ChevronDown, ChevronRight } from 'lucide-react';
import { extractErrorMessage } from '../utils/errors';
import { getKitchenHistory } from '../api/kitchen';

// Kitchen history (point 34d): the orders of a period, and for every dish who started it, who made it ready,
// who cancelled it and why, and how long it took. Quick periods rather than date fields: the kitchen mostly
// looks at today, yesterday or the week.
const STATUS_LABEL = { NAO_ENVIADO: 'Nao enviado', EM_ESPERA: 'Em espera', EM_PREPARACAO: 'Em preparacao', PRONTO: 'Pronto', ANULADO: 'Anulado' };
const STATUS_STYLE = {
  EM_ESPERA: 'text-sky-400 bg-sky-400/10',
  EM_PREPARACAO: 'text-amber-500 bg-amber-500/10',
  PRONTO: 'text-success bg-success/10',
  ANULADO: 'text-danger bg-danger/10',
};
const PERIODS = [
  { key: 'today', label: 'Hoje', from: 0, to: 0 },
  { key: 'yesterday', label: 'Ontem', from: 1, to: 1 },
  { key: 'week', label: '7 dias', from: 6, to: 0 },
  { key: 'month', label: '30 dias', from: 29, to: 0 },
];

function isoDay(daysAgo) {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function formatTime(value) {
  return value ? new Date(value).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' }) : '-';
}
function formatDay(value) {
  return new Date(value).toLocaleDateString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric' });
}
function formatMinutes(m) {
  return m === null || m === undefined ? '-' : Math.round(m) + ' min';
}
function formatQty(q) {
  const n = Number(q);
  return Number.isInteger(n) ? String(n) : n.toLocaleString('pt-PT', { maximumFractionDigits: 3 });
}

export default function KitchenHistory() {
  const [period, setPeriod] = useState('today');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activityFilter, setActivityFilter] = useState('');
  const [onlyCancelled, setOnlyCancelled] = useState(false);
  const [open, setOpen] = useState({});

  useEffect(() => {
    const p = PERIODS.find((x) => x.key === period);
    setLoading(true);
    setError('');
    getKitchenHistory(isoDay(p.from), isoDay(p.to))
      .then((d) => { setData(d); setOpen({}); })
      .catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar o historico')))
      .finally(() => setLoading(false));
  }, [period]);

  const orders = (data?.orders || [])
    .filter((o) => !activityFilter || o.activity_name === activityFilter)
    .filter((o) => !onlyCancelled || o.cancelled > 0);
  const activities = [...new Set((data?.orders || []).map((o) => o.activity_name))];
  const chip = (active) => 'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer '
    + (active ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary');
  const s = data?.summary;

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <History size={22} className="text-accent" />
        Historico da cozinha
      </h2>
      <p className="text-text-muted text-sm mb-6">Pedidos enviados, quem fez o que em cada prato e quanto tempo demorou</p>

      <div className="flex items-center gap-2 mb-3 flex-wrap">
        {PERIODS.map((p) => (
          <button key={p.key} type="button" onClick={() => setPeriod(p.key)} className={chip(period === p.key)}>{p.label}</button>
        ))}
        <span className="w-px h-5 bg-border mx-1" />
        <button type="button" onClick={() => setOnlyCancelled((v) => !v)} className={chip(onlyCancelled)}>Com anulados</button>
      </div>
      {activities.length > 1 && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <button type="button" onClick={() => setActivityFilter('')} className={chip(!activityFilter)}>Todas</button>
          {activities.map((a) => (
            <button key={a} type="button" onClick={() => setActivityFilter(a)} className={chip(activityFilter === a)}>{a}</button>
          ))}
        </div>
      )}

      {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>}

      {s && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          {[
            ['Pedidos', s.orders],
            ['Pratos servidos', s.served],
            ['Pratos anulados', s.cancelled + (s.sold_out ? ' (' + s.sold_out + ' esgotado' + (s.sold_out > 1 ? 's' : '') + ')' : '')],
            ['Tempo medio ate pronto', formatMinutes(s.average_wait_minutes)],
          ].map(([label, value]) => (
            <div key={label} className="bg-bg-elevated border border-border rounded-lg p-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1">{label}</p>
              <p className="font-mono font-semibold text-text-primary text-[18px]">{value}</p>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : orders.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <History size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium mb-1">Nenhum pedido neste periodo</p>
        </div>
      ) : (
        <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
          {orders.map((o) => (
            <div key={o.id} className="border-b border-border last:border-b-0">
              <button
                type="button"
                onClick={() => setOpen((p) => ({ ...p, [o.id]: !p[o.id] }))}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-bg-inset transition-colors cursor-pointer"
              >
                {open[o.id] ? <ChevronDown size={15} className="text-text-muted shrink-0" /> : <ChevronRight size={15} className="text-text-muted shrink-0" />}
                <span className="font-semibold text-text-primary text-[13px] w-40 truncate">#{o.number} - {o.account_label}</span>
                <span className="text-text-muted text-[12px] font-mono w-36 shrink-0">{formatDay(o.sent_at)} {formatTime(o.sent_at)}</span>
                <span className="text-text-muted text-[12px] flex-1 truncate">{activities.length > 1 ? o.activity_name + ' - ' : ''}{o.sent_by_name}</span>
                <span className="text-text-primary text-[12px] font-mono shrink-0">{o.dishes} prato(s)</span>
                {o.cancelled > 0 && <span className="text-danger text-[12px] font-mono shrink-0">{o.cancelled} anulado(s)</span>}
                <span className="text-text-primary text-[12px] font-mono w-16 text-right shrink-0">{formatMinutes(o.total_minutes)}</span>
              </button>
              {open[o.id] && (
                <div className="px-4 pb-3 pl-11 flex flex-col gap-1.5">
                  {o.lines.map((l) => (
                    <div key={l.id} className="bg-bg-inset border border-border rounded-md px-3 py-2 text-[12px]">
                      <div className="flex items-start justify-between gap-2">
                        <span className={l.status === 'ANULADO' ? 'text-text-muted line-through' : 'text-text-primary font-medium'}>
                          {formatQty(l.quantity)}{l.unit_code && l.unit_code !== 'UN' ? ' ' + l.unit_code : ''} x {l.name}
                          {l.modified && l.status !== 'ANULADO' ? ' - Modificado' : ''}
                        </span>
                        <span className={'text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ' + (STATUS_STYLE[l.status] || 'text-text-muted')}>{STATUS_LABEL[l.status] || l.status}</span>
                      </div>
                      <p className="text-text-muted font-mono mt-1">
                        Inicio {formatTime(l.started_at)}{l.started_by_name ? ' (' + l.started_by_name + ')' : ''}
                        {' - '}Pronto {formatTime(l.ready_at)}{l.ready_by_name ? ' (' + l.ready_by_name + ')' : ''}
                        {' - '}Preparacao {formatMinutes(l.prep_minutes)}{' - '}Espera {formatMinutes(l.wait_minutes)}
                      </p>
                      {l.status === 'ANULADO' && (
                        <p className="text-danger mt-0.5">
                          {l.cancel_reason || 'Anulado'}{l.cancelled_by_name ? ' - por ' + l.cancelled_by_name : ''}{l.cancelled_at ? ' as ' + formatTime(l.cancelled_at) : ''}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}

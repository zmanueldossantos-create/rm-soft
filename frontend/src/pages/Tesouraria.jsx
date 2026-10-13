import { useState, useEffect, useMemo } from 'react';
import { PiggyBank, Loader2, Wallet, ArrowLeftRight, Lock, FileText, RefreshCw, ArrowRight } from 'lucide-react';
import DateInput from '../components/DateInput';
import Select from '../components/Select';
import Modal from '../components/Modal';
import { formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { getTreasuryPosition, listTreasuryMovements, listTreasuryClosings } from '../api/tesouraria';
import { fetchClosingReportPdfBlob } from '../api/pos';

// Tesouraria - the manager's view of the company's cash (treasury_overview_service): every till now, the movements
// and the closings of a period. A read only: transfers, entradas and saídas are made at the Caixa.
const TYPE_LABELS = { TRANSFERENCIA: 'Transferência', ENTRADA_EXTERNA: 'Entrada externa', SAIDA_EXTERNA: 'Saída externa' };
const STATUS_LABELS = { PENDENTE: 'Em trânsito', RECEBIDO: 'Recebido' };
const TABS = [
  { key: 'position', label: 'Posição', icon: Wallet },
  { key: 'movements', label: 'Movimentos', icon: ArrowLeftRight },
  { key: 'closings', label: 'Fechos', icon: Lock },
];

const inputCls = 'bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const th = 'px-4 py-2.5';

function todayIso() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}

function dateTime(value) {
  if (!value) return '-';
  return new Date(value).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Luanda' });
}

function day(value) {
  return value ? new Date(value + 'T00:00:00').toLocaleDateString('pt-PT') : '-';
}

function Kpi({ label, value, hint, tone = 'text-text-primary' }) {
  return (
    <div className="bg-bg-elevated border border-border rounded-lg px-5 py-4">
      <p className="text-[11px] uppercase tracking-wide text-text-muted">{label}</p>
      <p className={'font-mono font-semibold text-2xl mt-1 ' + tone}>{value}</p>
      {hint && <p className="text-[12px] text-text-muted mt-0.5">{hint}</p>}
    </div>
  );
}

function Position({ position }) {
  // the tills grouped by activity, as on the Caixa selector
  const groups = useMemo(() => {
    const byActivity = new Map();
    for (const t of position.tills) {
      if (!byActivity.has(t.activity_name)) byActivity.set(t.activity_name, []);
      byActivity.get(t.activity_name).push(t);
    }
    return [...byActivity.entries()];
  }, [position]);

  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <Kpi label="Numerário nas caixas" value={formatKz(position.totals.cash) + ' Kz'} hint="Abertas: o esperado na gaveta · fechadas: o contado no último fecho" />
        <Kpi label="Em trânsito" value={formatKz(position.totals.in_transit) + ' Kz'} hint="Transferências enviadas ainda por receber" tone={position.totals.in_transit > 0 ? 'text-accent' : 'text-text-primary'} />
        <Kpi label="Caixas abertas" value={position.totals.open_tills + ' / ' + position.totals.tills} />
      </div>
      {groups.map(([activityName, tills]) => (
        <div key={activityName} className="mb-6">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-text-muted mb-2">{activityName}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {tills.map((t) => (
              <div key={t.pos_id} className="bg-bg-elevated border border-border rounded-lg px-5 py-4 flex flex-col gap-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-display font-semibold text-text-primary truncate">{t.pos_name}</p>
                  <span className={'text-[11px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap ' + (t.is_open ? 'bg-success/10 text-success' : 'bg-bg-inset text-text-muted')}>
                    {t.is_open ? 'Aberta' : 'Fechada'}
                  </span>
                </div>
                <p className="font-mono font-semibold text-xl text-text-primary">{formatKz(t.cash)} Kz</p>
                <p className="text-[12px] text-text-muted">
                  {t.is_open
                    ? `Aberta por ${t.opened_by || '-'} · ${dateTime(t.opened_at)} · dia ${day(t.business_date)}`
                    : t.last_closed_at ? `Fechada em ${dateTime(t.last_closed_at)}` : 'Nunca aberta'}
                </p>
                {(t.pending_out > 0 || t.pending_in > 0) && (
                  <div className="flex flex-col gap-0.5 text-[12px] border-t border-border pt-2">
                    {t.pending_out > 0 && <span className="text-accent">Enviado, por receber: {formatKz(t.pending_out)} Kz</span>}
                    {t.pending_in > 0 && <span className="text-accent">A receber: {formatKz(t.pending_in)} Kz</span>}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}

function tillName(ref) {
  return ref ? ref.name + ' · ' + ref.activity_name : '-';
}

function Movements({ movements }) {
  const total = (type) => movements.filter((m) => m.movement_type === type).reduce((s, m) => s + m.amount, 0);
  if (movements.length === 0) return <p className="text-text-muted text-[13px] text-center py-12">Nenhum movimento neste período</p>;
  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
        <Kpi label="Entradas externas" value={formatKz(total('ENTRADA_EXTERNA')) + ' Kz'} tone="text-success" />
        <Kpi label="Saídas externas" value={formatKz(total('SAIDA_EXTERNA')) + ' Kz'} tone="text-danger" />
        <Kpi label="Transferências" value={formatKz(total('TRANSFERENCIA')) + ' Kz'} hint="Entre caixas - não muda o total da empresa" />
      </div>
      <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
              <th className={th + ' text-left'}>Data</th>
              <th className={th + ' text-left'}>Tipo</th>
              <th className={th + ' text-left'}>Origem → Destino</th>
              <th className={th + ' text-left'}>Motivo / descrição</th>
              <th className={th + ' text-right'}>Valor</th>
              <th className={th + ' text-left'}>Estado</th>
              <th className={th + ' text-left'}>Registado por</th>
              <th className={th + ' text-left'}>Recebido por</th>
            </tr>
          </thead>
          <tbody>
            {movements.map((m) => (
              <tr key={m.id} className="border-b border-border last:border-0">
                <td className={th + ' font-mono text-[12px] text-text-muted whitespace-nowrap'}>{dateTime(m.created_at)}</td>
                <td className={th + ' text-[13px] text-text-primary whitespace-nowrap'}>{TYPE_LABELS[m.movement_type] || m.movement_type}</td>
                <td className={th + ' text-[12px] text-text-primary'}>
                  <span className="flex items-center gap-1.5 flex-wrap">
                    <span>{m.source ? tillName(m.source) : 'Exterior'}</span>
                    <ArrowRight size={12} className="text-text-muted shrink-0" />
                    <span>{m.destination ? tillName(m.destination) : 'Exterior'}</span>
                  </span>
                </td>
                <td className={th + ' text-[12px] text-text-muted'}>{[m.reason, m.description].filter(Boolean).join(' - ') || '-'}</td>
                <td className={th + ' text-right font-mono text-[13px] whitespace-nowrap ' + (m.movement_type === 'ENTRADA_EXTERNA' ? 'text-success' : m.movement_type === 'SAIDA_EXTERNA' ? 'text-danger' : 'text-text-primary')}>
                  {m.movement_type === 'SAIDA_EXTERNA' ? '- ' : ''}{formatKz(m.amount)} Kz
                </td>
                <td className={th}>
                  <span className={'text-[11px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap ' + (m.status === 'PENDENTE' ? 'bg-accent/10 text-accent' : 'bg-bg-inset text-text-muted')}>
                    {STATUS_LABELS[m.status] || m.status}
                  </span>
                </td>
                <td className={th + ' text-[12px] text-text-muted'}>{m.created_by || '-'}</td>
                <td className={th + ' text-[12px] text-text-muted'}>{m.received_by ? m.received_by + ' · ' + dateTime(m.received_at) : '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Closings({ closings, onReport }) {
  if (closings.length === 0) return <p className="text-text-muted text-[13px] text-center py-12">Nenhum fecho neste período</p>;
  const totalDifference = closings.reduce((s, c) => s + (c.difference || 0), 0);
  const withDifference = closings.filter((c) => Math.abs(c.difference || 0) >= 0.01).length;
  return (
    <>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
        <Kpi label="Fechos" value={String(closings.length)} />
        <Kpi label="Fechos com diferença" value={String(withDifference)} tone={withDifference ? 'text-danger' : 'text-text-primary'} />
        <Kpi label="Diferença acumulada" value={formatKz(totalDifference) + ' Kz'} tone={Math.abs(totalDifference) >= 0.01 ? 'text-danger' : 'text-success'} />
      </div>
      <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
              <th className={th + ' text-left'}>Caixa</th>
              <th className={th + ' text-left'}>Dia comercial</th>
              <th className={th + ' text-left'}>Abertura</th>
              <th className={th + ' text-left'}>Fecho</th>
              <th className={th + ' text-right'}>Esperado</th>
              <th className={th + ' text-right'}>Contado</th>
              <th className={th + ' text-right'}>Diferença</th>
              <th className={th + ' text-left'}>Motivo</th>
              <th className={th}></th>
            </tr>
          </thead>
          <tbody>
            {closings.map((c) => {
              const off = Math.abs(c.difference || 0) >= 0.01;
              return (
                <tr key={c.session_id} className="border-b border-border last:border-0">
                  <td className={th + ' text-[13px] text-text-primary'}>{c.pos_name}<span className="block text-[11px] text-text-muted">{c.activity_name}</span></td>
                  <td className={th + ' font-mono text-[12px] text-text-primary whitespace-nowrap'}>{day(c.business_date)}</td>
                  <td className={th + ' text-[12px] text-text-muted'}>{dateTime(c.opened_at)}<span className="block">{c.opened_by || '-'}</span></td>
                  <td className={th + ' text-[12px] text-text-muted'}>{dateTime(c.closed_at)}<span className="block">{c.closed_by || '-'}</span></td>
                  <td className={th + ' text-right font-mono text-[13px] text-text-muted whitespace-nowrap'}>{formatKz(c.expected)} Kz</td>
                  <td className={th + ' text-right font-mono text-[13px] text-text-primary whitespace-nowrap'}>{formatKz(c.counted)} Kz</td>
                  <td className={th + ' text-right font-mono text-[13px] font-semibold whitespace-nowrap ' + (off ? 'text-danger' : 'text-success')}>{formatKz(c.difference)} Kz</td>
                  <td className={th + ' text-[12px] text-text-muted'}>{c.notes || '-'}</td>
                  <td className={th + ' text-right'}>
                    <button
                      onClick={() => onReport(c)}
                      title="Relatório de fecho"
                      className="w-8 h-8 inline-flex items-center justify-center rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer"
                    >
                      <FileText size={15} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function Tesouraria() {
  const [tab, setTab] = useState('position');
  const [position, setPosition] = useState(null);
  const [movements, setMovements] = useState([]);
  const [closings, setClosings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [dateFrom, setDateFrom] = useState(todayIso().slice(0, 8) + '01');
  const [dateTo, setDateTo] = useState(todayIso());
  const [posId, setPosId] = useState('');
  const [movementType, setMovementType] = useState('');
  const [status, setStatus] = useState('');
  const [reload, setReload] = useState(0);
  const [pdf, setPdf] = useState(null); // { url, title }

  // the tills of the filters come from the position (every active till, named with its activity)
  useEffect(() => {
    getTreasuryPosition().then(setPosition).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar a tesouraria')));
  }, [reload]);

  useEffect(() => {
    if (tab === 'position') {
      setLoading(false);  // the position has its own request (above)
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    setError('');
    const filters = { dateFrom, dateTo, posId };
    const request = tab === 'movements'
      ? listTreasuryMovements({ ...filters, movementType, status }).then((data) => { if (!cancelled) setMovements(data); })
      : listTreasuryClosings(filters).then((data) => { if (!cancelled) setClosings(data); });
    request
      .catch((err) => { if (!cancelled) setError(extractErrorMessage(err, 'Erro ao carregar')); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [tab, dateFrom, dateTo, posId, movementType, status, reload]);

  async function openReport(closing) {
    try {
      setPdf({ url: await fetchClosingReportPdfBlob(closing.session_id), title: 'Relatório de fecho - ' + closing.pos_name + ' - ' + day(closing.business_date) });
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao gerar o relatório de fecho'));
    }
  }

  function closeReport() {
    if (pdf?.url) URL.revokeObjectURL(pdf.url);
    setPdf(null);
  }

  const tillOptions = [{ value: '', label: 'Todas as caixas' }, ...(position?.tills || []).map((t) => ({ value: t.pos_id, label: t.pos_name + ' · ' + t.activity_name }))];

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-start justify-between gap-3 mb-6 flex-wrap">
        <div>
          <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
            <PiggyBank size={22} className="text-accent" />
            Tesouraria
          </h2>
          <p className="text-text-muted text-sm">O dinheiro de todas as caixas - as transferências, entradas e saídas fazem-se no ecrã Caixa</p>
        </div>
        <button
          onClick={() => { setPosition(null); setReload((n) => n + 1); }}
          className="flex items-center gap-1.5 border border-border hover:border-accent hover:text-accent text-text-muted text-[13px] font-medium px-3.5 py-2 rounded-md transition-colors cursor-pointer"
        >
          <RefreshCw size={14} /> Atualizar
        </button>
      </div>

      <div className="flex gap-1 mb-5 border-b border-border">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={'px-4 py-2.5 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer flex items-center gap-1.5 ' + (tab === key ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}
          >
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {tab !== 'position' && (
        <div className="flex items-end gap-2.5 mb-5 flex-wrap">
          <div>
            <label className={labelCls}>De</label>
            <DateInput value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setDateTo((to) => (to && to < e.target.value ? e.target.value : to)); }} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>Até</label>
            <DateInput value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} className={inputCls} />
          </div>
          <div className="w-64">
            <label className={labelCls}>Caixa</label>
            <Select value={posId} onChange={setPosId} options={tillOptions} placeholder="Todas as caixas" />
          </div>
          {tab === 'movements' && (
            <>
              <div className="w-48">
                <label className={labelCls}>Tipo</label>
                <Select value={movementType} onChange={setMovementType} placeholder="Todos os tipos"
                  options={[{ value: '', label: 'Todos os tipos' }, ...Object.entries(TYPE_LABELS).map(([value, label]) => ({ value, label }))]} />
              </div>
              <div className="w-44">
                <label className={labelCls}>Estado</label>
                <Select value={status} onChange={setStatus} placeholder="Todos"
                  options={[{ value: '', label: 'Todos' }, ...Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))]} />
              </div>
            </>
          )}
        </div>
      )}

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {loading || (tab === 'position' && !position) ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" /> A carregar...
        </div>
      ) : tab === 'position' ? (
        <Position position={position} />
      ) : tab === 'movements' ? (
        <Movements movements={movements} />
      ) : (
        <Closings closings={closings} onReport={openReport} />
      )}

      <Modal open={!!pdf} onClose={closeReport} title={pdf?.title || ''} maxWidthClass="max-w-3xl">
        {pdf && (
          <div className="flex flex-col gap-3">
            <iframe src={pdf.url} title={pdf.title} className="w-full h-[70vh] rounded-md border border-border" />
            <a
              href={pdf.url}
              download={pdf.title + '.pdf'}
              className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer no-underline"
            >
              Descarregar PDF
            </a>
          </div>
        )}
      </Modal>
    </main>
  );
}

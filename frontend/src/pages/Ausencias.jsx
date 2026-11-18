import { useEffect, useMemo, useState } from 'react';
import {
  CalendarX, Plus, Loader2, ChevronLeft, ChevronRight, Check, X, Ban, Pencil, Paperclip, FileText, List, LayoutGrid,
} from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import DateInput from '../components/DateInput';
import {
  listAbsences, getAbsenceOptions, getAbsenceMap, saveAbsence, decideAbsence, attachAbsenceDocument, countDays,
  fetchEmployeeDocumentUrl,
} from '../api/hr';
import { openPdf } from '../store/pdfViewerStore';
import { useCan } from '../utils/permissions';
import { formatDate } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Recursos Humanos → Ausências: the absences of the month (asked, approved, refused, cancelled) and the team's map. An
// absence is registered as asked, or approved at once by who may approve; a type that requires a document is approved
// only once its document is attached.
const MONTHS = ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'];
const WEEKDAY_LETTERS = ['S', 'T', 'Q', 'Q', 'S', 'S', 'D'];
const STATUS_STYLE = { PEDIDA: 'bg-amber-500/15 text-amber-500', APROVADA: 'bg-success/15 text-success', RECUSADA: 'bg-danger/15 text-danger', CANCELADA: 'bg-bg-inset text-text-muted' };
const CATEGORY_STYLE = { FERIAS: 'bg-sky-500', JUSTIFICADA: 'bg-violet-500', INJUSTIFICADA: 'bg-danger', LICENCA: 'bg-amber-500' };
const CATEGORY_LABEL = { FERIAS: 'Férias', JUSTIFICADA: 'Falta justificada', INJUSTIFICADA: 'Falta injustificada', LICENCA: 'Licença' };
const FILTERS = [{ key: 'ABERTAS', label: 'Por decidir' }, { key: 'APROVADA', label: 'Aprovadas' }, { key: '', label: 'Todas' }];
const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const iso = (d) => d.toLocaleDateString('sv-SE');

export default function Ausencias() {
  const can = useCan();
  const canRegister = can('hr:absences');
  const canDecide = can('hr:absences_approve');
  const today = new Date();
  const [period, setPeriod] = useState({ year: today.getFullYear(), month: today.getMonth() + 1 });
  const [view, setView] = useState('LIST');
  const [filter, setFilter] = useState('');
  const [data, setData] = useState(null);
  const [map, setMap] = useState(null);
  const [options, setOptions] = useState(null);
  const [form, setForm] = useState(null);
  const [preview, setPreview] = useState(null);
  const [deciding, setDeciding] = useState(null); // { absence, action, note }
  const [busy, setBusy] = useState(false);

  const first = new Date(period.year, period.month - 1, 1);
  const last = new Date(period.year, period.month, 0);
  async function load() {
    try {
      if (view === 'LIST') {
        // «Por decidir» shows every pending request, whatever its month
        const params = filter === 'ABERTAS' ? { status_filter: 'ABERTAS' } : { date_from: iso(first), date_to: iso(last), status_filter: filter || undefined };
        setData(await listAbsences(params));
      } else {
        setMap(await getAbsenceMap(period.year, period.month));
      }
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar as ausências'));
    }
  }
  useEffect(() => { load(); }, [period, view, filter]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { getAbsenceOptions().then(setOptions).catch(() => setOptions(null)); }, []);

  const typeOf = useMemo(() => Object.fromEntries((options?.types || []).map((t) => [t.id, t])), [options]);
  const move = (k) => setPeriod((p) => { const m = p.month + k; return { year: p.year + Math.floor((m - 1) / 12), month: ((m - 1) % 12 + 12) % 12 + 1 }; });

  // the days the period counts, as the user types it
  useEffect(() => {
    setPreview(null);
    if (!form?.start_date || !form?.type_id) return undefined;
    const end = form.end_date || form.start_date;
    if (end < form.start_date) return undefined;
    const timer = setTimeout(() => {
      countDays(form.start_date, end, typeOf[form.type_id]?.working_days !== false)
        .then((r) => setPreview({ ...r, days: form.half_day ? r.days / 2 : r.days })).catch(() => setPreview(null));
    }, 250);
    return () => clearTimeout(timer);
  }, [form?.start_date, form?.end_date, form?.type_id, form?.half_day]); // eslint-disable-line react-hooks/exhaustive-deps

  function openNew() {
    setForm({ employee_id: '', type_id: '', start_date: '', end_date: '', half_day: false, reason: '', approve: canDecide, file: null });
  }
  function openEdit(a) {
    setForm({ id: a.id, employee_id: a.employee_id, type_id: a.type_id, start_date: a.start_date, end_date: a.end_date, half_day: a.half_day, reason: a.reason || '', approve: false, file: null });
  }

  async function save(e) {
    e.preventDefault();
    if (!form.employee_id) { toast.error('Escolha o colaborador'); return; }
    if (!form.type_id) { toast.error('Escolha o tipo de ausência'); return; }
    if (!form.start_date) { toast.error('Indique o primeiro dia'); return; }
    const needsDocument = typeOf[form.type_id]?.requires_document;
    setBusy(true);
    try {
      const saved = await saveAbsence(form.id, { employee_id: form.employee_id, type_id: form.type_id, start_date: form.start_date,
        end_date: form.end_date || form.start_date, half_day: form.half_day, reason: form.reason || null, approve: form.approve && !needsDocument });
      if (form.file) await attachAbsenceDocument(saved.id, form.file);
      toast.success(form.id ? 'Ausência alterada' : saved.status === 'APROVADA' ? 'Ausência registada e aprovada' : 'Pedido de ausência registado');
      setForm(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar a ausência'));
    } finally {
      setBusy(false);
    }
  }

  async function decide(e) {
    e?.preventDefault();
    if (deciding.action === 'refuse' && !deciding.note?.trim()) { toast.error('Indique o motivo da recusa'); return; }
    setBusy(true);
    try {
      await decideAbsence(deciding.absence.id, deciding.action, deciding.note);
      toast.success({ approve: 'Ausência aprovada', refuse: 'Ausência recusada', cancel: 'Ausência cancelada' }[deciding.action]);
      setDeciding(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Operação recusada'));
    } finally {
      setBusy(false);
    }
  }

  async function attach(a, file) {
    try {
      await attachAbsenceDocument(a.id, file);
      toast.success('Documento junto à ausência');
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao juntar o documento'));
    }
  }

  async function viewDocument(a) {
    try {
      const url = await fetchEmployeeDocumentUrl(a.employee_id, a.document_id);
      openPdf({ url, title: `Justificativo - ${a.employee_name}`, fileName: 'justificativo' });
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao abrir o documento'));
    }
  }

  const absences = data?.absences || [];
  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <CalendarX size={22} className="text-accent" /> Ausências
      </h2>
      <p className="text-text-muted text-sm mb-5">Férias, faltas e licenças: os pedidos, as decisões e o mapa da equipa</p>

      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex rounded-md border border-border overflow-hidden">
            <button type="button" onClick={() => setView('LIST')} className={'h-9 px-3 text-sm flex items-center gap-1.5 cursor-pointer ' + (view === 'LIST' ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}><List size={15} /> Lista</button>
            <button type="button" onClick={() => setView('MAP')} className={'h-9 px-3 text-sm flex items-center gap-1.5 cursor-pointer ' + (view === 'MAP' ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}><LayoutGrid size={15} /> Mapa do mês</button>
          </div>
          {!(view === 'LIST' && filter === 'ABERTAS') && (
            <div className="flex items-center gap-1">
              <button type="button" onClick={() => move(-1)} className="w-9 h-9 rounded-md border border-border text-text-muted hover:text-text-primary flex items-center justify-center cursor-pointer"><ChevronLeft size={15} /></button>
              <span className="w-36 text-center text-sm font-semibold text-text-primary">{MONTHS[period.month - 1]} {period.year}</span>
              <button type="button" onClick={() => move(1)} className="w-9 h-9 rounded-md border border-border text-text-muted hover:text-text-primary flex items-center justify-center cursor-pointer"><ChevronRight size={15} /></button>
            </div>
          )}
          {view === 'LIST' && FILTERS.map((f) => (
            <button key={f.key} type="button" onClick={() => setFilter(f.key)}
              className={'h-9 px-3.5 rounded-md text-sm font-medium border transition-colors cursor-pointer ' + (filter === f.key ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary')}>
              {f.label}{f.key === 'ABERTAS' && data ? <span className="opacity-70"> ({data.pending})</span> : null}
            </button>
          ))}
        </div>
        {canRegister && (
          <button type="button" onClick={openNew} disabled={!options} className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm h-9 px-4 rounded-md cursor-pointer">
            <Plus size={16} /> Nova ausência
          </button>
        )}
      </div>

      {view === 'LIST' ? (
        !data ? <div className="flex justify-center py-16"><Loader2 size={18} className="animate-spin text-text-muted" /></div> : absences.length === 0 ? (
          <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
            <CalendarX size={28} className="text-text-muted mx-auto mb-3" />
            <p className="text-text-primary font-medium">{filter === 'ABERTAS' ? 'Nenhum pedido por decidir' : 'Nenhuma ausência neste mês'}</p>
          </div>
        ) : (
          <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-[11px] uppercase tracking-wide text-text-muted">
                  <th className="text-left px-4 py-2.5">Colaborador</th><th className="text-left px-4 py-2.5">Tipo</th><th className="text-left px-4 py-2.5">Período</th>
                  <th className="text-right px-4 py-2.5">Dias</th><th className="text-left px-4 py-2.5">Estado</th><th className="text-right px-4 py-2.5">Ações</th>
                </tr>
              </thead>
              <tbody>
                {absences.map((a) => (
                  <tr key={a.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40">
                    <td className="px-4 py-2.5"><span className="text-text-primary font-medium">{a.employee_name}</span> <span className="font-mono text-[11px] text-text-muted">{a.employee_number}</span></td>
                    <td className="px-4 py-2.5">
                      <span className="flex items-center gap-2"><span className={'w-2.5 h-2.5 rounded-full ' + (CATEGORY_STYLE[a.category] || 'bg-border')} /><span className="text-text-primary">{a.type_name}</span></span>
                      {a.reason && <span className="block text-[12px] text-text-muted mt-0.5">{a.reason}</span>}
                    </td>
                    <td className="px-4 py-2.5 text-text-muted whitespace-nowrap">{formatDate(a.start_date)}{a.end_date !== a.start_date ? ' → ' + formatDate(a.end_date) : ''}{a.half_day ? ' (meio dia)' : ''}</td>
                    <td className="px-4 py-2.5 text-right font-mono">{String(a.days).replace('.', ',')}{!a.paid && <span className="block text-[11px] text-danger font-sans">não remunerada</span>}</td>
                    <td className="px-4 py-2.5">
                      <span title={a.decision_note || ''} className={'inline-block whitespace-nowrap text-[11px] font-semibold px-2 py-0.5 rounded-full ' + STATUS_STYLE[a.status]}>{a.status_label}</span>
                      {a.decided_by && <span className="block text-[11px] text-text-muted mt-0.5">{a.decided_by}{a.decision_note ? ` · ${a.decision_note}` : ''}</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right whitespace-nowrap">
                      {a.document_id ? (
                        <button type="button" title="Ver o justificativo" onClick={() => viewDocument(a)} className="inline-flex items-center justify-center w-8 h-8 mr-1.5 rounded-md border border-border text-accent cursor-pointer"><FileText size={13} /></button>
                      ) : canRegister && (a.status === 'PEDIDA' || a.status === 'APROVADA') && (
                        <label title={a.requires_document ? 'Juntar o justificativo (exigido)' : 'Juntar um justificativo'} className={'inline-flex items-center justify-center w-8 h-8 mr-1.5 rounded-md border cursor-pointer ' + (a.requires_document ? 'border-amber-500 text-amber-500' : 'border-border text-text-muted hover:text-text-primary')}>
                          <Paperclip size={13} />
                          <input type="file" accept="application/pdf,image/jpeg,image/png" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) attach(a, f); }} />
                        </label>
                      )}
                      {canRegister && a.status === 'PEDIDA' && <button type="button" title="Alterar" onClick={() => openEdit(a)} className="inline-flex items-center justify-center w-8 h-8 mr-1.5 rounded-md border border-border text-text-muted hover:text-text-primary cursor-pointer"><Pencil size={13} /></button>}
                      {canDecide && a.status === 'PEDIDA' && (
                        <>
                          <button type="button" onClick={() => setDeciding({ absence: a, action: 'approve', note: '' })} className="inline-flex items-center gap-1 h-8 px-2.5 mr-1.5 rounded-md border border-success/50 text-success text-[12px] font-medium cursor-pointer"><Check size={13} /> Aprovar</button>
                          <button type="button" onClick={() => setDeciding({ absence: a, action: 'refuse', note: '' })} className="inline-flex items-center gap-1 h-8 px-2.5 mr-1.5 rounded-md border border-danger/50 text-danger text-[12px] font-medium cursor-pointer"><X size={13} /> Recusar</button>
                        </>
                      )}
                      {canDecide && (a.status === 'PEDIDA' || a.status === 'APROVADA') && (
                        <button type="button" title="Cancelar" onClick={() => setDeciding({ absence: a, action: 'cancel', note: '' })} className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger cursor-pointer"><Ban size={13} /></button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      ) : (
        !map ? <div className="flex justify-center py-16"><Loader2 size={18} className="animate-spin text-text-muted" /></div> : (
          <>
            <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
              <table className="text-[12px] border-collapse">
                <thead>
                  <tr>
                    <th className="sticky left-0 bg-bg-elevated text-left px-3 py-2 min-w-[200px] border-b border-border text-text-muted font-medium">Colaborador</th>
                    {map.days.map((d) => (
                      <th key={d.day} title={d.holiday || ''} className={'w-7 min-w-[28px] text-center py-1 border-b border-border font-normal ' + (d.holiday ? 'text-accent' : d.off ? 'text-text-muted/50' : 'text-text-muted')}>
                        <span className="block text-[10px]">{WEEKDAY_LETTERS[d.weekday]}</span>{Number(d.day.slice(8))}
                      </th>
                    ))}
                    <th className="px-3 py-2 border-b border-border text-text-muted font-medium text-right">Dias</th>
                  </tr>
                </thead>
                <tbody>
                  {map.employees.length === 0 && <tr><td colSpan={map.days.length + 2} className="text-center text-text-muted py-8">Nenhum colaborador neste mês</td></tr>}
                  {map.employees.map((r) => (
                    <tr key={r.employee_id} className="border-b border-border last:border-0">
                      <td className="sticky left-0 bg-bg-elevated px-3 py-1.5 text-text-primary whitespace-nowrap">{r.name}</td>
                      {map.days.map((d) => {
                        const cell = r.cells[d.day];
                        return (
                          <td key={d.day} title={cell ? `${cell.type}${cell.pending ? ' (pedida)' : ''}` : d.holiday || ''} className={'p-0.5 ' + (d.holiday ? 'bg-accent/10' : d.off ? 'bg-bg-inset' : '')}>
                            {cell && <div className={'h-5 rounded-sm ' + (CATEGORY_STYLE[cell.category] || 'bg-border') + (cell.pending ? ' opacity-40' : '') + (cell.half ? ' w-1/2' : '')} />}
                          </td>
                        );
                      })}
                      <td className="px-3 py-1.5 text-right font-mono text-text-primary">{String(r.absent_days).replace('.', ',')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap gap-4 mt-3 text-[12px] text-text-muted">
              {Object.entries(CATEGORY_LABEL).map(([k, label]) => <span key={k} className="flex items-center gap-1.5"><span className={'w-3 h-3 rounded-sm ' + CATEGORY_STYLE[k]} /> {label}</span>)}
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-sky-500 opacity-40" /> Pedida (por decidir)</span>
              <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded-sm bg-bg-inset border border-border" /> Fim de semana / feriado</span>
            </div>
          </>
        )
      )}

      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? 'Alterar o pedido' : 'Nova ausência'} maxWidthClass="max-w-2xl">
        {form && (
          <form noValidate onSubmit={save} className="flex flex-col gap-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className={labelClass}>Colaborador *</label>
                <Select value={form.employee_id} onChange={(v) => !form.id && setForm((p) => ({ ...p, employee_id: v }))} disabled={!!form.id} placeholder="Escolha"
                  options={(options?.employees || []).map((e) => ({ value: e.id, label: `${e.name} (${e.number})` }))} />
              </div>
              <div>
                <label className={labelClass}>Tipo *</label>
                <Select value={form.type_id} onChange={(v) => setForm((p) => ({ ...p, type_id: v }))} placeholder="Escolha"
                  options={(options?.types || []).map((t) => ({ value: t.id, label: t.name + (t.paid ? '' : ' (não remunerada)') }))} />
              </div>
              <div>
                <label className={labelClass}>Primeiro dia *</label>
                <DateInput value={form.start_date} onChange={(e) => setForm((p) => ({ ...p, start_date: e.target.value, end_date: p.end_date && p.end_date >= e.target.value ? p.end_date : e.target.value }))} className={inputClass} />
              </div>
              <div>
                <label className={labelClass}>Último dia</label>
                <DateInput value={form.end_date} onChange={(e) => setForm((p) => ({ ...p, end_date: e.target.value, half_day: e.target.value === p.start_date && p.half_day }))} className={inputClass} />
              </div>
            </div>
            {form.start_date && (!form.end_date || form.end_date === form.start_date) && (
              <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer select-none">
                <input type="checkbox" checked={form.half_day} onChange={(e) => setForm((p) => ({ ...p, half_day: e.target.checked }))} className="w-4 h-4 accent-accent" /> Meio dia
              </label>
            )}
            {preview && (
              <p className={'text-[13px] ' + (preview.days > 0 ? 'text-text-primary' : 'text-danger')}>
                {preview.days > 0 ? `${String(preview.days).replace('.', ',')} dia(s) ${typeOf[form.type_id]?.working_days === false ? 'de calendário' : 'úteis'}` : 'Nenhum dia útil neste período'}
                {preview.holidays?.length > 0 && <span className="text-text-muted"> · sem {preview.holidays.map((h) => h.name).join(', ')}</span>}
                {typeOf[form.type_id]?.max_days && <span className="text-text-muted"> · máximo {typeOf[form.type_id].max_days}</span>}
              </p>
            )}
            <div>
              <label className={labelClass}>Motivo / observação</label>
              <input value={form.reason} maxLength={500} onChange={(e) => setForm((p) => ({ ...p, reason: e.target.value }))} className={inputClass} />
            </div>
            <label className={'flex items-center gap-2 h-[42px] px-3 rounded-md border border-dashed text-[13px] cursor-pointer ' + (typeOf[form.type_id]?.requires_document && !form.file ? 'border-amber-500 text-amber-500' : 'border-border text-text-muted hover:text-accent')}>
              <Paperclip size={14} /> <span className="truncate">{form.file ? form.file.name : typeOf[form.type_id]?.requires_document ? 'Documento justificativo (exigido para aprovar)' : 'Documento justificativo (opcional)'}</span>
              <input type="file" accept="application/pdf,image/jpeg,image/png" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; setForm((p) => ({ ...p, file: f || null })); }} />
            </label>
            {!form.id && canDecide && (
              <label className="flex items-center gap-2 text-sm text-text-primary cursor-pointer select-none">
                <input type="checkbox" checked={form.approve} onChange={(e) => setForm((p) => ({ ...p, approve: e.target.checked }))} className="w-4 h-4 accent-accent" />
                Aprovar já{typeOf[form.type_id]?.requires_document ? ' (depois de juntar o documento, na lista)' : ''}
              </label>
            )}
            <button type="submit" disabled={busy} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-2.5 flex items-center justify-center gap-2 cursor-pointer">
              {busy ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />} {form.id ? 'Guardar' : 'Registar'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={!!deciding} onClose={() => setDeciding(null)} title={{ approve: 'Aprovar a ausência', refuse: 'Recusar a ausência', cancel: 'Cancelar a ausência' }[deciding?.action]}
        subtitle={deciding ? `${deciding.absence.employee_name} · ${deciding.absence.type_name} · ${formatDate(deciding.absence.start_date)}${deciding.absence.end_date !== deciding.absence.start_date ? ' → ' + formatDate(deciding.absence.end_date) : ''}` : ''}>
        {deciding && (
          <form noValidate onSubmit={decide} className="flex flex-col gap-3">
            <div>
              <label className={labelClass}>{deciding.action === 'refuse' ? 'Motivo da recusa *' : 'Observação'}</label>
              <input autoFocus value={deciding.note} maxLength={300} onChange={(e) => setDeciding((p) => ({ ...p, note: e.target.value }))} className={inputClass} />
            </div>
            <button type="submit" disabled={busy} className={'text-white font-semibold text-sm rounded-md py-2.5 flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 ' + (deciding.action === 'approve' ? 'bg-success hover:opacity-90' : 'bg-danger hover:opacity-90')}>
              {busy ? <Loader2 size={16} className="animate-spin" /> : deciding.action === 'approve' ? <Check size={16} /> : <X size={16} />}
              {{ approve: 'Aprovar', refuse: 'Recusar', cancel: 'Cancelar a ausência' }[deciding.action]}
            </button>
          </form>
        )}
      </Modal>
    </main>
  );
}

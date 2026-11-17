import { useEffect, useState } from 'react';
import { Loader2, Plus, Pencil, Trash2, Save, ArrowLeft, Wand2, ChevronLeft, ChevronRight } from 'lucide-react';
import Select from './Select';
import DateInput from './DateInput';
import { listHolidays, generateHolidays, saveHoliday, deleteHoliday, listAbsenceTypes, saveAbsenceType, deleteAbsenceType } from '../api/hr';
import { formatDate } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Parâmetros de RH → Feriados and Tipos de ausência (step 3a / 3b): the year's holidays generated from the law and
// changed by the company, and what an absence can be (paid or not, holiday days, working or calendar days, limit).
const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const KIND_STYLE = { FERIADO: 'bg-accent/10 text-accent', PONTE: 'bg-amber-500/15 text-amber-500', TOLERANCIA: 'bg-success/15 text-success', LOCAL: 'bg-bg-inset text-text-muted' };

function Check({ checked, onChange, label, hint }) {
  return (
    <label className="flex items-start gap-2.5 cursor-pointer select-none">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-0.5 w-4 h-4 accent-accent cursor-pointer" />
      <span className="text-sm text-text-primary">{label}{hint && <span className="block text-[12px] text-text-muted">{hint}</span>}</span>
    </label>
  );
}

export function HolidaysTab({ canEdit }) {
  const [year, setYear] = useState(new Date().getFullYear());
  const [data, setData] = useState(null);
  const [form, setForm] = useState(null); // { id?, day, name, kind }
  const [busy, setBusy] = useState(false);

  const load = (y = year) => listHolidays(y).then(setData).catch((e) => toast.error(extractErrorMessage(e, 'Erro ao carregar os feriados')));
  useEffect(() => { setData(null); load(year); }, [year]); // eslint-disable-line react-hooks/exhaustive-deps

  async function generate() {
    setBusy(true);
    try {
      const r = await generateHolidays(year);
      setData(r);
      toast.success(r.added ? `${r.added} dia(s) acrescentado(s) a ${year}` : `Os feriados nacionais de ${year} já estão no calendário`);
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao gerar os feriados'));
    } finally {
      setBusy(false);
    }
  }

  async function save(e) {
    e.preventDefault();
    if (!form.day) { toast.error('Indique o dia'); return; }
    setBusy(true);
    try {
      await saveHoliday(form.id, { day: form.day, name: form.name, kind: form.kind });
      setForm(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar o feriado'));
    } finally {
      setBusy(false);
    }
  }

  async function remove(h) {
    try {
      await deleteHoliday(h.id);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao apagar'));
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => setYear((y) => y - 1)} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary flex items-center justify-center cursor-pointer"><ChevronLeft size={15} /></button>
          <span className="w-16 text-center font-semibold text-text-primary">{year}</span>
          <button type="button" onClick={() => setYear((y) => y + 1)} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary flex items-center justify-center cursor-pointer"><ChevronRight size={15} /></button>
        </div>
        {canEdit && (
          <div className="flex gap-2">
            <button type="button" onClick={generate} disabled={busy} className="h-9 px-3 rounded-md border border-border text-sm text-text-primary hover:border-accent hover:text-accent flex items-center gap-1.5 cursor-pointer disabled:opacity-50">
              <Wand2 size={14} /> Feriados nacionais de {year}
            </button>
            <button type="button" onClick={() => setForm({ day: '', name: '', kind: 'TOLERANCIA' })} className="h-9 px-3 rounded-md bg-accent hover:bg-accent-hover text-white text-sm font-medium flex items-center gap-1.5 cursor-pointer">
              <Plus size={14} /> Dia
            </button>
          </div>
        )}
      </div>

      {form && (
        <form noValidate onSubmit={save} className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end border border-border rounded-md p-3">
          <div><label className={labelClass}>Dia *</label><DateInput value={form.day} onChange={(e) => setForm((p) => ({ ...p, day: e.target.value }))} className={inputClass} /></div>
          <div className="sm:col-span-2"><label className={labelClass}>Nome *</label><input value={form.name} maxLength={120} onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} className={inputClass} placeholder="Ex.: Tolerância de ponto" /></div>
          <div><label className={labelClass}>Tipo</label><Select value={form.kind} onChange={(v) => setForm((p) => ({ ...p, kind: v }))} options={data?.kinds || []} /></div>
          <div className="sm:col-span-4 flex justify-end gap-2">
            <button type="button" onClick={() => setForm(null)} className="h-9 px-3 rounded-md border border-border text-sm text-text-muted cursor-pointer">Cancelar</button>
            <button type="submit" disabled={busy} className="h-9 px-4 rounded-md bg-accent hover:bg-accent-hover text-white text-sm font-medium flex items-center gap-1.5 cursor-pointer disabled:opacity-50"><Save size={14} /> Guardar</button>
          </div>
        </form>
      )}

      {!data ? <Loader2 size={18} className="animate-spin text-text-muted mx-auto my-8" /> : data.holidays.length === 0 ? (
        <p className="text-sm text-text-muted text-center py-8">Nenhum feriado em {year}.{canEdit ? ` Use «Feriados nacionais de ${year}».` : ''}</p>
      ) : (
        <div className="border border-border rounded-md divide-y divide-border">
          {data.holidays.map((h) => (
            <div key={h.id} className="flex items-center gap-3 px-3 py-2">
              <span className="w-24 font-mono text-[13px] text-text-primary">{formatDate(h.day)}</span>
              <span className="w-16 text-[12px] text-text-muted">{h.weekday}</span>
              <span className="flex-1 text-sm text-text-primary">{h.name}</span>
              <span className={'text-[11px] px-2 py-0.5 rounded-full whitespace-nowrap ' + (KIND_STYLE[h.kind] || '')}>{h.kind_label}</span>
              {canEdit && (
                <>
                  <button type="button" title="Alterar" onClick={() => setForm({ id: h.id, day: h.day, name: h.name, kind: h.kind })} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary flex items-center justify-center cursor-pointer"><Pencil size={13} /></button>
                  <button type="button" title="Retirar" onClick={() => remove(h)} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger flex items-center justify-center cursor-pointer"><Trash2 size={13} /></button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="text-[12px] text-text-muted">Gerados a partir da lei (Lei n.º 10/11 alterada pela Lei n.º 11/18): um feriado à terça dá a segunda como ponte, à quinta a sexta - exceto Ano Novo, Carnaval, Finados e Natal. Retire uma ponte que não se aplique e acrescente as tolerâncias de ponto decretadas.</p>
    </div>
  );
}

const emptyType = { name: '', category: 'JUSTIFICADA', paid: true, takes_holiday_days: false, working_days: true, max_days: '', requires_document: false, is_active: true, notes: '' };

export function AbsenceTypesTab({ canEdit }) {
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = () => listAbsenceTypes().then(setData).catch((e) => toast.error(extractErrorMessage(e, 'Erro ao carregar')));
  useEffect(() => { load(); }, []);
  if (!data) return <Loader2 size={18} className="animate-spin text-text-muted mx-auto my-10" />;
  const set = (key) => (v) => setEditing((p) => ({ ...p, [key]: v?.target ? v.target.value : v }));

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await saveAbsenceType(editing.id, { ...editing, max_days: editing.max_days === '' ? null : Number(editing.max_days) });
      toast.success('Tipo de ausência guardado');
      setEditing(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setBusy(false);
    }
  }
  async function remove(t) {
    try {
      await deleteAbsenceType(t.id);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao apagar'));
    }
  }

  if (editing) {
    return (
      <form noValidate onSubmit={save} className="flex flex-col gap-3">
        <button type="button" onClick={() => setEditing(null)} className="self-start flex items-center gap-1.5 text-[13px] text-text-muted hover:text-text-primary cursor-pointer"><ArrowLeft size={14} /> Tipos de ausência</button>
        <fieldset disabled={!canEdit} className="contents">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2"><label className={labelClass}>Nome *</label><input value={editing.name} maxLength={120} onChange={set('name')} className={inputClass} /></div>
            <div><label className={labelClass}>Categoria</label><Select value={editing.category} onChange={set('category')} options={data.categories} /></div>
            <div><label className={labelClass}>Máximo de dias por ausência</label><input value={editing.max_days ?? ''} inputMode="numeric" onChange={set('max_days')} placeholder="Sem limite" className={inputClass + ' font-mono'} /></div>
            <div className="sm:col-span-2"><label className={labelClass}>Observação</label><input value={editing.notes || ''} maxLength={300} onChange={set('notes')} className={inputClass} /></div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 border border-border rounded-md p-3">
            <Check checked={editing.paid} onChange={set('paid')} label="Remunerada" hint="Senão, os dias são descontados no salário (DIAS_FALTA)" />
            <Check checked={editing.working_days} onChange={set('working_days')} label="Conta dias úteis" hint="Senão, dias de calendário (ex.: maternidade)" />
            {editing.category === 'FERIAS' && <Check checked={editing.takes_holiday_days} onChange={set('takes_holiday_days')} label="Desconta do saldo de férias" />}
            <Check checked={editing.requires_document} onChange={set('requires_document')} label="Exige documento justificativo" />
            <Check checked={editing.is_active} onChange={set('is_active')} label="Ativo" />
          </div>
        </fieldset>
        {canEdit && (
          <button type="submit" disabled={busy} className="self-end h-10 px-5 rounded-md bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-semibold flex items-center gap-2 cursor-pointer">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar
          </button>
        )}
      </form>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {canEdit && <button type="button" onClick={() => setEditing({ ...emptyType })} className="self-end h-9 px-3.5 rounded-md bg-accent hover:bg-accent-hover text-white text-sm font-medium flex items-center gap-1.5 cursor-pointer"><Plus size={15} /> Novo tipo</button>}
      <div className="border border-border rounded-md overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] uppercase tracking-wide text-text-muted border-b border-border">
              <th className="px-3 py-2 text-left">Tipo</th><th className="px-3 py-2 text-left">Categoria</th><th className="px-3 py-2 text-center">Remunerada</th>
              <th className="px-3 py-2 text-left">Conta</th><th className="px-3 py-2 text-center">Máx.</th><th className="px-3 py-2 text-center">Documento</th><th />
            </tr>
          </thead>
          <tbody>
            {data.types.map((t) => (
              <tr key={t.id} className={'border-b border-border last:border-0 ' + (t.is_active ? '' : 'opacity-50')}>
                <td className="px-3 py-2 text-text-primary">{t.name}{t.takes_holiday_days && <span className="ml-1.5 text-[11px] text-accent">saldo de férias</span>}</td>
                <td className="px-3 py-2 text-text-muted">{t.category_label}</td>
                <td className="px-3 py-2 text-center">{t.paid ? '✓' : <span className="text-danger">Não</span>}</td>
                <td className="px-3 py-2 text-text-muted whitespace-nowrap">{t.working_days ? 'Dias úteis' : 'Dias de calendário'}</td>
                <td className="px-3 py-2 text-center text-text-muted">{t.max_days ?? '-'}</td>
                <td className="px-3 py-2 text-center">{t.requires_document ? '✓' : '-'}</td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  <button type="button" onClick={() => setEditing({ ...t, max_days: t.max_days ?? '' })} title={canEdit ? 'Alterar' : 'Ver'} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary inline-flex items-center justify-center cursor-pointer"><Pencil size={13} /></button>
                  {canEdit && <button type="button" onClick={() => remove(t)} title="Apagar" className="ml-1.5 w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger inline-flex items-center justify-center cursor-pointer"><Trash2 size={13} /></button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[12px] text-text-muted">Valores iniciais a confirmar pelo contabilista (remuneração e número de dias de cada falta justificada).</p>
    </div>
  );
}

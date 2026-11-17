import { useEffect, useState } from 'react';
import { Loader2, Save, Plus, Pencil, Trash2, Percent, TableProperties, ListOrdered, CheckCircle2, ArrowLeft, Copy, CalendarDays, CalendarX } from 'lucide-react';
import { HolidaysTab, AbsenceTypesTab } from './HrCalendarTabs';
import Modal from './Modal';
import Select from './Select';
import DateInput from './DateInput';
import {
  getPayrollSettings, updatePayrollSettings, listIrtTables, saveIrtTable, deleteIrtTable, listPayrollItems, savePayrollItem,
  deletePayrollItem, checkFormula,
} from '../api/hr';
import { formatDate, formatKz } from '../utils/format';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Parâmetros de RH (steps 2 and 3a/3b): everything the payslip reads, nothing coded - the INSS and the hours and days of a
// month, the IRT tables (valid from a date: a new law is a new table), the rubricas (allowances and deductions, with
// their INSS / IRT base and exempt limit, fixed, % of the salary, formula or typed each month).
const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const num = (v) => (v === '' || v === null || v === undefined ? null : Number(String(v).replace(/\s/g, '').replace(',', '.')));

const TABS = [
  { key: 'GERAL', label: 'INSS e horário', icon: Percent },
  { key: 'IRT', label: 'Tabela de IRT', icon: TableProperties },
  { key: 'RUB', label: 'Rubricas', icon: ListOrdered },
  { key: 'FER', label: 'Feriados', icon: CalendarDays },
  { key: 'AUS', label: 'Tipos de ausência', icon: CalendarX },
];
const WEEKDAYS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];

function Check({ checked, onChange, label, hint }) {
  return (
    <label className="flex items-start gap-2.5 cursor-pointer select-none">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="mt-0.5 w-4 h-4 accent-accent cursor-pointer" />
      <span className="text-sm text-text-primary">{label}{hint && <span className="block text-[12px] text-text-muted">{hint}</span>}</span>
    </label>
  );
}

function GeneralTab({ canEdit }) {
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { getPayrollSettings().then((s) => setForm(Object.fromEntries(Object.entries(s).map(([k, v]) => [k, typeof v === 'boolean' || Array.isArray(v) ? v : String(v)])))).catch((e) => toast.error(extractErrorMessage(e, 'Erro ao carregar'))); }, []);
  if (!form) return <Loader2 size={18} className="animate-spin text-text-muted mx-auto my-10" />;
  const field = (label, key, hint) => (
    <div>
      <label className={labelClass}>{label}</label>
      <input value={form[key]} disabled={!canEdit} inputMode="decimal" onChange={(e) => setForm((p) => ({ ...p, [key]: e.target.value }))} className={inputClass + ' font-mono'} />
      {hint && <p className="text-[11px] text-text-muted mt-1">{hint}</p>}
    </div>
  );
  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await updatePayrollSettings({ inss_employee_rate: num(form.inss_employee_rate), inss_employer_rate: num(form.inss_employer_rate),
        monthly_hours: num(form.monthly_hours), monthly_days: num(form.monthly_days), inss_deducted_from_irt: form.inss_deducted_from_irt,
        work_weekdays: form.work_weekdays });
      toast.success('Parâmetros guardados');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form noValidate onSubmit={save} className="flex flex-col gap-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {field('INSS do trabalhador (%)', 'inss_employee_rate', 'Descontado no recibo')}
        {field('INSS da entidade empregadora (%)', 'inss_employer_rate', 'Encargo da empresa')}
        {field('Horas de trabalho por mês', 'monthly_hours', 'Valor da hora (VH) = salário base / horas')}
        {field('Dias de trabalho por mês', 'monthly_days', 'Valor do dia (VD) = salário base / dias')}
      </div>
      <div>
        <label className={labelClass}>Dias de trabalho da semana</label>
        <div className="flex flex-wrap gap-1.5">
          {WEEKDAYS.map((label, d) => {
            const on = (form.work_weekdays || []).includes(d);
            return (
              <button key={d} type="button" disabled={!canEdit}
                onClick={() => setForm((p) => ({ ...p, work_weekdays: on ? p.work_weekdays.filter((x) => x !== d) : [...p.work_weekdays, d].sort() }))}
                className={'h-9 w-14 rounded-md border text-sm font-medium cursor-pointer transition-colors ' + (on ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary')}>
                {label}
              </button>
            );
          })}
        </div>
        <p className="text-[11px] text-text-muted mt-1">As ausências e as férias contam-se nestes dias, sem os feriados.</p>
      </div>
      <Check checked={form.inss_deducted_from_irt} onChange={(v) => canEdit && setForm((p) => ({ ...p, inss_deducted_from_irt: v }))}
        label="O INSS do trabalhador é deduzido da base do IRT" hint="Matéria colectável = rendimentos tributáveis - INSS" />
      {canEdit && (
        <button type="submit" disabled={busy} className="self-end h-10 px-5 rounded-md bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-semibold flex items-center gap-2 cursor-pointer">
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar
        </button>
      )}
    </form>
  );
}

function IrtTab({ canEdit }) {
  const [tables, setTables] = useState(null);
  const [editing, setEditing] = useState(null); // { id?, name, valid_from, brackets: [{from,to,fixed,rate,over}] }
  const [busy, setBusy] = useState(false);
  const load = () => listIrtTables().then(setTables).catch((e) => toast.error(extractErrorMessage(e, 'Erro ao carregar')));
  useEffect(() => { load(); }, []);
  if (!tables) return <Loader2 size={18} className="animate-spin text-text-muted mx-auto my-10" />;

  const str = (v) => (v === null || v === undefined ? '' : String(v));
  function open(table, copy = false) {
    setEditing({ id: copy ? null : table?.id, name: copy ? '' : table?.name || '', valid_from: copy ? '' : table?.valid_from || '',
      brackets: (table?.brackets || [{ from: 0, to: null, fixed: 0, rate: 0, over: 0 }]).map((b) => ({ from: str(b.from), to: str(b.to), fixed: str(b.fixed), rate: str(b.rate), over: str(b.over) })) });
  }
  function setRow(k, key, value) {
    setEditing((p) => {
      const brackets = p.brackets.map((b, i) => (i === k ? { ...b, [key]: value } : b));
      // the next bracket starts where this one ends
      if (key === 'to' && brackets[k + 1]) brackets[k + 1] = { ...brackets[k + 1], from: value, over: brackets[k + 1].over === brackets[k + 1].from ? value : brackets[k + 1].over };
      return { ...p, brackets };
    });
  }
  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await saveIrtTable(editing.id, { name: editing.name, valid_from: editing.valid_from || null,
        brackets: editing.brackets.map((b) => ({ from: num(b.from), to: num(b.to), fixed: num(b.fixed), rate: num(b.rate), over: num(b.over) })) });
      toast.success('Tabela de IRT guardada');
      setEditing(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar a tabela'));
    } finally {
      setBusy(false);
    }
  }
  async function remove(table) {
    try {
      await deleteIrtTable(table.id);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao apagar'));
    }
  }

  if (editing) {
    const cell = 'w-full bg-bg-inset border border-border rounded px-2 py-1.5 text-[13px] font-mono text-right text-text-primary outline-none focus:border-accent';
    return (
      <form noValidate onSubmit={save} className="flex flex-col gap-3">
        <button type="button" onClick={() => setEditing(null)} className="self-start flex items-center gap-1.5 text-[13px] text-text-muted hover:text-text-primary cursor-pointer"><ArrowLeft size={14} /> Tabelas</button>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div><label className={labelClass}>Nome *</label><input value={editing.name} disabled={!canEdit} onChange={(e) => setEditing((p) => ({ ...p, name: e.target.value }))} placeholder="Ex.: OGE 2027" className={inputClass} /></div>
          <div><label className={labelClass}>Aplica-se a partir de *</label><DateInput value={editing.valid_from} disabled={!canEdit} onChange={(e) => setEditing((p) => ({ ...p, valid_from: e.target.value }))} className={inputClass} /></div>
        </div>
        <div className="border border-border rounded-md overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[11px] uppercase tracking-wide text-text-muted border-b border-border">
                <th className="px-2 py-2 text-left">Esc.</th><th className="px-2 py-2 text-right">De (Kz)</th><th className="px-2 py-2 text-right">Até (Kz)</th>
                <th className="px-2 py-2 text-right">Parcela fixa</th><th className="px-2 py-2 text-right">Taxa %</th><th className="px-2 py-2 text-right">Sobre o excesso de</th><th />
              </tr>
            </thead>
            <tbody>
              {editing.brackets.map((b, k) => (
                <tr key={k} className="border-b border-border last:border-0">
                  <td className="px-2 py-1.5 text-text-muted">{k + 1}º</td>
                  <td className="px-2 py-1.5"><input value={b.from} disabled={!canEdit || k > 0} onChange={(e) => setRow(k, 'from', e.target.value)} className={cell} /></td>
                  <td className="px-2 py-1.5"><input value={b.to} disabled={!canEdit} placeholder={k === editing.brackets.length - 1 ? 'sem limite' : ''} onChange={(e) => setRow(k, 'to', e.target.value)} className={cell} /></td>
                  <td className="px-2 py-1.5"><input value={b.fixed} disabled={!canEdit} onChange={(e) => setRow(k, 'fixed', e.target.value)} className={cell} /></td>
                  <td className="px-2 py-1.5"><input value={b.rate} disabled={!canEdit} onChange={(e) => setRow(k, 'rate', e.target.value)} className={cell} /></td>
                  <td className="px-2 py-1.5"><input value={b.over} disabled={!canEdit} onChange={(e) => setRow(k, 'over', e.target.value)} className={cell} /></td>
                  <td className="px-2 py-1.5 text-right">
                    {canEdit && editing.brackets.length > 1 && (
                      <button type="button" title="Retirar" onClick={() => setEditing((p) => ({ ...p, brackets: p.brackets.filter((_, i) => i !== k) }))} className="w-7 h-7 inline-flex items-center justify-center rounded border border-border text-text-muted hover:text-danger cursor-pointer"><Trash2 size={12} /></button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[12px] text-text-muted">IRT = parcela fixa + (base - excesso de) × taxa, no escalão da base. Cada escalão começa onde o anterior acaba; o último fica sem limite.</p>
        {canEdit && (
          <div className="flex justify-between">
            <button type="button" onClick={() => setEditing((p) => { const last = p.brackets[p.brackets.length - 1]; return { ...p, brackets: [...p.brackets, { from: last.to, to: '', fixed: '', rate: '', over: last.to }] }; })}
              className="h-9 px-3 rounded-md border border-border text-sm text-text-primary hover:border-accent flex items-center gap-1.5 cursor-pointer"><Plus size={14} /> Escalão</button>
            <button type="submit" disabled={busy} className="h-10 px-5 rounded-md bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-semibold flex items-center gap-2 cursor-pointer">
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar tabela
            </button>
          </div>
        )}
      </form>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {tables.map((t) => (
        <div key={t.id} className="border border-border rounded-md px-4 py-3 flex items-center gap-3">
          <div className="flex-1">
            <p className="text-sm font-medium text-text-primary flex items-center gap-2">{t.name}
              {t.in_force && <span className="text-[11px] px-2 py-0.5 rounded-full bg-success/15 text-success flex items-center gap-1"><CheckCircle2 size={11} /> Em vigor</span>}</p>
            <p className="text-[12px] text-text-muted">A partir de {formatDate(t.valid_from)} · {t.brackets.length} escalões · isento até {formatKz(t.brackets[0]?.rate === 0 ? t.brackets[0].to : 0)} Kz</p>
          </div>
          <button type="button" onClick={() => open(t)} title={canEdit ? 'Alterar' : 'Ver'} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary flex items-center justify-center cursor-pointer"><Pencil size={13} /></button>
          {canEdit && <button type="button" onClick={() => open(t, true)} title="Nova tabela a partir desta" className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary flex items-center justify-center cursor-pointer"><Copy size={13} /></button>}
          {canEdit && tables.length > 1 && <button type="button" onClick={() => remove(t)} title="Apagar" className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger flex items-center justify-center cursor-pointer"><Trash2 size={13} /></button>}
        </div>
      ))}
      <p className="text-[12px] text-text-muted">Uma nova lei (OGE, IRPS) é uma nova tabela a partir da sua data: os meses já processados guardam a sua. Use o botão de cópia para partir da tabela atual.</p>
    </div>
  );
}

const emptyItem = { code: '', name: '', nature: 'ABONO', calc_method: 'FIXO', amount: '', rate: '', formula: '', subject_inss: true, subject_irt: true,
  irt_exempt_limit: '', applies_to_all: false, is_active: true, notes: '' };

function ItemsTab({ canEdit }) {
  const [data, setData] = useState(null);
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [example, setExample] = useState(null);
  const load = () => listPayrollItems().then(setData).catch((e) => toast.error(extractErrorMessage(e, 'Erro ao carregar')));
  useEffect(() => { load(); }, []);
  if (!data) return <Loader2 size={18} className="animate-spin text-text-muted mx-auto my-10" />;

  const str = (v) => (v === null || v === undefined ? '' : String(v));
  const set = (key) => (v) => setEditing((p) => ({ ...p, [key]: v?.target ? v.target.value : v }));
  function open(item) {
    setExample(null);
    setEditing(item ? { ...item, amount: str(item.amount), rate: str(item.rate), formula: item.formula || '', irt_exempt_limit: str(item.irt_exempt_limit), notes: item.notes || '' } : { ...emptyItem });
  }
  async function save(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await savePayrollItem(editing.id, { ...editing, amount: num(editing.amount), rate: num(editing.rate), irt_exempt_limit: num(editing.irt_exempt_limit) });
      toast.success('Rubrica guardada');
      setEditing(null);
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar a rubrica'));
    } finally {
      setBusy(false);
    }
  }
  async function test() {
    try {
      const r = await checkFormula(editing.formula, editing.code);
      setExample(r);
    } catch (err) {
      setExample(null);
      toast.error(extractErrorMessage(err, 'Fórmula inválida'));
    }
  }
  async function remove(item) {
    try {
      await deletePayrollItem(item.id);
      toast.success('Rubrica apagada');
      await load();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao apagar'));
    }
  }

  if (editing) {
    const isDeduction = editing.nature === 'DESCONTO';
    return (
      <form noValidate onSubmit={save} className="flex flex-col gap-3">
        <button type="button" onClick={() => setEditing(null)} className="self-start flex items-center gap-1.5 text-[13px] text-text-muted hover:text-text-primary cursor-pointer"><ArrowLeft size={14} /> Rubricas</button>
        <fieldset disabled={!canEdit} className="contents">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div><label className={labelClass}>Código *</label><input value={editing.code} maxLength={20} onChange={(e) => set('code')(e.target.value.toUpperCase())} placeholder="SUB_ALIM" className={inputClass + ' font-mono'} /></div>
          <div className="sm:col-span-2"><label className={labelClass}>Nome *</label><input value={editing.name} maxLength={120} onChange={set('name')} className={inputClass} /></div>
          <div><label className={labelClass}>Natureza</label><Select value={editing.nature} onChange={set('nature')} options={data.natures} /></div>
          <div className="sm:col-span-2"><label className={labelClass}>Cálculo</label><Select value={editing.calc_method} onChange={set('calc_method')} options={data.calc_methods} /></div>
          {editing.calc_method === 'FIXO' && <div className="sm:col-span-2"><label className={labelClass}>Valor por omissão (Kz)</label><input value={editing.amount} inputMode="decimal" onChange={set('amount')} placeholder="Indicado na ficha de cada colaborador" className={inputClass + ' font-mono'} /></div>}
          {editing.calc_method === 'PERCENTAGEM' && <div className="sm:col-span-2"><label className={labelClass}>Percentagem do salário base *</label><input value={editing.rate} inputMode="decimal" onChange={set('rate')} className={inputClass + ' font-mono'} /></div>}
          {editing.calc_method === 'MENSAL' && <p className="sm:col-span-2 self-end text-[12px] text-text-muted pb-2">O valor é indicado em cada mês, nas variáveis do mês.</p>}
        </div>
        {editing.calc_method === 'FORMULA' && (
          <div className="flex flex-col gap-2">
            <label className={labelClass + ' !mb-0'}>Fórmula *</label>
            <div className="flex gap-2">
              <input value={editing.formula} onChange={(e) => { setExample(null); set('formula')(e.target.value); }} placeholder="Ex.: SE(ANTIGUIDADE >= 5; SB * 5%; 0)" className={inputClass + ' font-mono'} />
              <button type="button" onClick={test} className="h-[38px] px-3 rounded-md border border-border text-sm text-text-primary hover:border-accent whitespace-nowrap cursor-pointer">Testar</button>
            </div>
            {example && <p className="text-[12px] text-success">Com salário base {formatKz(example.example_salary)} e 5 anos de antiguidade: {formatKz(example.value)} Kz</p>}
            <div className="flex flex-wrap gap-1.5">
              {[...data.variables, ...data.items.filter((i) => i.code !== editing.code).map((i) => ({ code: i.code, label: i.name }))].map((v) => (
                <button key={v.code} type="button" title={v.label} onClick={() => set('formula')((editing.formula ? editing.formula + ' ' : '') + v.code)}
                  className="text-[11px] font-mono px-2 py-0.5 rounded border border-border text-text-muted hover:text-accent hover:border-accent cursor-pointer">{v.code}</button>
              ))}
            </div>
            <p className="text-[11px] text-text-muted">Operações + - * / ( ) e %, comparações {'> < >= <= = <>'}, funções SE(condição; então; senão), MIN(a; b), MAX(a; b), ARRED(x). Separe os argumentos com «;».</p>
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 border border-border rounded-md p-3">
          <Check checked={editing.subject_inss} onChange={set('subject_inss')} label={isDeduction ? 'Reduz a base do INSS' : 'Entra na base do INSS'} />
          <Check checked={editing.subject_irt} onChange={set('subject_irt')} label={isDeduction ? 'Reduz a base do IRT' : 'Entra na base do IRT'} />
          {!isDeduction && editing.subject_irt && (
            <div><label className={labelClass}>Isento de IRT até (Kz)</label><input value={editing.irt_exempt_limit} inputMode="decimal" onChange={set('irt_exempt_limit')} placeholder="Sem limite: tudo tributado" className={inputClass + ' font-mono'} /></div>
          )}
          {editing.calc_method !== 'MENSAL' && <Check checked={editing.applies_to_all} onChange={set('applies_to_all')} label="Aplica-se a todos os colaboradores" hint="Senão, só a quem a tiver na ficha (Remuneração)" />}
          <Check checked={editing.is_active} onChange={set('is_active')} label="Ativa" />
        </div>
        <div><label className={labelClass}>Observação</label><input value={editing.notes} maxLength={300} onChange={set('notes')} className={inputClass} /></div>
        </fieldset>
        {canEdit && (
          <button type="submit" disabled={busy} className="self-end h-10 px-5 rounded-md bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-semibold flex items-center gap-2 cursor-pointer">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Guardar rubrica
          </button>
        )}
      </form>
    );
  }

  const describe = (i) => {
    if (i.calc_method === 'FIXO') return i.amount !== null ? formatKz(i.amount) + ' Kz' : 'Valor na ficha';
    if (i.calc_method === 'PERCENTAGEM') return i.rate + ' % do salário';
    if (i.calc_method === 'FORMULA') return i.formula;
    return 'Valor do mês';
  };
  return (
    <div className="flex flex-col gap-3">
      {canEdit && <button type="button" onClick={() => open(null)} className="self-end h-9 px-3.5 rounded-md bg-accent hover:bg-accent-hover text-white text-sm font-medium flex items-center gap-1.5 cursor-pointer"><Plus size={15} /> Nova rubrica</button>}
      <div className="border border-border rounded-md overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[11px] uppercase tracking-wide text-text-muted border-b border-border">
              <th className="px-3 py-2 text-left">Código</th><th className="px-3 py-2 text-left">Rubrica</th><th className="px-3 py-2 text-left">Cálculo</th>
              <th className="px-3 py-2 text-center">INSS</th><th className="px-3 py-2 text-center">IRT</th><th className="px-3 py-2 text-left">Aplica-se</th><th />
            </tr>
          </thead>
          <tbody>
            {data.items.map((i) => (
              <tr key={i.id} className={'border-b border-border last:border-0 ' + (i.is_active ? '' : 'opacity-50')}>
                <td className="px-3 py-2 font-mono text-[12px] text-text-muted">{i.code}</td>
                <td className="px-3 py-2 text-text-primary">{i.name} <span className={'ml-1 text-[11px] px-1.5 py-0.5 rounded ' + (i.nature === 'ABONO' ? 'bg-success/10 text-success' : 'bg-danger/10 text-danger')}>{i.nature === 'ABONO' ? 'Abono' : 'Desconto'}</span></td>
                <td className="px-3 py-2 text-text-muted text-[13px] max-w-[260px] truncate" title={describe(i)}>{describe(i)}</td>
                <td className="px-3 py-2 text-center">{i.subject_inss ? '✓' : '-'}</td>
                <td className="px-3 py-2 text-center whitespace-nowrap">{i.subject_irt ? (i.irt_exempt_limit !== null ? `isento até ${formatKz(i.irt_exempt_limit)}` : '✓') : '-'}</td>
                <td className="px-3 py-2 text-text-muted text-[13px] whitespace-nowrap">{i.calc_method === 'MENSAL' ? 'No mês' : i.applies_to_all ? 'Todos' : `${i.employees} colab.`}</td>
                <td className="px-3 py-2 text-right whitespace-nowrap">
                  <button type="button" onClick={() => open(i)} title={canEdit ? 'Alterar' : 'Ver'} className="w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary inline-flex items-center justify-center cursor-pointer"><Pencil size={13} /></button>
                  {canEdit && i.employees === 0 && <button type="button" onClick={() => remove(i)} title="Apagar" className="ml-1.5 w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger inline-flex items-center justify-center cursor-pointer"><Trash2 size={13} /></button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[12px] text-text-muted">Num desconto, as caixas INSS / IRT querem dizer «reduz a base» (ex.: faltas injustificadas). Os valores por omissão das rubricas devem ser confirmados pelo contabilista da empresa.</p>
    </div>
  );
}

export default function PayrollSettingsModal({ open, onClose, canEdit }) {
  const [tab, setTab] = useState('GERAL');
  useEffect(() => { if (open) setTab('GERAL'); }, [open]);
  return (
    <Modal open={open} onClose={onClose} title="Parâmetros de RH" subtitle="O que os salários e as ausências leem: nada está escrito no programa" maxWidthClass="max-w-5xl" size="full">
      <div className="flex gap-1 border-b border-border -mt-1 mb-5 overflow-x-auto">
        {TABS.map((t) => (
          <button key={t.key} type="button" onClick={() => setTab(t.key)}
            className={'flex items-center gap-2 px-4 h-10 text-sm font-medium border-b-2 -mb-px whitespace-nowrap cursor-pointer transition-colors ' + (tab === t.key ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}>
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </div>
      {open && tab === 'GERAL' && <GeneralTab canEdit={canEdit} />}
      {open && tab === 'IRT' && <IrtTab canEdit={canEdit} />}
      {open && tab === 'RUB' && <ItemsTab canEdit={canEdit} />}
      {open && tab === 'FER' && <HolidaysTab canEdit={canEdit} />}
      {open && tab === 'AUS' && <AbsenceTypesTab canEdit={canEdit} />}
    </Modal>
  );
}

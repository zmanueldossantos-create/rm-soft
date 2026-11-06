import { useEffect, useMemo, useState } from 'react';
import { BookText, Plus, Trash2, Loader2, Search, Undo2, Pencil, CheckCircle2, AlertTriangle } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import DateInput from '../components/DateInput';
import ConfirmDialog from '../components/ConfirmDialog';
import {
  getChart, getJournals, createJournal, updateJournal, deleteJournal, getEntries, getEntry, saveEntry, deleteEntry, reverseEntry,
} from '../api/accounting';
import { extractErrorMessage } from '../utils/errors';
import { formatKz } from '../utils/format';
import { useCan } from '../utils/permissions';
import { toast } from '../store/toastStore';

// Contabilidade › Lançamentos: the entries typed in the journals (diários). A draft (rascunho) is changed freely; posted
// («Lançar») it must balance (debit = credit), takes the next number of its journal for the year (OD 2026/0001) and
// never changes again - it is corrected by its estorno. Lines go to last-level active accounts only. The «Diários» tab
// sets the journals (the defaults VND, CMP, CX, BCO, OD, ABE are made with the chart).

const inputCls = 'bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const cellInputCls = 'bg-bg-inset border border-border rounded-md px-2.5 py-2 text-[13px] text-text-primary outline-none focus:border-accent transition-colors w-full';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const btnGhost = 'flex items-center gap-1.5 border border-border hover:border-accent text-text-primary hover:text-accent text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50';
const btnPrimary = 'flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50';

const today = () => new Date().toISOString().slice(0, 10);
const fmtDate = (iso) => (iso ? iso.slice(8, 10) + '/' + iso.slice(5, 7) + '/' + iso.slice(0, 4) : '');
// amounts typed with a comma or a point, kept as text while typing; 0 when empty
const toNumber = (text) => Number(String(text ?? '').replace(/\s/g, '').replace(',', '.')) || 0;
const cents = (n) => Math.round(n * 100);
const emptyLine = () => ({ key: Math.random().toString(36).slice(2), account_id: '', description: '', debit: '', credit: '' });

export default function Lancamentos() {
  const can = useCan();
  const canRecord = can('accounting:entries_record');
  const canJournals = can('accounting:journals_manage');
  const [view, setView] = useState('entries'); // entries | journals
  const [journals, setJournals] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [entries, setEntries] = useState(null);
  const [filters, setFilters] = useState({ journal_id: '', status: '', date_from: '', date_to: '', q: '' });
  const [form, setForm] = useState(null); // the entry being typed / looked at
  const [busy, setBusy] = useState(false);
  const [reverse, setReverse] = useState(null); // { entry, date }
  const [toDelete, setToDelete] = useState(null);
  const [journalForm, setJournalForm] = useState(null); // { id?, code, name, isActive }
  const [journalToDelete, setJournalToDelete] = useState(null);

  async function loadJournals() {
    try {
      setJournals(await getJournals());
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar os diários'));
    }
  }
  async function loadEntries(f = filters) {
    try {
      setEntries(await getEntries(f));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar os lançamentos'));
    }
  }
  useEffect(() => {
    loadJournals();
    getChart().then((c) => setAccounts(c.accounts)).catch(() => {});
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => loadEntries(filters), 250);
    return () => clearTimeout(timer);
  }, [filters]); // eslint-disable-line react-hooks/exhaustive-deps

  // only last-level active accounts take lines
  const accountOptions = useMemo(() => accounts.filter((a) => a.is_active && !a.has_children)
    .map((a) => ({ value: a.id, label: a.code + ' · ' + a.name })), [accounts]);
  const activeJournals = (journals || []).filter((j) => j.is_active);
  const journalOptions = (list) => list.map((j) => ({ value: j.id, label: j.code + ' · ' + j.name }));

  function newEntry() {
    if (!activeJournals.length) {
      toast.error('Não há nenhum diário ativo - crie um no separador Diários');
      return;
    }
    const od = activeJournals.find((j) => j.code === 'OD') || activeJournals[0];
    setForm({ id: null, status: 'RASCUNHO', journal_id: od.id, entry_date: today(), description: '', document_ref: '', lines: [emptyLine(), emptyLine()] });
  }

  async function openEntry(row) {
    try {
      const e = await getEntry(row.id);
      setForm({
        id: e.id, status: e.status, label: e.label, journal_id: e.journal_id, entry_date: e.entry_date, description: e.description,
        document_ref: e.document_ref || '', reversal_of: e.reversal_of, reversed_by: e.reversed_by,
        lines: e.lines.map((l) => ({ ...emptyLine(), account_id: l.account_id, account_label: l.account_code + ' · ' + l.account_name,
          description: l.description || '', debit: Number(l.debit) ? String(Number(l.debit)) : '', credit: Number(l.credit) ? String(Number(l.credit)) : '' })),
      });
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao abrir o lançamento'));
    }
  }

  const totals = useMemo(() => {
    const lines = form?.lines || [];
    const debit = lines.reduce((s, l) => s + cents(toNumber(l.debit)), 0);
    const credit = lines.reduce((s, l) => s + cents(toNumber(l.credit)), 0);
    return { debit: debit / 100, credit: credit / 100, diff: (debit - credit) / 100 };
  }, [form]);

  function setLine(key, patch) {
    setForm((f) => ({ ...f, lines: f.lines.map((l) => {
      if (l.key !== key) return l;
      const next = { ...l, ...patch };
      // a line is a debit OR a credit: typing one side clears the other
      if (patch.debit !== undefined && toNumber(patch.debit)) next.credit = '';
      if (patch.credit !== undefined && toNumber(patch.credit)) next.debit = '';
      return next;
    }) }));
  }

  function addLine() {
    // the new line takes what is missing to balance, on the side that lacks it
    const line = emptyLine();
    if (totals.diff > 0) line.credit = String(totals.diff);
    if (totals.diff < 0) line.debit = String(-totals.diff);
    setForm((f) => ({ ...f, lines: [...f.lines, line] }));
  }

  async function save(post) {
    const lines = form.lines.filter((l) => l.account_id || toNumber(l.debit) || toNumber(l.credit) || l.description.trim())
      .map((l) => ({ account_id: l.account_id || null, description: l.description, debit: toNumber(l.debit), credit: toNumber(l.credit) }));
    setBusy(true);
    try {
      const saved = await saveEntry(form.id, {
        journal_id: form.journal_id, entry_date: form.entry_date, description: form.description, document_ref: form.document_ref, lines, post,
      });
      toast.success(post ? 'Lançamento ' + saved.label + ' lançado' : 'Rascunho guardado');
      setForm(null);
      loadEntries();
      loadJournals();
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Lançamento recusado'));
    } finally {
      setBusy(false);
    }
  }

  async function run(action, success, after) {
    setBusy(true);
    try {
      const result = await action();
      toast.success(typeof success === 'function' ? success(result) : success);
      if (after) after(result);
      return result;
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Operação recusada'));
      return null;
    } finally {
      setBusy(false);
    }
  }

  const editable = form && form.status === 'RASCUNHO' && canRecord;
  const balanced = totals.debit > 0 && totals.diff === 0;

  if (!journals) {
    return <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-9 flex justify-center"><Loader2 className="animate-spin text-accent" /></main>;
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-text-primary flex items-center gap-2.5"><BookText size={22} className="text-accent" /> Lançamentos</h1>
          <p className="text-text-muted text-sm mt-1">Os lançamentos dos diários: débito = crédito, numerados por diário e ano, corrigidos por estorno</p>
        </div>
        <div className="flex items-center gap-2">
          {view === 'entries' && canRecord && <button type="button" onClick={newEntry} className={btnPrimary}><Plus size={15} /> Novo lançamento</button>}
          {view === 'journals' && canJournals && <button type="button" onClick={() => setJournalForm({ code: '', name: '', isActive: true })} className={btnPrimary}><Plus size={15} /> Novo diário</button>}
        </div>
      </div>

      <div className="flex gap-1 mb-5 border-b border-border">
        {[['entries', 'Lançamentos'], ['journals', 'Diários']].map(([key, label]) => (
          <button key={key} type="button" onClick={() => setView(key)}
            className={'px-4 py-2.5 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer ' + (view === key ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}>
            {label}
          </button>
        ))}
      </div>

      {view === 'entries' && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3 mb-4">
            <div className="relative lg:col-span-2">
              <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
              <input value={filters.q} onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))} placeholder="Procurar na descrição ou no documento" className={inputCls + ' w-full pl-10'} />
            </div>
            <Select value={filters.journal_id} onChange={(v) => setFilters((f) => ({ ...f, journal_id: v }))}
              options={[{ value: '', label: 'Todos os diários' }, ...journalOptions(journals)]} />
            <Select value={filters.status} onChange={(v) => setFilters((f) => ({ ...f, status: v }))}
              options={[{ value: '', label: 'Todos os estados' }, { value: 'RASCUNHO', label: 'Rascunhos' }, { value: 'LANCADO', label: 'Lançados' }]} />
            <div className="flex items-center gap-2 sm:col-span-2">
              <div className="flex-1 min-w-0"><DateInput value={filters.date_from} onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))} className={inputCls + ' w-full'} /></div>
              <span className="text-text-muted text-xs">a</span>
              <div className="flex-1 min-w-0"><DateInput value={filters.date_to} min={filters.date_from || undefined} onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))} className={inputCls + ' w-full'} /></div>
            </div>
          </div>

          <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted border-b border-border">
                  <th className="px-4 py-3 font-medium">Número</th>
                  <th className="px-4 py-3 font-medium">Data</th>
                  <th className="px-4 py-3 font-medium">Descrição</th>
                  <th className="px-4 py-3 font-medium text-right">Débito</th>
                  <th className="px-4 py-3 font-medium text-right">Crédito</th>
                  <th className="px-4 py-3 font-medium">Estado</th>
                </tr>
              </thead>
              <tbody>
                {entries === null && <tr><td colSpan={6} className="py-10 text-center"><Loader2 className="animate-spin text-accent inline" /></td></tr>}
                {entries?.length === 0 && <tr><td colSpan={6} className="py-10 text-center text-text-muted">Nenhum lançamento{canRecord ? ' - comece por «Novo lançamento»' : ''}</td></tr>}
                {entries?.map((e) => (
                  <tr key={e.id} onClick={() => openEntry(e)} className="border-b border-border last:border-0 hover:bg-bg-inset/60 cursor-pointer">
                    <td className="px-4 py-2.5 font-mono whitespace-nowrap text-text-primary">{e.label}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-text-muted">{fmtDate(e.entry_date)}</td>
                    <td className="px-4 py-2.5 text-text-primary">
                      {e.description}
                      {e.document_ref && <span className="text-text-muted"> · {e.document_ref}</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono whitespace-nowrap">{formatKz(e.debit)}</td>
                    <td className="px-4 py-2.5 text-right font-mono whitespace-nowrap">{formatKz(e.credit)}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap"><StatusBadge entry={e} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {view === 'journals' && (
        <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden max-w-3xl">
          {journals.length === 0 && <p className="text-text-muted text-[13px] text-center py-10">Os diários são criados ao começar o plano de contas</p>}
          {journals.map((j) => (
            <div key={j.id} className={'flex items-center gap-3 px-4 py-2.5 border-b border-border last:border-0' + (j.is_active ? '' : ' opacity-50')}>
              <span className="font-mono text-[13px] font-semibold text-text-primary w-16 shrink-0">{j.code}</span>
              <span className="text-[13px] text-text-primary flex-1 min-w-0 truncate">{j.name}</span>
              {!j.is_active && <span className="text-[10px] font-semibold uppercase text-text-muted bg-bg-inset px-1.5 py-0.5 rounded">Inativo</span>}
              <span className="text-[12px] text-text-muted w-28 text-right">{j.entries} lançamento(s)</span>
              {canJournals && (
                <div className="flex items-center gap-1.5 shrink-0">
                  <button type="button" title="Editar" onClick={() => setJournalForm({ id: j.id, code: j.code, name: j.name, isActive: j.is_active })}
                    className="w-7 h-7 inline-flex items-center justify-center rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer"><Pencil size={13} /></button>
                  <button type="button" title={j.entries ? 'Tem lançamentos - não pode ser apagado (pode desativá-lo)' : 'Apagar'} disabled={j.entries > 0} onClick={() => setJournalToDelete(j)}
                    className="w-7 h-7 inline-flex items-center justify-center rounded-md border border-border text-text-muted hover:text-danger hover:border-danger transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"><Trash2 size={13} /></button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* The entry: typed (a draft) or looked at (posted) */}
      <Modal open={!!form} onClose={() => setForm(null)} size="full" maxWidthClass="max-w-6xl"
        title={form?.id ? (form.status === 'LANCADO' ? 'Lançamento ' + form.label : 'Rascunho') : 'Novo lançamento'}
        subtitle={form?.reversal_of ? 'Estorno de ' + form.reversal_of : form?.reversed_by ? 'Estornado por ' + form.reversed_by : editable ? 'Débito = crédito para lançar. Só contas de último nível.' : null}
        footer={form && (
          <div className="flex items-center justify-between gap-3 px-6 py-4 flex-wrap">
            <div className="flex items-center gap-2">
              {editable && form.id && <button type="button" disabled={busy} onClick={() => setToDelete(form)} className={btnGhost + ' hover:!border-danger hover:!text-danger'}><Trash2 size={15} /> Apagar rascunho</button>}
              {!editable && form.status === 'LANCADO' && canRecord && !form.reversal_of && !form.reversed_by && (
                <button type="button" disabled={busy} onClick={() => setReverse({ entry: form, date: today() })} className={btnGhost}><Undo2 size={15} /> Estornar</button>
              )}
            </div>
            {editable && (
              <div className="flex items-center gap-2">
                <button type="button" disabled={busy} onClick={() => save(false)} className={btnGhost}>Guardar rascunho</button>
                <button type="button" disabled={busy || !balanced} onClick={() => save(true)} className={btnPrimary}
                  title={balanced ? '' : 'O lançamento tem de estar equilibrado'}>
                  <CheckCircle2 size={15} /> Lançar
                </button>
              </div>
            )}
          </div>
        )}>
        {form && (
          <div className="flex flex-col gap-5">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className={labelCls}>Diário *</label>
                {editable
                  ? <Select value={form.journal_id} onChange={(v) => setForm((f) => ({ ...f, journal_id: v }))} options={journalOptions(activeJournals)} />
                  : <p className="text-sm text-text-primary py-2.5">{journalOptions(journals).find((o) => o.value === form.journal_id)?.label}</p>}
              </div>
              <div>
                <label className={labelCls}>Data *</label>
                {editable
                  ? <DateInput value={form.entry_date} onChange={(e) => setForm((f) => ({ ...f, entry_date: e.target.value }))} className={inputCls + ' w-full'} />
                  : <p className="text-sm text-text-primary py-2.5">{fmtDate(form.entry_date)}</p>}
              </div>
              <div className="md:col-span-2">
                <label className={labelCls}>Documento de suporte</label>
                {editable
                  ? <input value={form.document_ref} maxLength={60} onChange={(e) => setForm((f) => ({ ...f, document_ref: e.target.value }))} placeholder="Ex.: Fatura 123, Ata n.º 1" className={inputCls + ' w-full'} />
                  : <p className="text-sm text-text-primary py-2.5">{form.document_ref || '—'}</p>}
              </div>
              <div className="md:col-span-4">
                <label className={labelCls}>Descrição *</label>
                {editable
                  ? <input value={form.description} maxLength={200} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} className={inputCls + ' w-full'} />
                  : <p className="text-sm text-text-primary py-2.5">{form.description}</p>}
              </div>
            </div>

            <div className="border border-border rounded-lg overflow-x-auto">
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted border-b border-border bg-bg-inset/60">
                    <th className="px-3 py-2.5 font-medium w-8">#</th>
                    <th className="px-3 py-2.5 font-medium min-w-[280px]">Conta</th>
                    <th className="px-3 py-2.5 font-medium min-w-[200px]">Descrição da linha</th>
                    <th className="px-3 py-2.5 font-medium text-right w-40">Débito</th>
                    <th className="px-3 py-2.5 font-medium text-right w-40">Crédito</th>
                    {editable && <th className="w-10" />}
                  </tr>
                </thead>
                <tbody>
                  {form.lines.map((l, i) => (
                    <tr key={l.key} className="border-b border-border last:border-0">
                      <td className="px-3 py-2 text-text-muted">{i + 1}</td>
                      <td className="px-3 py-2">
                        {editable
                          ? <Select value={l.account_id} onChange={(v) => setLine(l.key, { account_id: v })} options={accountOptions} placeholder="Escolha a conta" compact />
                          : <span className="text-text-primary">{l.account_label}</span>}
                      </td>
                      <td className="px-3 py-2">
                        {editable
                          ? <input value={l.description} maxLength={200} onChange={(e) => setLine(l.key, { description: e.target.value })} className={cellInputCls} />
                          : <span className="text-text-muted">{l.description}</span>}
                      </td>
                      {['debit', 'credit'].map((side) => (
                        <td key={side} className="px-3 py-2 text-right">
                          {editable
                            ? <input value={l[side]} inputMode="decimal" onChange={(e) => setLine(l.key, { [side]: e.target.value })} placeholder="0,00" className={cellInputCls + ' text-right font-mono'} />
                            : <span className="font-mono">{toNumber(l[side]) ? formatKz(toNumber(l[side])) : ''}</span>}
                        </td>
                      ))}
                      {editable && (
                        <td className="px-2 py-2">
                          <button type="button" title="Retirar a linha" onClick={() => setForm((f) => ({ ...f, lines: f.lines.filter((x) => x.key !== l.key) }))}
                            className="w-7 h-7 inline-flex items-center justify-center rounded-md text-text-muted hover:text-danger transition-colors cursor-pointer"><Trash2 size={14} /></button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-border bg-bg-inset/60">
                    <td colSpan={3} className="px-3 py-3">
                      {editable && <button type="button" onClick={addLine} className="flex items-center gap-1.5 text-accent text-[13px] font-semibold cursor-pointer"><Plus size={14} /> Adicionar linha</button>}
                    </td>
                    <td className="px-3 py-3 text-right font-mono font-semibold text-text-primary">{formatKz(totals.debit)}</td>
                    <td className="px-3 py-3 text-right font-mono font-semibold text-text-primary">{formatKz(totals.credit)}</td>
                    {editable && <td />}
                  </tr>
                </tfoot>
              </table>
            </div>
            <div className="flex justify-end">
              {balanced
                ? <span className="flex items-center gap-1.5 text-[13px] font-semibold text-success"><CheckCircle2 size={15} /> Equilibrado</span>
                : <span className="flex items-center gap-1.5 text-[13px] font-semibold text-amber-500"><AlertTriangle size={15} />
                    {totals.debit === 0 && totals.credit === 0 ? 'Sem valores' : 'Diferença ' + formatKz(Math.abs(totals.diff)) + (totals.diff > 0 ? ' a crédito' : ' a débito')}
                  </span>}
            </div>
          </div>
        )}
      </Modal>

      <Modal open={!!reverse} onClose={() => setReverse(null)} stacked title={reverse ? 'Estornar ' + reverse.entry.label : ''} maxWidthClass="max-w-md">
        {reverse && (
          <div className="flex flex-col gap-4">
            <p className="text-[13px] text-text-muted">É lançado um novo lançamento no mesmo diário, com as mesmas linhas e o débito e o crédito trocados. O lançamento original fica como está.</p>
            <div>
              <label className={labelCls}>Data do estorno *</label>
              <DateInput value={reverse.date} min={reverse.entry.entry_date} onChange={(e) => setReverse((r) => ({ ...r, date: e.target.value }))} className={inputCls + ' w-full'} />
            </div>
            <button type="button" disabled={busy || !reverse.date} className="bg-accent hover:bg-accent-hover disabled:opacity-60 text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer"
              onClick={() => run(() => reverseEntry(reverse.entry.id, reverse.date), (r) => 'Estorno ' + r.label + ' lançado', () => { setReverse(null); setForm(null); loadEntries(); loadJournals(); })}>
              Lançar o estorno
            </button>
          </div>
        )}
      </Modal>

      <Modal open={!!journalForm} onClose={() => setJournalForm(null)} title={journalForm?.id ? 'Editar diário ' + journalForm.code : 'Novo diário'} maxWidthClass="max-w-md">
        {journalForm && (
          <form className="flex flex-col gap-4" onSubmit={(e) => {
            e.preventDefault();
            run(() => (journalForm.id ? updateJournal(journalForm.id, journalForm.name, journalForm.isActive) : createJournal(journalForm.code, journalForm.name)),
              journalForm.id ? 'Diário atualizado' : 'Diário criado', () => { setJournalForm(null); loadJournals(); });
          }}>
            <div>
              <label className={labelCls}>Código *</label>
              <input value={journalForm.code} required readOnly={!!journalForm.id} maxLength={10} onChange={(e) => setJournalForm((f) => ({ ...f, code: e.target.value.toUpperCase() }))}
                placeholder="REG" className={inputCls + ' w-full font-mono' + (journalForm.id ? ' opacity-60 cursor-not-allowed' : '')} />
              <p className="text-[11px] text-text-muted mt-1">{journalForm.id ? 'O código não muda (a numeração usa-o).' : 'Até 10 letras ou algarismos. Aparece no número: REG 2026/0001.'}</p>
            </div>
            <div>
              <label className={labelCls}>Nome *</label>
              <input value={journalForm.name} required maxLength={100} autoFocus onChange={(e) => setJournalForm((f) => ({ ...f, name: e.target.value }))} className={inputCls + ' w-full'} />
            </div>
            {journalForm.id && (
              <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer">
                <input type="checkbox" checked={journalForm.isActive} onChange={(e) => setJournalForm((f) => ({ ...f, isActive: e.target.checked }))} className="w-4 h-4 accent-accent" />
                Diário ativo (um diário inativo não recebe novos lançamentos)
              </label>
            )}
            <button type="submit" disabled={busy} className="bg-accent hover:bg-accent-hover disabled:opacity-60 text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer">
              {journalForm.id ? 'Guardar' : 'Criar diário'}
            </button>
          </form>
        )}
      </Modal>

      <ConfirmDialog open={!!toDelete} title="Apagar o rascunho" danger confirmLabel="Apagar"
        message="Apagar este rascunho? Não tem número: nada fica na numeração do diário."
        onCancel={() => setToDelete(null)}
        onConfirm={() => { const e = toDelete; setToDelete(null); run(() => deleteEntry(e.id), 'Rascunho apagado', () => { setForm(null); loadEntries(); loadJournals(); }); }} />

      <ConfirmDialog open={!!journalToDelete} title="Apagar o diário" danger confirmLabel="Apagar"
        message={journalToDelete ? `Apagar o diário ${journalToDelete.code} - ${journalToDelete.name}?` : ''}
        onCancel={() => setJournalToDelete(null)}
        onConfirm={() => { const j = journalToDelete; setJournalToDelete(null); run(() => deleteJournal(j.id), 'Diário ' + j.code + ' apagado', loadJournals); }} />
    </main>
  );
}

function StatusBadge({ entry }) {
  if (entry.status === 'RASCUNHO') return <span className="text-[11px] font-semibold uppercase text-amber-500 bg-amber-500/10 px-2 py-0.5 rounded">Rascunho</span>;
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-[11px] font-semibold uppercase text-success bg-success/10 px-2 py-0.5 rounded">Lançado</span>
      {entry.reversed_by && <span className="text-[11px] text-text-muted">estornado por {entry.reversed_by}</span>}
      {entry.reversal_of && <span className="text-[11px] text-text-muted">estorno de {entry.reversal_of}</span>}
    </span>
  );
}

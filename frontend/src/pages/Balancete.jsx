import { useEffect, useMemo, useState } from 'react';
import { Scale, Loader2, FileSpreadsheet, FileText, CheckCircle2, AlertTriangle, Search, Plus, Minus, ChevronsUpDown, ChevronsDownUp } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import DateInput from '../components/DateInput';
import { getTrialBalance, getAccountLedger, downloadAccountingFile } from '../api/accounting';
import { extractErrorMessage } from '../utils/errors';
import { formatKz } from '../utils/format';
import { toast } from '../store/toastStore';

// Contabilidade › Balancete: every account with its balance before the period, its debits and credits in it and its
// balance at the end (D devedor, C credor) - an account adds up its sub-accounts, the classes make the totals. Only the
// posted entries count. A row opens the extrato de conta (its lines, with the running balance). As the Plano de contas,
// the tree opens and closes with +/- (all open at first: the balancete is read whole) and a search shows its matches
// with their parents.

const inputCls = 'bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const btnGhost = 'flex items-center gap-1.5 border border-border hover:border-accent text-text-primary hover:text-accent text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50';

const iso = (d) => d.toISOString().slice(0, 10);
const fmtDate = (value) => value.slice(8, 10) + '/' + value.slice(5, 7) + '/' + value.slice(0, 4);
const amount = (v) => (Number(v) ? formatKz(Number(v)) : '');
const side = (v) => { const n = Number(v); return n ? formatKz(Math.abs(n)) + (n > 0 ? ' D' : ' C') : ''; };
const LEVELS = [{ value: '', label: 'Todos os níveis' }, { value: '1', label: 'Só as classes' }, { value: '2', label: 'Até às contas (45)' },
  { value: '3', label: 'Até ao 3.º nível (45.1)' }, { value: '4', label: 'Até ao 4.º nível (45.1.1)' }];

export default function Balancete() {
  const today = new Date();
  const [filters, setFilters] = useState({ date_from: today.getFullYear() + '-01-01', date_to: iso(today), max_level: '', all_accounts: false });
  const [data, setData] = useState(null);
  const [ledger, setLedger] = useState(null); // { account, loading, data }

  useEffect(() => {
    if (!filters.date_from || !filters.date_to) return undefined;
    const timer = setTimeout(() => {
      getTrialBalance(filters).then(setData).catch((err) => toast.error(extractErrorMessage(err, 'Erro ao calcular o balancete')));
    }, 200);
    return () => clearTimeout(timer);
  }, [filters]);

  async function openLedger(account) {
    setLedger({ account, data: null });
    try {
      setLedger({ account, data: await getAccountLedger(account.id, filters.date_from, filters.date_to) });
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao abrir o extrato'));
      setLedger(null);
    }
  }

  function download(kind) {
    const name = 'balancete_' + filters.date_from + '_' + filters.date_to + '.xlsx';
    downloadAccountingFile('/accounting/trial-balance/' + kind, filters, name, kind === 'pdf')
      .catch(() => toast.error('Erro ao gerar o ficheiro'));
  }

  const [search, setSearch] = useState('');
  const [closed, setClosed] = useState(new Set()); // ids of the accounts shown closed
  const rows = data?.accounts || [];
  const byId = useMemo(() => new Map(rows.map((a) => [a.id, a])), [rows]);
  const parents = useMemo(() => new Set(rows.map((a) => a.parent_id).filter(Boolean)), [rows]); // with rows under them
  const searching = search.trim() !== '';
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (q) {  // the matches and their parents (to read them in their place)
      const keep = new Set();
      rows.filter((a) => a.code.startsWith(q) || a.name.toLowerCase().includes(q)).forEach((a) => {
        for (let x = a; x && !keep.has(x.id); x = byId.get(x.parent_id)) keep.add(x.id);
      });
      return rows.filter((a) => keep.has(a.id));
    }
    return rows.filter((a) => {  // shown when no parent is closed
      for (let x = byId.get(a.parent_id); x; x = byId.get(x.parent_id)) if (closed.has(x.id)) return false;
      return true;
    });
  }, [rows, byId, closed, search]);

  function toggle(e, id) {
    e.stopPropagation();  // the row itself opens the extrato
    const next = new Set(closed);
    if (next.has(id)) next.delete(id); else next.add(id);
    setClosed(next);
  }

  const totals = data?.totals;
  const balanced = totals && Number(totals.debit).toFixed(2) === Number(totals.credit).toFixed(2);

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-text-primary flex items-center gap-2.5"><Scale size={22} className="text-accent" /> Balancete</h1>
          <p className="text-text-muted text-sm mt-1">Saldos e movimentos de cada conta no período (D devedor, C credor) - clique numa conta para ver o extrato</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => download('excel')} className={btnGhost}><FileSpreadsheet size={15} /> Excel</button>
          <button type="button" onClick={() => download('pdf')} className={btnGhost}><FileText size={15} /> PDF</button>
        </div>
      </div>

      <div className="flex items-end gap-3 flex-wrap mb-4">
        <div className="w-44">
          <label className={labelCls}>De</label>
          <DateInput value={filters.date_from} onChange={(e) => setFilters((f) => ({ ...f, date_from: e.target.value }))} className={inputCls + ' w-full'} />
        </div>
        <div className="w-44">
          <label className={labelCls}>Até</label>
          <DateInput value={filters.date_to} min={filters.date_from} onChange={(e) => setFilters((f) => ({ ...f, date_to: e.target.value }))} className={inputCls + ' w-full'} />
        </div>
        <div className="w-60">
          <label className={labelCls}>Nível</label>
          <Select value={filters.max_level} onChange={(v) => setFilters((f) => ({ ...f, max_level: v }))} options={LEVELS} />
        </div>
        <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer pb-3">
          <input type="checkbox" checked={filters.all_accounts} onChange={(e) => setFilters((f) => ({ ...f, all_accounts: e.target.checked }))} className="w-4 h-4 accent-accent" />
          Incluir as contas sem movimento
        </label>
      </div>

      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="relative flex-1 max-w-md">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Procurar por código ou descrição" className={inputCls + ' w-full pl-10'} />
        </div>
        {!searching && (
          <>
            <button type="button" onClick={() => setClosed(new Set())} className={btnGhost}><ChevronsUpDown size={15} /> Abrir tudo</button>
            <button type="button" onClick={() => setClosed(new Set(rows.filter((a) => a.level === 1).map((a) => a.id)))} className={btnGhost}>
              <ChevronsDownUp size={15} /> Fechar tudo
            </button>
          </>
        )}
      </div>

      <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted border-b border-border">
              <th className="px-4 py-3 font-medium">Conta</th>
              <th className="px-4 py-3 font-medium text-right">Saldo inicial</th>
              <th className="px-4 py-3 font-medium text-right">Débito</th>
              <th className="px-4 py-3 font-medium text-right">Crédito</th>
              <th className="px-4 py-3 font-medium text-right">Saldo final</th>
            </tr>
          </thead>
          <tbody>
            {data === null && <tr><td colSpan={5} className="py-10 text-center"><Loader2 className="animate-spin text-accent inline" /></td></tr>}
            {data?.accounts.length === 0 && <tr><td colSpan={5} className="py-10 text-center text-text-muted">Nenhum movimento no período</td></tr>}
            {data && rows.length > 0 && shown.length === 0 && <tr><td colSpan={5} className="py-10 text-center text-text-muted">Nenhuma conta encontrada</td></tr>}
            {shown.map((a) => (
              <tr key={a.id} onClick={() => openLedger(a)}
                className={'border-b border-border last:border-0 hover:bg-bg-inset/60 cursor-pointer ' + (a.level === 1 ? 'bg-bg-inset/60 font-semibold' : '')}>
                <td className="relative px-4 py-2">
                  {Array.from({ length: a.level - 1 }, (_, i) => (
                    <span key={i} aria-hidden="true" className="absolute -top-px -bottom-px w-px bg-text-muted/30" style={{ left: 22 + i * 18 }} />
                  ))}
                  <div className="flex items-center gap-3" style={{ paddingLeft: (a.level - 1) * 18 }}>
                    {parents.has(a.id) && !searching ? (
                      <button type="button" onClick={(e) => toggle(e, a.id)} title={closed.has(a.id) ? 'Abrir' : 'Fechar'}
                        className="w-5 h-5 shrink-0 inline-flex items-center justify-center rounded border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer">
                        {closed.has(a.id) ? <Plus size={12} /> : <Minus size={12} />}
                      </button>
                    ) : <span className="w-5 shrink-0" />}
                    <span className={'font-mono w-24 shrink-0 ' + (a.level <= 2 ? 'text-text-primary' : 'text-text-muted')}>{a.code}</span>
                    <span className={'truncate ' + (a.level === 1 ? 'uppercase tracking-wide text-text-primary' : 'text-text-primary')}>{a.name}</span>
                  </div>
                </td>
                <td className="px-4 py-2 text-right font-mono whitespace-nowrap">{side(a.opening)}</td>
                <td className="px-4 py-2 text-right font-mono whitespace-nowrap">{amount(a.debit)}</td>
                <td className="px-4 py-2 text-right font-mono whitespace-nowrap">{amount(a.credit)}</td>
                <td className="px-4 py-2 text-right font-mono whitespace-nowrap">{side(a.closing)}</td>
              </tr>
            ))}
          </tbody>
          {totals && (
            <tfoot>
              <tr className="border-t border-border bg-bg-inset/60 font-semibold">
                <td className="px-4 py-3 text-text-primary">
                  <span className="flex items-center gap-3">
                    Totais
                    {balanced
                      ? <span className="flex items-center gap-1 text-[12px] text-success"><CheckCircle2 size={14} /> Débito = crédito</span>
                      : <span className="flex items-center gap-1 text-[12px] text-amber-500"><AlertTriangle size={14} /> Débito ≠ crédito</span>}
                  </span>
                </td>
                <td className="px-4 py-3 text-right font-mono whitespace-nowrap">{side(totals.opening)}</td>
                <td className="px-4 py-3 text-right font-mono whitespace-nowrap">{amount(totals.debit)}</td>
                <td className="px-4 py-3 text-right font-mono whitespace-nowrap">{amount(totals.credit)}</td>
                <td className="px-4 py-3 text-right font-mono whitespace-nowrap">{side(totals.closing)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      <Modal open={!!ledger} onClose={() => setLedger(null)} size="full" maxWidthClass="max-w-6xl"
        title={ledger ? 'Extrato · ' + ledger.account.code + ' ' + ledger.account.name : ''}
        subtitle={fmtDate(filters.date_from) + ' a ' + fmtDate(filters.date_to) + (ledger?.account.has_children ? ' · com as subcontas' : '')}
        footer={ledger?.data && (
          <div className="flex justify-end px-6 py-4">
            <button type="button" className={btnGhost}
              onClick={() => downloadAccountingFile('/accounting/ledger/' + ledger.account.id + '/pdf', { date_from: filters.date_from, date_to: filters.date_to }, 'extrato_' + ledger.account.code + '_' + filters.date_from + '_' + filters.date_to, true)
                .catch(() => toast.error('Erro ao gerar o PDF'))}>
              <FileText size={15} /> PDF
            </button>
          </div>
        )}>
        {ledger && !ledger.data && <div className="flex justify-center py-12"><Loader2 className="animate-spin text-accent" /></div>}
        {ledger?.data && (
          <div className="border border-border rounded-lg overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-text-muted border-b border-border bg-bg-inset/60">
                  <th className="px-3 py-2.5 font-medium">Data</th>
                  <th className="px-3 py-2.5 font-medium">Lançamento</th>
                  {ledger.account.has_children && <th className="px-3 py-2.5 font-medium">Conta</th>}
                  <th className="px-3 py-2.5 font-medium">Descrição</th>
                  <th className="px-3 py-2.5 font-medium text-right">Débito</th>
                  <th className="px-3 py-2.5 font-medium text-right">Crédito</th>
                  <th className="px-3 py-2.5 font-medium text-right">Saldo</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-border text-text-muted">
                  <td colSpan={ledger.account.has_children ? 6 : 5} className="px-3 py-2">Saldo inicial</td>
                  <td className="px-3 py-2 text-right font-mono">{side(ledger.data.opening) || '0,00'}</td>
                </tr>
                {ledger.data.lines.map((l, i) => (
                  <tr key={i} className="border-b border-border last:border-0">
                    <td className="px-3 py-2 whitespace-nowrap text-text-muted">{fmtDate(l.date)}</td>
                    <td className="px-3 py-2 whitespace-nowrap font-mono">{l.entry}</td>
                    {ledger.account.has_children && <td className="px-3 py-2 whitespace-nowrap font-mono text-text-muted" title={l.account_name}>{l.account_code}</td>}
                    <td className="px-3 py-2 text-text-primary">{l.description}{l.document_ref && <span className="text-text-muted"> · {l.document_ref}</span>}</td>
                    <td className="px-3 py-2 text-right font-mono whitespace-nowrap">{amount(l.debit)}</td>
                    <td className="px-3 py-2 text-right font-mono whitespace-nowrap">{amount(l.credit)}</td>
                    <td className="px-3 py-2 text-right font-mono whitespace-nowrap">{side(l.balance) || '0,00'}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-border bg-bg-inset/60 font-semibold">
                  <td colSpan={ledger.account.has_children ? 4 : 3} className="px-3 py-3">Totais do período</td>
                  <td className="px-3 py-3 text-right font-mono">{amount(ledger.data.total_debit)}</td>
                  <td className="px-3 py-3 text-right font-mono">{amount(ledger.data.total_credit)}</td>
                  <td className="px-3 py-3 text-right font-mono">{side(ledger.data.closing) || '0,00'}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </Modal>
    </main>
  );
}

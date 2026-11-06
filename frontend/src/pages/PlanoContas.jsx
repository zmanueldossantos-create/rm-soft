import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ListTree, Download, Upload, Plus, Pencil, Trash2, Loader2, Search, BookOpen, FileSpreadsheet, Square } from 'lucide-react';
import Modal from '../components/Modal';
import ContasPorOperacao from '../components/ContasPorOperacao';
import ConfirmDialog from '../components/ConfirmDialog';
import { getChart, startChart, downloadChartTemplate, importChart, createAccount, updateAccount, deleteAccount } from '../api/accounting';
import { extractErrorMessage } from '../utils/errors';
import { useCan } from '../utils/permissions';
import { toast } from '../store/toastStore';

// Contabilidade › Plano de contas: the company's chart, fully set by it - the PGC loaded from the system, its own chart
// imported from the Excel model, or typed one account at a time. A class has 1 digit (4), an account 2 (45), the
// sub-accounts follow with points (45.1, 45.1.1); the parent is the code without its last part.

const inputCls = 'bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors';
const labelCls = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block';
const SOURCE_LABEL = { PGC: 'PGC de Angola', PROPRIO: 'Plano próprio (importado)', VAZIO: 'Criado à mão' };

export default function PlanoContas() {
  const can = useCan();
  const canManage = can('accounting:chart_manage');
  const [chart, setChart] = useState(null);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [form, setForm] = useState(null); // { id?, code, name, isActive }
  const [toDelete, setToDelete] = useState(null);
  const [importErrors, setImportErrors] = useState(null);
  const [searchParams] = useSearchParams();
  const [view, setView] = useState(searchParams.get('tab') === 'operacoes' ? 'operations' : 'chart'); // chart | operations
  const fileRef = useRef(null);

  async function load() {
    try {
      setChart(await getChart());
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao carregar o plano de contas'));
    }
  }
  useEffect(() => { load(); }, []);

  async function run(action, success) {
    setBusy(true);
    try {
      const result = await action();
      if (success) toast.success(typeof success === 'function' ? success(result) : success);
      await load();
      return result;
    } catch (err) {
      if (err?.response?.data?.errors) setImportErrors(err.response.data.errors);
      toast.error(extractErrorMessage(err, 'Operação recusada'));
      return null;
    } finally {
      setBusy(false);
    }
  }

  function choose(source) {
    if (source === 'PROPRIO') {
      run(() => startChart('PROPRIO'), 'Plano próprio: descarregue o modelo, preencha-o e importe-o');
      return;
    }
    run(() => startChart(source), source === 'PGC' ? 'PGC carregado' : 'Plano vazio: crie as contas uma a uma');
  }

  function onFile(e) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setImportErrors(null);
    run(() => importChart(file), (r) => `Importação concluída: ${r.created} criada(s), ${r.renamed} renomeada(s), ${r.unchanged} sem alteração`);
  }

  async function saveForm() {
    const ok = await run(
      () => (form.id ? updateAccount(form.id, form.name, form.isActive) : createAccount(form.code, form.name)),
      form.id ? 'Conta atualizada' : 'Conta ' + form.code + ' criada',
    );
    if (ok) setForm(null);
  }

  const accounts = chart?.accounts || [];
  const shown = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return accounts;
    return accounts.filter((a) => a.code.startsWith(q) || a.name.toLowerCase().includes(q));
  }, [accounts, search]);

  if (!chart) {
    return <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-9 flex justify-center"><Loader2 className="animate-spin text-accent" /></main>;
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-text-primary flex items-center gap-2.5"><ListTree size={22} className="text-accent" /> Plano de contas</h1>
          <p className="text-text-muted text-sm mt-1">
            {chart.source ? 'Origem: ' + SOURCE_LABEL[chart.source] + ' · ' : ''}{accounts.length} conta(s) · Classe: 1 algarismo (4), conta: 2 (45), subcontas com pontos (45.1, 45.1.1)
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button type="button" onClick={() => downloadChartTemplate().catch(() => toast.error('Erro ao descarregar o modelo'))}
            className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary hover:text-accent text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer">
            <Download size={15} /> Modelo Excel
          </button>
          {canManage && accounts.length > 0 && (
            <>
              <button type="button" disabled={busy} onClick={() => fileRef.current?.click()}
                className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary hover:text-accent text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50">
                <Upload size={15} /> Importar
              </button>
              <button type="button" disabled={busy} onClick={() => choose('PGC')} title="Acrescenta as contas do PGC que faltam - nenhuma conta é apagada nem renomeada"
                className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary hover:text-accent text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50">
                <BookOpen size={15} /> Carregar o PGC
              </button>
              <button type="button" onClick={() => setForm({ code: '', name: '', isActive: true })}
                className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer">
                <Plus size={15} /> Nova conta
              </button>
            </>
          )}
          <input ref={fileRef} type="file" accept=".xlsx" onChange={onFile} className="hidden" />
        </div>
      </div>

      {accounts.length > 0 && (
        <div className="flex gap-1 mb-5 border-b border-border">
          {[['chart', 'Plano de contas'], ['operations', 'Contas por operação']].map(([key, label]) => (
            <button key={key} type="button" onClick={() => setView(key)}
              className={'px-4 py-2.5 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer ' + (view === key ? 'border-accent text-accent' : 'border-transparent text-text-muted hover:text-text-primary')}>
              {label}
            </button>
          ))}
        </div>
      )}

      {accounts.length > 0 && view === 'operations' ? (
        <ContasPorOperacao accounts={accounts} canManage={canManage} onChartChanged={load} />
      ) : accounts.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-6">
          <p className="font-display font-semibold text-text-primary mb-1">Como quer começar o plano de contas?</p>
          <p className="text-text-muted text-[13px] mb-5">Pode mudar depois: o plano continua editável (importar, acrescentar, renomear, desativar).</p>
          {!canManage && <p className="text-[13px] text-text-muted">Só quem configura o plano de contas pode fazer esta escolha.</p>}
          {canManage && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              {[
                ['PGC', BookOpen, 'PGC de Angola', 'O Plano Geral de Contabilidade carregado pelo sistema. Depois acrescente as subcontas da empresa.'],
                ['PROPRIO', FileSpreadsheet, 'Plano próprio', 'Descarregue o modelo Excel, cole o plano da empresa (ou o do contabilista) e importe-o.'],
                ['VAZIO', Square, 'Começar vazio', 'Crie as contas uma a uma, a partir das classes.'],
              ].map(([source, Icon, title, text]) => (
                <button key={source} type="button" disabled={busy} onClick={() => choose(source)}
                  className="text-left bg-bg-inset border border-border hover:border-accent rounded-lg p-4 transition-colors cursor-pointer disabled:opacity-50">
                  <Icon size={20} className="text-accent mb-2" />
                  <p className="text-[14px] font-semibold text-text-primary mb-1">{title}</p>
                  <p className="text-[12px] text-text-muted">{text}</p>
                </button>
              ))}
            </div>
          )}
          {canManage && chart.source === 'PROPRIO' && (
            <div className="flex items-center gap-2 mt-5">
              <button type="button" disabled={busy} onClick={() => fileRef.current?.click()}
                className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50">
                <Upload size={15} /> Importar o plano preenchido
              </button>
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="relative mb-4 max-w-md">
            <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Procurar por código ou descrição" className={inputCls + ' w-full pl-10'} />
          </div>
          <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
            {shown.length === 0 && <p className="text-text-muted text-[13px] text-center py-10">Nenhuma conta encontrada</p>}
            {shown.map((a) => (
              <div key={a.id} className={'relative flex items-center gap-3 px-4 py-2 border-b border-border last:border-0 ' + (a.level === 1 ? 'bg-bg-inset/60' : '') + (a.is_active ? '' : ' opacity-50')}>
                {/* Indentation guides: one vertical line per ancestor level, like an editor's */}
                {Array.from({ length: a.level - 1 }, (_, i) => (
                  <span key={i} aria-hidden="true" className="absolute -top-px -bottom-px w-px bg-text-muted/30" style={{ left: 22 + i * 18 }} />
                ))}
                <div className="flex-1 min-w-0 flex items-center gap-3" style={{ paddingLeft: (a.level - 1) * 18 }}>
                  <span className={'font-mono text-[13px] w-24 shrink-0 ' + (a.level <= 2 ? 'text-text-primary font-semibold' : 'text-text-muted')}>{a.code}</span>
                  <span className={'text-[13px] truncate ' + (a.level === 1 ? 'font-semibold text-text-primary uppercase tracking-wide' : 'text-text-primary')}>{a.name}</span>
                  {!a.is_active && <span className="text-[10px] font-semibold uppercase text-text-muted bg-bg-inset px-1.5 py-0.5 rounded">Inativa</span>}
                </div>
                {canManage && (
                  <div className="flex items-center gap-1.5 shrink-0">
                    <button type="button" title="Nova subconta" onClick={() => setForm({ code: a.code + (a.level === 1 ? '' : '.'), name: '', isActive: true })}
                      className="w-7 h-7 inline-flex items-center justify-center rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer"><Plus size={13} /></button>
                    <button type="button" title="Editar" onClick={() => setForm({ id: a.id, code: a.code, name: a.name, isActive: a.is_active })}
                      className="w-7 h-7 inline-flex items-center justify-center rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer"><Pencil size={13} /></button>
                    <button type="button" title={a.has_children ? 'Tem subcontas - não pode ser apagada' : a.in_use ? 'Em uso: ' + a.in_use : 'Apagar'} disabled={a.has_children || !!a.in_use} onClick={() => setToDelete(a)}
                      className="w-7 h-7 inline-flex items-center justify-center rounded-md border border-border text-text-muted hover:text-danger hover:border-danger transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"><Trash2 size={13} /></button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      <Modal open={!!form} onClose={() => setForm(null)} title={form?.id ? 'Editar conta ' + form.code : 'Nova conta'} maxWidthClass="max-w-md">
        {form && (
          <form onSubmit={(e) => { e.preventDefault(); saveForm(); }} className="flex flex-col gap-4">
            <div>
              <label className={labelCls}>Código *</label>
              <input value={form.code} required readOnly={!!form.id} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                placeholder="45.1.1" className={inputCls + ' w-full font-mono' + (form.id ? ' opacity-60 cursor-not-allowed' : '')} />
              <p className="text-[11px] text-text-muted mt-1">{form.id ? 'O código não muda (os lançamentos apontam para ele).' : 'A conta-mãe tem de existir: 45.1.1 precisa de 45.1.'}</p>
            </div>
            <div>
              <label className={labelCls}>Descrição *</label>
              <input value={form.name} required maxLength={200} autoFocus onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} className={inputCls + ' w-full'} />
            </div>
            {form.id && (
              <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer">
                <input type="checkbox" checked={form.isActive} onChange={(e) => setForm((f) => ({ ...f, isActive: e.target.checked }))} className="w-4 h-4 accent-accent" />
                Conta ativa
              </label>
            )}
            <button type="submit" disabled={busy} className="bg-accent hover:bg-accent-hover disabled:opacity-60 text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer">
              {busy ? 'A guardar...' : form.id ? 'Guardar' : 'Criar conta'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={!!importErrors} onClose={() => setImportErrors(null)} title="Linhas a corrigir no ficheiro" maxWidthClass="max-w-xl">
        {importErrors && (
          <div className="flex flex-col gap-3">
            <p className="text-[13px] text-text-muted">Nada foi importado. Corrija estas linhas no Excel e importe de novo.</p>
            <ul className="max-h-[50vh] overflow-y-auto flex flex-col gap-1 text-[13px] text-danger">
              {importErrors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        )}
      </Modal>

      <ConfirmDialog open={!!toDelete} title="Apagar a conta" danger confirmLabel="Apagar"
        message={toDelete ? `Apagar a conta ${toDelete.code} - ${toDelete.name}?` : ''}
        onCancel={() => setToDelete(null)}
        onConfirm={() => { const a = toDelete; setToDelete(null); run(() => deleteAccount(a.id), 'Conta ' + a.code + ' apagada'); }} />
    </main>
  );
}

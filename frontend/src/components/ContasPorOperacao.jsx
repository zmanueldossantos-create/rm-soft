import { useEffect, useMemo, useState } from 'react';
import { Loader2, Wand2, GitBranchPlus } from 'lucide-react';
import Select from './Select';
import { getMappings, setMapping, setMappingOptions, applyMappingSuggestions, syncSubaccounts } from '../api/accounting';
import { extractErrorMessage } from '../utils/errors';
import { toast } from '../store/toastStore';

// Contabilidade › Contas por operação: which account of the chart each kind of operation goes to (sales, VAT, stock,
// treasury...), and the parents under which the system makes one sub-account per bank account, till, customer and
// supplier. The PGC accounts are suggested; the company (or its accountant) changes any of them.

export default function ContasPorOperacao({ accounts, canManage, onChartChanged }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { getMappings().then(setData).catch((err) => toast.error(extractErrorMessage(err, 'Erro ao carregar'))); }, []);

  const options = useMemo(() => [{ value: '', label: '— Nenhuma —' },
    ...accounts.filter((a) => a.is_active).map((a) => ({ value: a.id, label: a.code + ' · ' + a.name }))], [accounts]);
  const groups = useMemo(() => {
    const out = [];
    (data?.operations || []).forEach((op) => {
      let group = out.find((g) => g.name === op.group);
      if (!group) { group = { name: op.group, rows: [] }; out.push(group); }
      group.rows.push(op);
    });
    return out;
  }, [data]);

  async function run(action, success) {
    setBusy(true);
    try {
      const result = await action();
      if (result?.operations) setData(result);
      if (success) toast.success(typeof success === 'function' ? success(result) : success);
      return result;
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Operação recusada'));
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function sync() {
    const result = await run(() => syncSubaccounts());
    if (!result) return;
    if (result.created) toast.success(result.created + ' subconta(s) criada(s)');
    else if (!result.missing_parent.length) toast.success('Todas as subcontas já existem');
    if (result.missing_parent.length) toast.error('Sem conta-mãe definida: ' + result.missing_parent.join(', '));
    if (result.created) onChartChanged();
  }

  if (!data) return <div className="flex justify-center py-12"><Loader2 className="animate-spin text-accent" /></div>;
  const missing = data.operations.filter((o) => !o.account_id).length;

  return (
    <>
      <div className="flex items-start justify-between gap-4 flex-wrap mb-4">
        <p className="text-text-muted text-[13px] max-w-3xl">
          A conta do plano para onde vai cada tipo de operação. As contas do PGC são sugeridas; mude qualquer uma (um plano próprio usa os seus códigos).
          {missing > 0 && <span className="text-amber-500"> {missing} operação(ões) sem conta.</span>}
        </p>
        {canManage && (
          <div className="flex items-center gap-2 flex-wrap">
            <button type="button" disabled={busy} onClick={() => run(() => applyMappingSuggestions(), (r) => r.applied ? r.applied + ' sugestão(ões) aplicada(s)' : 'Nenhuma sugestão a aplicar')}
              title="Preenche as operações ainda sem conta com a conta do PGC, quando o plano a tem"
              className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary hover:text-accent text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50">
              <Wand2 size={15} /> Aplicar sugestões do PGC
            </button>
            <button type="button" disabled={busy} onClick={sync}
              title="Cria a subconta de cada conta bancária, caixa, cliente e fornecedor que ainda não a tem"
              className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[13px] font-semibold px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50">
              <GitBranchPlus size={15} /> Criar subcontas
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-col gap-4">
        {groups.map((g) => (
          <div key={g.name} className="bg-bg-elevated border border-border rounded-lg">
            <p className="px-5 py-3 border-b border-border text-[11px] font-semibold uppercase tracking-wide text-text-muted">{g.name}</p>
            {g.name === 'Subcontas criadas pelo sistema' && (
              <div className="px-5 py-3 border-b border-border flex items-center gap-5 flex-wrap text-[13px] text-text-primary">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={data.subaccount_per_customer} disabled={!canManage || busy}
                    onChange={(e) => run(() => setMappingOptions(e.target.checked, data.subaccount_per_supplier), 'Opção guardada')} className="w-4 h-4 accent-accent" />
                  Uma subconta por cliente
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" checked={data.subaccount_per_supplier} disabled={!canManage || busy}
                    onChange={(e) => run(() => setMappingOptions(data.subaccount_per_customer, e.target.checked), 'Opção guardada')} className="w-4 h-4 accent-accent" />
                  Uma subconta por fornecedor
                </label>
                <span className="text-[12px] text-text-muted">Sem subconta, os movimentos vão para a própria conta-mãe.</span>
              </div>
            )}
            {g.rows.map((op) => (
              <div key={op.key} className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-2 md:gap-4 items-center px-5 py-2.5 border-b border-border last:border-0">
                <div>
                  <p className="text-[13px] text-text-primary">{op.label}{op.kind === 'parent' && <span className="text-text-muted"> · conta-mãe</span>}</p>
                  <p className="text-[11px] text-text-muted">{op.suggestion ? 'Sugestão PGC: ' + op.suggestion : 'Sem sugestão - decide o contabilista'}</p>
                </div>
                <Select value={op.account_id || ''} disabled={!canManage || busy} options={options} placeholder="— Nenhuma —"
                  onChange={(v) => run(() => setMapping(op.key, v), 'Conta guardada')} />
              </div>
            ))}
          </div>
        ))}
      </div>
    </>
  );
}

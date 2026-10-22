import { useEffect, useMemo, useState } from 'react';
import { FileSignature, Loader2, Save } from 'lucide-react';
import Select from './Select';
import { getCompanyContract, getPlanCatalog, kz, limitText, listPlans, saveCompanyContract } from '../api/plans';
import { extractErrorMessage } from '../utils/errors';
import { useToastState } from './Toaster';
import { toast } from '../store/toastStore';

// Empresas > Editar > «Contrato»: the company's plan, how it pays, until when, its add-ons - and what it uses of it.
// «Guardar novo contrato» makes a new contract (a renewal, a change of plan): the current one goes to the history.
// It lives inside the company's form, so its buttons are never «submit».

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors';
const PRICE_OF = { MENSAL: 'price_monthly', TRIMESTRAL: 'price_quarterly', SEMESTRAL: 'price_semiannual', ANUAL: 'price_annual', VITALICIA: 'price_lifetime' };
const MONTHS = { MENSAL: 1, TRIMESTRAL: 3, SEMESTRAL: 6, ANUAL: 12 };

const iso = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
const today = () => iso(new Date());
export const dateText = (value) => (value ? value.split('-').reverse().join('/') : '');

// the same rule as the server: the period paid ends the day before the same date, so many months later
export function periodEnd(billing, start, trialDays = 15) {
  if (!start || billing === 'VITALICIA') return null;
  const [y, m, d] = start.split('-').map(Number);
  if (billing === 'TESTE') return iso(new Date(y, m - 1, d + trialDays - 1));
  const months = MONTHS[billing];
  const target = new Date(y, m - 1 + months, 1);
  const last = new Date(target.getFullYear(), target.getMonth() + 1, 0).getDate();
  return iso(new Date(target.getFullYear(), target.getMonth(), Math.min(d, last) - 1));
}

function Field({ label, children, className = '' }) {
  return (
    <div className={className}>
      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{label}</label>
      {children}
    </div>
  );
}

export default function ContractPanel({ companyId, defaultMode = 'SAAS', onChanged }) {
  const [catalog, setCatalog] = useState(null);
  const [plans, setPlans] = useState([]);
  const [view, setView] = useState(null);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useToastState('error');

  function formFrom(current, planList) {
    const plan = current ? current.plan_id : (planList.find((p) => p.is_popular) || planList[0])?.id || '';
    const addons = {};
    (Object.keys(current?.addons || {})).forEach((k) => { addons[k] = String(current.addons[k]); });
    return {
      plan_id: plan, deployment_mode: current?.deployment_mode || defaultMode, billing: current?.billing || 'ANUAL',
      start_date: today(), endMode: 'AUTO', end_date: '', maintenance_until: '', addons, price: '', notes: '',
    };
  }

  async function load() {
    try {
      const [c, p, v] = await Promise.all([getPlanCatalog(), listPlans(), getCompanyContract(companyId)]);
      setCatalog(c);
      setPlans(p);
      setView(v);
      setForm(formFrom(v.current, p.filter((x) => x.is_active)));
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível carregar o contrato'));
    }
  }
  useEffect(() => { load(); }, [companyId]); // eslint-disable-line react-hooks/exhaustive-deps

  const plan = useMemo(() => plans.find((p) => p.id === form?.plan_id), [plans, form?.plan_id]);
  const set = (field, value) => setForm((prev) => ({ ...prev, [field]: value }));
  const autoEnd = form ? periodEnd(form.billing, form.start_date, catalog?.trial_days) : null;
  const suggestedPrice = plan && form ? plan[PRICE_OF[form.billing]] : null;

  async function save() {
    setSaving(true);
    setError('');
    try {
      const addons = {};
      Object.entries(form.addons).forEach(([k, v]) => { if (v !== '' && Number(v) > 0) addons[k] = parseInt(v, 10); });
      const result = await saveCompanyContract(companyId, {
        plan_id: form.plan_id, deployment_mode: form.deployment_mode, billing: form.billing, start_date: form.start_date,
        end_date: form.endMode === 'DATA' && form.end_date ? form.end_date : null, no_end: form.endMode === 'SEM_FIM',
        maintenance_until: form.billing === 'VITALICIA' && form.maintenance_until ? form.maintenance_until : null,
        addons, price: form.price === '' ? (suggestedPrice ?? null) : Number(form.price), notes: form.notes || null,
      });
      setView(result);
      setForm(formFrom(result.current, plans.filter((x) => x.is_active)));
      toast.success('Contrato guardado: ' + result.current.plan_name);
      onChanged?.(result);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível guardar o contrato'));
    } finally {
      setSaving(false);
    }
  }

  if (!view || !catalog || !form) {
    return error ? null : <div className="flex items-center justify-center py-16 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>;
  }

  const billingLabel = (code) => catalog.billing_types.find((b) => b.code === code)?.label || code;
  const modeLabel = (code) => catalog.deployment_modes.find((m) => m.code === code)?.label || code;
  const current = view.current;
  const planOptions = plans.filter((p) => p.is_active || p.id === form.plan_id).map((p) => ({ value: p.id, label: p.name + (p.is_active ? '' : ' (inativo)') }));
  const billingOptions = catalog.billing_types
    .filter((b) => b.code !== 'VITALICIA' || form.deployment_mode === 'LOCAL')
    .map((b) => ({ value: b.code, label: b.label }));

  return (
    <div className="flex flex-col gap-5">
      {/* the current contract and what the company uses of it */}
      <div className="bg-bg-elevated border border-border rounded-lg p-4 flex flex-col gap-3">
        {current ? (
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-text-muted">Contrato atual</div>
              <div className="text-[17px] font-semibold text-text-primary flex items-center gap-2"><FileSignature size={17} className="text-accent" />{current.plan_name}</div>
              <div className="text-[12px] text-text-muted mt-0.5">
                {billingLabel(current.billing)} · {modeLabel(current.deployment_mode)} · desde {dateText(current.start_date)}
                {current.billing === 'VITALICIA'
                  ? ' · sem fim' + (current.maintenance_until ? ' · manutenção até ' + dateText(current.maintenance_until) : '')
                  : current.end_date ? ' · até ' + dateText(current.end_date) : ' · sem data de fim'}
                {current.price != null ? ' · ' + kz(current.price) : ''}
              </div>
              {Object.keys(current.addons || {}).length > 0 && (
                <div className="text-[12px] text-accent mt-0.5">
                  Acréscimos: {Object.entries(current.addons).map(([k, v]) => '+' + v + ' ' + (catalog.limits.find((l) => l.code === k)?.label.toLowerCase() || k)).join(', ')}
                </div>
              )}
              {current.notes && <div className="text-[12px] text-text-muted italic mt-0.5">{current.notes}</div>}
            </div>
          </div>
        ) : (
          <p className="text-[13px] text-amber-500 [.light_&]:text-amber-700">Esta empresa ainda não tem contrato: nada está limitado.</p>
        )}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {catalog.limits.map((lim) => {
            const used = view.usage[lim.code];
            const max = view.limits ? view.limits[lim.code] : null;
            const full = max != null && used >= max;
            return (
              <div key={lim.code} className="bg-bg-inset border border-border rounded-md px-3 py-2">
                <div className="text-[11px] text-text-muted">{lim.label}</div>
                <div className={'text-[15px] font-semibold font-mono ' + (full ? 'text-amber-500 [.light_&]:text-amber-700' : 'text-text-primary')}>
                  {used} <span className="text-text-muted text-[12px]">/ {limitText(max)}</span>
                </div>
                {max != null && max > 0 && (
                  <div className="h-1 bg-border rounded mt-1 overflow-hidden">
                    <div className={'h-full ' + (full ? 'bg-amber-500' : 'bg-accent')} style={{ width: Math.min(100, (used / max) * 100) + '%' }} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* a new contract */}
      <div className="border border-border rounded-lg p-4 flex flex-col gap-4">
        <div>
          <h4 className="text-[14px] font-semibold text-text-primary">{current ? 'Novo contrato (renovação, mudança de plano, acréscimos)' : 'Primeiro contrato'}</h4>
          <p className="text-[12px] text-text-muted">O contrato atual passa para o histórico. Recusado se a empresa já usar mais do que o novo plano permite.</p>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <Field label="Plano *"><Select value={form.plan_id} onChange={(v) => set('plan_id', v)} options={planOptions} placeholder="Selecionar" /></Field>
          <Field label="Instalação *">
            <Select value={form.deployment_mode} onChange={(v) => setForm((prev) => ({ ...prev, deployment_mode: v, billing: v !== 'LOCAL' && prev.billing === 'VITALICIA' ? 'ANUAL' : prev.billing }))}
              options={catalog.deployment_modes.map((m) => ({ value: m.code, label: m.label }))} />
          </Field>
          <Field label="Pagamento *"><Select value={form.billing} onChange={(v) => set('billing', v)} options={billingOptions} /></Field>
          <Field label="Início *"><input type="date" value={form.start_date} onChange={(e) => set('start_date', e.target.value)} className={inputClass} /></Field>
        </div>

        {form.billing === 'VITALICIA' ? (
          <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
            <Field label="Manutenção até" className="sm:col-span-1">
              <input type="date" value={form.maintenance_until} onChange={(e) => set('maintenance_until', e.target.value)} className={inputClass} />
            </Field>
            <p className="sm:col-span-3 self-end text-[12px] text-text-muted pb-2">
              Vitalícia: funciona para sempre, sem data de fim. Vazio: 1 ano de atualizações incluído
              (até {dateText(periodEnd('ANUAL', form.start_date))}); depois, a manutenção anual.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Fim</span>
            <div className="flex items-center gap-4 flex-wrap text-[13px] text-text-primary">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input type="radio" checked={form.endMode === 'AUTO'} onChange={() => set('endMode', 'AUTO')} className="accent-accent" />
                Fim do período pago {autoEnd && <span className="font-mono text-text-muted">({dateText(autoEnd)})</span>}
              </label>
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input type="radio" checked={form.endMode === 'DATA'} onChange={() => set('endMode', 'DATA')} className="accent-accent" /> Outra data
              </label>
              {form.endMode === 'DATA' && <input type="date" value={form.end_date} onChange={(e) => set('end_date', e.target.value)} className={inputClass + ' max-w-[180px]'} />}
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input type="radio" checked={form.endMode === 'SEM_FIM'} onChange={() => set('endMode', 'SEM_FIM')} className="accent-accent" /> Sem data de fim
              </label>
            </div>
          </div>
        )}

        <div className="flex flex-col gap-2">
          <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Acréscimos ao plano (opcional)</span>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {catalog.limits.map((lim) => (
              <div key={lim.code}>
                <div className="text-[11px] text-text-muted mb-1 truncate" title={lim.label}>+ {lim.label}</div>
                <input type="number" min="0" step="1" value={form.addons[lim.code] || ''} disabled={plan && plan.limits[lim.code] == null}
                  onChange={(e) => setForm((prev) => ({ ...prev, addons: { ...prev.addons, [lim.code]: e.target.value } }))}
                  placeholder="0" className={inputClass + ' disabled:opacity-40'} />
                <div className="text-[11px] text-text-muted mt-1 font-mono">{plan && plan.limits[lim.code] == null ? 'ilimitado no plano' : limitText(plan?.limits[lim.code]) + ' no plano'}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <Field label="Valor acordado (Kz)">
            <input type="number" min="0" step="0.01" value={form.price} onChange={(e) => set('price', e.target.value)}
              placeholder={suggestedPrice != null ? 'Plano: ' + Number(suggestedPrice).toLocaleString('pt-PT') : 'Sob cotação'} className={inputClass} />
          </Field>
          <Field label="Notas" className="sm:col-span-3"><input value={form.notes} onChange={(e) => set('notes', e.target.value)} maxLength={500} placeholder="Ex.: desconto de lançamento, pago por transferência" className={inputClass} /></Field>
        </div>

        <button type="button" onClick={save} disabled={saving || !form.plan_id || (form.endMode === 'DATA' && !form.end_date && form.billing !== 'VITALICIA')}
          className="self-start flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer">
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
          {saving ? 'A guardar...' : 'Guardar novo contrato'}
        </button>
      </div>

      {/* the history */}
      {view.history.length > 0 && (
        <div className="border border-border rounded-md overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-bg-inset text-[11px] uppercase tracking-wide text-text-muted">
              <tr>
                <th className="text-left px-3 py-2.5 font-medium">Plano</th>
                <th className="text-left px-3 py-2.5 font-medium">Pagamento</th>
                <th className="text-left px-3 py-2.5 font-medium">Instalação</th>
                <th className="text-left px-3 py-2.5 font-medium">Período</th>
                <th className="text-right px-3 py-2.5 font-medium">Valor</th>
                <th className="text-left px-3 py-2.5 font-medium">Notas</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {view.history.map((c) => (
                <tr key={c.id} className={c.is_current ? '' : 'opacity-70'}>
                  <td className="px-3 py-2 text-[13px] text-text-primary font-medium">
                    {c.plan_name} {c.is_current && <span className="ml-1 text-[10px] font-semibold uppercase text-success">atual</span>}
                  </td>
                  <td className="px-3 py-2 text-[12px] text-text-primary">{billingLabel(c.billing)}</td>
                  <td className="px-3 py-2 text-[12px] text-text-muted">{c.deployment_mode === 'LOCAL' ? 'Local' : 'SaaS'}</td>
                  <td className="px-3 py-2 font-mono text-[12px] text-text-primary whitespace-nowrap">
                    {dateText(c.start_date)} → {c.billing === 'VITALICIA' ? 'sem fim' : c.end_date ? dateText(c.end_date) : 'sem fim'}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-[12px] text-text-primary">{kz(c.price)}</td>
                  <td className="px-3 py-2 text-[12px] text-text-muted">{c.notes || '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

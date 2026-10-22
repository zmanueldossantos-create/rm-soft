import { useEffect, useState } from 'react';
import { Check, Layers, Loader2, Pencil, Plus, Save, Star, X } from 'lucide-react';
import Modal from '../components/Modal';
import { getPlanCatalog, kz, limitText, listPlans, savePlan } from '../api/plans';
import { extractErrorMessage } from '../utils/errors';
import { useToastState } from '../components/Toaster';
import { toast } from '../store/toastStore';

// Planos (menu of the platform): what each plan allows - the limits (users, modules, shops, tills, warehouses) and the
// options (suppliers, guias, the assistant...). The sector modules say what business a company runs; the plan says how
// far it goes. A change applies at once to the companies on the plan. What the law requires (invoicing, SAF-T, AGT) is
// in every plan and never appears here.

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors';
const PRICES = [
  ['price_monthly', 'Mensal'], ['price_quarterly', 'Trimestral'], ['price_semiannual', 'Semestral'], ['price_annual', 'Anual'],
];

function Field({ label, children, className = '' }) {
  return (
    <div className={className}>
      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{label}</label>
      {children}
    </div>
  );
}

export default function Planos() {
  const [catalog, setCatalog] = useState(null);
  const [plans, setPlans] = useState(null);
  const [editing, setEditing] = useState(null); // null closed, {} new, a plan to edit
  const [error, setError] = useToastState('error');

  async function load() {
    try {
      const [c, p] = await Promise.all([getPlanCatalog(), listPlans()]);
      setCatalog(c);
      setPlans(p);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível carregar os planos'));
    }
  }
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
        <div>
          <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
            <Layers size={22} className="text-accent" /> Planos
          </h2>
          <p className="text-text-muted text-sm max-w-3xl">
            O que cada plano permite. Os módulos dizem o negócio da empresa; o plano diz até onde vai. Uma alteração aplica-se
            logo às empresas do plano. Faturação, SAF-T, envio à AGT e IVA estão sempre incluídos, em todos os planos.
          </p>
        </div>
        <button type="button" onClick={() => setEditing({})} disabled={!catalog}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer">
          <Plus size={16} /> Novo plano
        </button>
      </div>

      {!plans || !catalog ? (
        !error && <div className="flex items-center justify-center py-20 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {plans.map((p) => (
            <div key={p.id} className={'relative bg-bg-elevated border rounded-lg p-5 flex flex-col gap-4 ' + (p.is_popular ? 'border-accent' : 'border-border') + (p.is_active ? '' : ' opacity-60')}>
              {p.is_popular && (
                <span className="absolute -top-2.5 right-4 flex items-center gap-1 bg-accent text-white text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded">
                  <Star size={10} /> Popular
                </span>
              )}
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h3 className="text-[17px] font-semibold text-text-primary">{p.name}</h3>
                  {p.description && <p className="text-[12px] text-text-muted mt-0.5">{p.description}</p>}
                </div>
                <button type="button" onClick={() => setEditing(p)} aria-label="Editar" title="Editar"
                  className="shrink-0 w-8 h-8 flex items-center justify-center rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent cursor-pointer">
                  <Pencil size={13} />
                </button>
              </div>

              <div>
                {p.price_annual != null ? (
                  <>
                    <div className="text-[22px] font-semibold text-text-primary font-mono">{kz(p.price_annual)}<span className="text-[12px] text-text-muted font-sans"> / ano</span></div>
                    {p.price_monthly != null && <div className="text-[12px] text-text-muted">ou {kz(p.price_monthly)} / mês</div>}
                  </>
                ) : (
                  <div className="text-[18px] font-semibold text-text-primary">Sob cotação</div>
                )}
                {p.price_lifetime != null && (
                  <div className="text-[12px] text-text-muted mt-1">
                    Vitalícia (local): {kz(p.price_lifetime)}{p.maintenance_percent != null ? ' · manutenção ' + Number(p.maintenance_percent) + '%/ano' : ''}
                  </div>
                )}
              </div>

              <ul className="flex flex-col gap-1.5 border-t border-border pt-3 text-[13px]">
                {catalog.limits.map((lim) => (
                  <li key={lim.code} className="flex items-center justify-between gap-2">
                    <span className="text-text-muted">{lim.label}</span>
                    <span className="font-mono text-text-primary">{limitText(p.limits[lim.code])}</span>
                  </li>
                ))}
              </ul>
              <ul className="flex flex-col gap-1.5 border-t border-border pt-3 text-[13px]">
                {catalog.options.map((o) => {
                  const on = p.options.includes(o.code);
                  return (
                    <li key={o.code} className={'flex items-start gap-2 ' + (on ? 'text-text-primary' : 'text-text-muted line-through opacity-70')}>
                      {on ? <Check size={14} className="text-success shrink-0 mt-0.5" /> : <X size={14} className="shrink-0 mt-0.5" />}
                      {o.label}
                    </li>
                  );
                })}
              </ul>
              <div className="mt-auto flex items-center justify-between text-[12px] text-text-muted border-t border-border pt-3">
                <span>{p.companies === 1 ? '1 empresa' : p.companies + ' empresas'}</span>
                {!p.is_active && <span className="text-amber-500 [.light_&]:text-amber-700">Inativo - não se escolhe para novos contratos</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && catalog && (
        <PlanForm plan={editing.id ? editing : null} catalog={catalog} nextOrder={(plans?.length || 0) + 1}
          onClose={() => setEditing(null)} onSaved={async (saved) => { setEditing(null); toast.success('Plano «' + saved.name + '» guardado'); await load(); }} />
      )}
    </main>
  );
}

function PlanForm({ plan, catalog, nextOrder, onClose, onSaved }) {
  const [form, setForm] = useState(() => {
    const base = plan || { name: '', description: '', limits: {}, options: [], is_popular: false, is_active: true, sort_order: nextOrder };
    const limits = {};
    catalog.limits.forEach((lim) => { limits[lim.code] = base.limits[lim.code] == null ? '' : String(base.limits[lim.code]); });
    const prices = {};
    [...PRICES.map(([k]) => k), 'price_lifetime', 'maintenance_percent'].forEach((k) => { prices[k] = base[k] == null ? '' : String(Number(base[k])); });
    return { ...base, description: base.description || '', ...prices, limits };
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useToastState('error');
  const set = (field, value) => setForm((prev) => ({ ...prev, [field]: value }));
  const setLimit = (code, value) => setForm((prev) => ({ ...prev, limits: { ...prev.limits, [code]: value } }));
  const toggleOption = (code) => set('options', form.options.includes(code) ? form.options.filter((c) => c !== code) : [...form.options, code]);
  const num = (v) => (v === '' || v == null ? null : Number(v));

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const limits = {};
      Object.entries(form.limits).forEach(([code, value]) => { limits[code] = value === '' ? null : parseInt(value, 10); });
      const saved = await savePlan(plan?.id, {
        name: form.name, description: form.description || null, limits, options: form.options,
        is_popular: form.is_popular, is_active: form.is_active, sort_order: parseInt(form.sort_order, 10) || 0,
        price_monthly: num(form.price_monthly), price_quarterly: num(form.price_quarterly), price_semiannual: num(form.price_semiannual),
        price_annual: num(form.price_annual), price_lifetime: num(form.price_lifetime), maintenance_percent: num(form.maintenance_percent),
      });
      onSaved(saved);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível guardar o plano'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open onClose={onClose} title={plan ? 'Editar plano' : 'Novo plano'}
      subtitle={plan && plan.companies ? 'Aplica-se logo às ' + plan.companies + (plan.companies === 1 ? ' empresa' : ' empresas') + ' deste plano' : undefined}
      maxWidthClass="max-w-5xl">
      <form onSubmit={submit} className="flex flex-col gap-5">
        <div className="grid grid-cols-1 sm:grid-cols-6 gap-3">
          <Field label="Nome *" className="sm:col-span-2"><input value={form.name} onChange={(e) => set('name', e.target.value)} required maxLength={60} className={inputClass} /></Field>
          <Field label="Descrição" className="sm:col-span-3"><input value={form.description} onChange={(e) => set('description', e.target.value)} maxLength={300} placeholder="Ex.: Para começar: um negócio, uma caixa" className={inputClass} /></Field>
          <Field label="Ordem"><input type="number" min="0" value={form.sort_order} onChange={(e) => set('sort_order', e.target.value)} className={inputClass} /></Field>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          <div className="flex flex-col gap-3">
            <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Preços (Kz) - vazio: não se vende assim</span>
            {PRICES.map(([key, label]) => (
              <div key={key} className="grid grid-cols-5 items-center gap-2">
                <span className="col-span-2 text-[13px] text-text-primary">{label}</span>
                <input type="number" min="0" step="0.01" value={form[key]} onChange={(e) => set(key, e.target.value)} className={inputClass + ' col-span-3'} />
              </div>
            ))}
            <div className="grid grid-cols-5 items-center gap-2 border-t border-border pt-3">
              <span className="col-span-2 text-[13px] text-text-primary">Vitalícia (local)</span>
              <input type="number" min="0" step="0.01" value={form.price_lifetime} onChange={(e) => set('price_lifetime', e.target.value)} placeholder="Pago uma vez" className={inputClass + ' col-span-3'} />
            </div>
            <div className="grid grid-cols-5 items-center gap-2">
              <span className="col-span-2 text-[13px] text-text-primary">Manutenção (%/ano)</span>
              <input type="number" min="0" max="100" step="0.01" value={form.maintenance_percent} onChange={(e) => set('maintenance_percent', e.target.value)} placeholder="Ex.: 20" className={inputClass + ' col-span-3'} />
            </div>
            <p className="text-[11px] text-text-muted">
              Vitalícia: paga uma vez, funciona para sempre. A manutenção (atualizações fiscais da AGT, novidades, suporte)
              é anual, em % do preço vitalício; o primeiro ano está incluído.
            </p>
          </div>

          <div className="flex flex-col gap-3">
            <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Limites - vazio: ilimitado</span>
            {catalog.limits.map((lim) => (
              <div key={lim.code} className="grid grid-cols-5 items-center gap-2">
                <span className="col-span-3 text-[13px] text-text-primary">{lim.label}</span>
                <input type="number" min="0" step="1" value={form.limits[lim.code]} onChange={(e) => setLimit(lim.code, e.target.value)} placeholder="Ilimitado" className={inputClass + ' col-span-2'} />
              </div>
            ))}
            <p className="text-[11px] text-text-muted">
              As caixas contam todas as caixas ativas (cada atividade traz a sua). Os armazéns dos pontos de venda das
              atividades não contam - só os armazéns da empresa.
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Opções incluídas</span>
            {catalog.options.map((o) => (
              <label key={o.code} className="flex items-start gap-2.5 border border-border rounded-md px-3 py-2 cursor-pointer hover:border-accent select-none">
                <input type="checkbox" checked={form.options.includes(o.code)} onChange={() => toggleOption(o.code)} className="w-4 h-4 mt-0.5 accent-accent cursor-pointer" />
                <span>
                  <span className="block text-[13px] text-text-primary">{o.label}</span>
                  <span className="block text-[11px] text-text-muted">{o.description}</span>
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-5 flex-wrap border-t border-border pt-4">
          <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer select-none">
            <input type="checkbox" checked={form.is_popular} onChange={(e) => set('is_popular', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" /> Destacar («Popular»)
          </label>
          <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer select-none">
            <input type="checkbox" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" /> Ativo (escolhe-se para novos contratos)
          </label>
        </div>

        <button type="submit" disabled={saving || !form.name.trim()}
          className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 cursor-pointer">
          {saving ? <Loader2 size={17} className="animate-spin" /> : <Save size={17} />}
          {saving ? 'A guardar...' : plan ? 'Guardar alterações' : 'Criar plano'}
        </button>
      </form>
    </Modal>
  );
}

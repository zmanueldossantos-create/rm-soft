import { useRef, useState, useEffect } from 'react';
import { CheckCircle2, Loader2, MessageCircle } from 'lucide-react';
import { API_BASE_URL } from '../src/api/config';

// «Pedir demonstração»: sent to POST /public/demo-requests, followed by RM SOFT in «Pedidos». The hidden field
// («fax», read-only so the browser's autofill never fills it) and the time the form was open are the anti-spam (app/services/demo_request_service.py).

const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2.5 text-[15px] text-text-primary outline-none focus:border-accent';

function Label({ children, optional }) {
  return (
    <span className="block text-[13px] font-medium text-text-muted mb-1.5">
      {children}{optional && <span className="font-normal text-text-muted/70"> ({optional})</span>}
    </span>
  );
}

export default function DemoForm({ t, lang, sectors, sectorName, plans, wantedPlan, whatsappLink }) {
  const f = t.form;
  const openedAt = useRef(0);
  const [form, setForm] = useState({ name: '', company_name: '', phone: '', email: '', nif: '', sectors: [], plan_id: '',
    deployment: 'NAO_SEI', message: '', fax: '' });
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const [shownPlan, setShownPlan] = useState(wantedPlan);
  useEffect(() => { openedAt.current = Date.now(); }, []); // when the form appeared: a person needs some seconds
  if (wantedPlan !== shownPlan) { // «Pedir este plano» clicked: that plan chosen in the form
    setShownPlan(wantedPlan);
    if (wantedPlan) setForm((v) => ({ ...v, plan_id: wantedPlan }));
  }
  const set = (field, value) => { setForm((v) => ({ ...v, [field]: value })); setError(''); };
  const toggleSector = (code) => set('sectors', form.sectors.includes(code) ? form.sectors.filter((c) => c !== code) : [...form.sectors, code]);

  async function submit(e) {
    e.preventDefault();
    if (!form.name.trim() || !form.company_name.trim() || !form.phone.trim()) { setError(f.required); return; }
    setSending(true);
    setError('');
    try {
      const response = await fetch(API_BASE_URL + '/public/demo-requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, plan_id: form.plan_id || null, language: lang, elapsed_ms: Date.now() - openedAt.current }),
      });
      if (response.ok) { setDone(true); return; }
      const body = await response.json().catch(() => ({}));
      setError(typeof body.detail === 'string' ? body.detail : f.failed);
    } catch {
      setError(f.failed);
    } finally {
      setSending(false);
    }
  }

  if (done) {
    return (
      <div className="bg-bg-elevated text-text-primary rounded-xl p-8 flex flex-col items-start gap-3" role="status">
        <CheckCircle2 size={34} className="text-success" />
        <h3 className="font-display font-semibold text-[24px]">{f.doneTitle}</h3>
        <p className="text-[16px] leading-[1.6] text-text-muted">{f.doneText}</p>
        {whatsappLink && (
          <a href={whatsappLink('(' + form.company_name.trim() + ')')} target="_blank" rel="noreferrer"
            className="mt-2 inline-flex items-center gap-2 text-[15px] font-semibold text-accent">
            <MessageCircle size={17} /> {f.doneWhatsapp}
          </a>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={submit} noValidate className="relative bg-bg-elevated text-text-primary rounded-xl p-5 sm:p-7 grid sm:grid-cols-2 gap-4">
      {/* the hidden field: a person never sees it, a robot fills it; read-only: the browser's autofill skips it */}
      <input type="text" name="fax" value={form.fax} onChange={(e) => set('fax', e.target.value)} readOnly
        tabIndex={-1} autoComplete="off" aria-hidden="true" className="absolute -left-[9999px] w-px h-px opacity-0" />
      <label><Label>{f.name}</Label><input value={form.name} onChange={(e) => set('name', e.target.value)} autoComplete="name" maxLength={120} className={inputClass} /></label>
      <label><Label>{f.company}</Label><input value={form.company_name} onChange={(e) => set('company_name', e.target.value)} autoComplete="organization" maxLength={160} className={inputClass} /></label>
      <label>
        <Label>{f.phone}</Label>
        <div className="flex items-center bg-bg-inset border border-border rounded-md focus-within:border-accent">
          <span className="pl-3 text-[15px] text-text-muted">+244</span>
          <input value={form.phone} onChange={(e) => set('phone', e.target.value)} type="tel" autoComplete="tel-national"
            placeholder="923 000 000" className="flex-1 min-w-0 bg-transparent px-2 py-2.5 text-[15px] text-text-primary outline-none" />
        </div>
      </label>
      <label><Label optional={f.optional}>{f.email}</Label><input value={form.email} onChange={(e) => set('email', e.target.value)} type="email" autoComplete="email" maxLength={160} className={inputClass} /></label>

      <fieldset className="sm:col-span-2">
        <legend className="block text-[13px] font-medium text-text-muted mb-2">{f.sectors}</legend>
        <div className="flex flex-wrap gap-2">
          {sectors.map((s) => {
            const on = form.sectors.includes(s.code);
            return (
              <button key={s.code} type="button" onClick={() => toggleSector(s.code)} aria-pressed={on}
                className={'px-3 py-1.5 rounded-full text-[13px] font-medium border cursor-pointer ' + (on
                  ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary')}>
                {sectorName(s)}
              </button>
            );
          })}
        </div>
      </fieldset>

      <label>
        <Label>{f.plan}</Label>
        <select value={form.plan_id} onChange={(e) => set('plan_id', e.target.value)} className={inputClass + ' cursor-pointer'}>
          <option value="">{f.planUnknown}</option>
          {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
      <label><Label optional={f.optional}>{f.nif}</Label><input value={form.nif} onChange={(e) => set('nif', e.target.value)} maxLength={20} className={inputClass + ' font-mono'} /></label>

      <fieldset className="sm:col-span-2">
        <legend className="block text-[13px] font-medium text-text-muted mb-2">{f.deployment}</legend>
        <div className="flex flex-wrap gap-2">
          {Object.entries(f.deployments).map(([code, label]) => (
            <button key={code} type="button" onClick={() => set('deployment', code)} aria-pressed={form.deployment === code}
              className={'px-3 py-1.5 rounded-md text-[13px] font-medium border cursor-pointer ' + (form.deployment === code
                ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary')}>
              {label}
            </button>
          ))}
        </div>
      </fieldset>

      <label className="sm:col-span-2">
        <Label optional={f.optional}>{f.message}</Label>
        <textarea value={form.message} onChange={(e) => set('message', e.target.value)} rows={3} maxLength={1000}
          placeholder={f.messageHint} className={inputClass + ' resize-y'} />
      </label>

      {error && <p className="sm:col-span-2 text-[14px] text-danger" role="alert">{error}</p>}
      <button type="submit" disabled={sending}
        className="sm:col-span-2 flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-60 text-white font-semibold text-[16px] py-3 rounded-md cursor-pointer">
        {sending && <Loader2 size={18} className="animate-spin" />} {sending ? f.sending : f.send}
      </button>
    </form>
  );
}

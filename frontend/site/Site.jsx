import { useEffect, useMemo, useState } from 'react';
import { BadgePercent, Check, CheckCircle2, CloudOff, FileCheck2, FileSpreadsheet, Gift, Mail, MessageCircle, Minus, Moon, Server, Sun, X } from 'lucide-react';
import { API_BASE_URL } from '../src/api/config';
import { EN, LANGS, TEXT, initialLang, saveLang } from './i18n';
import DemoForm from './DemoForm';

// The public site (rmsystem.co.ao): one page, its data from GET /public/site (plans, sectors, contacts, AGT number).
// Its pictures: real RM SOFT screens (the demonstration company, app/tools/demo.py) in the visitor's theme, and an
// illustration per sector (site/img/setor-<code>.webp - a photo can replace it under the same name).

const BILLINGS = ['MENSAL', 'TRIMESTRAL', 'SEMESTRAL', 'ANUAL', 'VITALICIA'];
const SUBDOMAIN_RE = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const IMAGES = import.meta.glob('./img/*.webp', { eager: true, query: '?url', import: 'default' });
const image = (name) => IMAGES[`./img/${name}.webp`];

function kz(value) {
  return Number(value).toLocaleString('pt-PT', { maximumFractionDigits: 0, useGrouping: 'always' }) + ' Kz';
}

function initialTheme() {
  try { return localStorage.getItem('rmsoft_site_theme') === 'light' ? 'light' : 'dark'; } catch { return 'dark'; }
}

function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <img src="/favicon.svg" alt="" width="32" height="32" className="rounded-[7px]" />
      <span className="font-display font-bold text-[19px] tracking-tight text-text-primary">RM SOFT</span>
    </span>
  );
}

// A screen of the program in a window frame (three dots, the address bar): reads as "the real thing"
function Screen({ name, theme, alt, className = '', eager = false }) {
  return (
    <figure className={'rounded-xl overflow-hidden border border-border bg-bg-elevated shadow-[0_30px_80px_-30px_rgba(0,0,0,0.6)] ' + className}>
      <div className="flex items-center gap-1.5 px-3.5 h-8 border-b border-border bg-bg-inset">
        <span className="w-2.5 h-2.5 rounded-full bg-[#E5645A]/80" />
        <span className="w-2.5 h-2.5 rounded-full bg-[#E5B55A]/80" />
        <span className="w-2.5 h-2.5 rounded-full bg-[#4FAE7C]/80" />
        <span className="ml-3 text-[11px] text-text-muted truncate">demo.rmsystem.co.ao</span>
      </div>
      <img src={image(`${name}-${theme}`)} alt={alt} width="1600" height="956" loading={eager ? 'eager' : 'lazy'}
        className="block w-full h-auto" />
    </figure>
  );
}

function SectionTitle({ title, text }) {
  return (
    <>
      <h2 className="font-display font-bold text-[30px] sm:text-[38px] leading-[1.12] tracking-[-0.015em] text-text-primary">{title}</h2>
      {text && <p className="mt-4 text-[16px] sm:text-[17px] leading-[1.6] text-text-muted max-w-[60ch]">{text}</p>}
    </>
  );
}

// --------------------------------------------------------------------------------------------------------- the page

export default function Site() {
  const [lang, setLang] = useState(initialLang);
  const [theme, setTheme] = useState(initialTheme);
  const [site, setSite] = useState(null);
  const [failed, setFailed] = useState(false);
  const [billing, setBilling] = useState(null);
  const [screen, setScreen] = useState('painel'); // the hero already shows the till
  const [clientOpen, setClientOpen] = useState(false);
  const [wantedPlan, setWantedPlan] = useState(''); // «Pedir este plano»: the form opens with that plan chosen
  const t = TEXT[lang];
  const trialDays = site?.trial_days ?? 15;

  useEffect(() => {
    document.documentElement.lang = lang === 'pt' ? 'pt' : 'en';
    saveLang(lang);
  }, [lang]);

  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light');
    try { localStorage.setItem('rmsoft_site_theme', theme); } catch { /* private mode */ }
  }, [theme]);

  useEffect(() => {
    fetch(API_BASE_URL + '/public/site')
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then(setSite)
      .catch(() => setFailed(true));
  }, []);

  // the ways of paying that at least one plan offers; yearly first shown when there is one
  const billings = useMemo(() => {
    if (!site) return [];
    return BILLINGS.filter((b) => site.plans.some((p) => p.prices[b] != null));
  }, [site]);
  const shownBilling = billing && billings.includes(billing) ? billing : (billings.includes('ANUAL') ? 'ANUAL' : billings[0]);

  const sectorName = (s) => (lang === 'en' && EN.sectors[s.code] ? EN.sectors[s.code][0] : s.name);
  const sectorText = (s) => (lang === 'en' && EN.sectors[s.code] ? EN.sectors[s.code][1] : s.description);
  const limitLabel = (l) => (lang === 'en' && EN.limits[l.code]) || l.label;
  const optionLabel = (o) => (lang === 'en' && EN.options[o.code]) || o.label;

  const whatsapp = site?.contacts?.whatsapp;
  const email = site?.contacts?.email;
  const whatsappLink = (extra) => 'https://wa.me/' + whatsapp.replace(/\D/g, '') + '?text='
    + encodeURIComponent(t.whatsappHello + (extra ? ' ' + extra : ''));

  const ready = (site?.sectors || []).filter((s) => s.ready && image('setor-' + s.code.toLowerCase()));
  const soon = (site?.sectors || []).filter((s) => !s.ready);
  const current = t.program.find((p) => p.key === screen) || t.program[0];

  return (
    <div className="min-h-screen flex flex-col overflow-x-clip">
      {/* ---------------------------------------------------------------------------------------------- header */}
      <header className="sticky top-0 z-30 bg-bg-primary/90 backdrop-blur border-b border-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center gap-4">
          <a href="#topo" className="shrink-0"><Logo /></a>
          <nav className="hidden md:flex items-center gap-6 ml-6 text-[14px] text-text-muted">
            <a href="#setores" className="hover:text-text-primary">{t.nav.sectors}</a>
            <a href="#programa" className="hover:text-text-primary">{t.nav.program}</a>
            <a href="#planos" className="hover:text-text-primary">{t.nav.plans}</a>
            <a href="#contacto" className="hover:text-text-primary">{t.nav.contact}</a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <div className="flex rounded-md border border-border overflow-hidden text-[12px] font-semibold" role="group" aria-label="Idioma / Language">
              {LANGS.map((code) => (
                <button key={code} type="button" onClick={() => setLang(code)} aria-pressed={lang === code}
                  className={'px-2.5 py-1.5 cursor-pointer ' + (lang === code ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}>
                  {code.toUpperCase()}
                </button>
              ))}
            </div>
            <button type="button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              aria-label={theme === 'dark' ? t.themeLight : t.themeDark} title={theme === 'dark' ? t.themeLight : t.themeDark}
              className="w-9 h-9 flex items-center justify-center rounded-md border border-border text-text-muted hover:text-text-primary cursor-pointer">
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <button type="button" onClick={() => setClientOpen(true)}
              className="hidden sm:block border border-border hover:border-accent text-text-primary text-[14px] font-medium px-3.5 py-2 rounded-md cursor-pointer">
              {t.clientArea}
            </button>
          </div>
        </div>
      </header>

      <main id="topo" className="flex-1">
        {/* ---------------------------------------------------------------------------------------------- hero */}
        <section className="hero-glow">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-14 pb-16 md:pt-20 md:pb-24 grid lg:grid-cols-[0.9fr_1.1fr] gap-12 lg:gap-10 items-center">
            <div>
              <h1 className="font-display font-bold text-[38px] leading-[1.06] sm:text-[54px] tracking-[-0.025em] text-text-primary max-w-[15ch]">
                {t.heroTitle}
              </h1>
              <p className="mt-6 text-[17px] sm:text-[18px] leading-[1.6] text-text-muted max-w-[50ch]">{t.heroText}</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <a href="#contacto"
                  className="bg-accent hover:bg-accent-hover text-white font-semibold text-[15px] px-6 py-3.5 rounded-md">{t.askDemo}</a>
                <a href="#planos" className="border border-border hover:border-accent text-text-primary font-medium text-[15px] px-6 py-3.5 rounded-md">{t.seePlans}</a>
              </div>
              <p className="mt-6 flex items-center gap-2 text-[14px] text-text-muted">
                <Gift size={16} className="text-success" /> {t.trialBadge(trialDays)}
              </p>
              <button type="button" onClick={() => setClientOpen(true)} className="sm:hidden mt-4 text-[14px] text-accent underline underline-offset-4 cursor-pointer">
                {t.clientArea}
              </button>
            </div>
            <div className="relative lg:-mr-24 xl:-mr-40">
              <Screen name="caixa" theme={theme} alt={t.shotAlt('Caixa')} eager className="hero-screen" />
              <div className="hero-chip absolute -bottom-5 left-4 sm:left-8 flex items-center gap-3 bg-bg-elevated border border-border rounded-lg pl-3 pr-4 py-2.5 shadow-[0_16px_40px_-16px_rgba(0,0,0,0.6)]">
                <CheckCircle2 size={22} className="text-success shrink-0" />
                <div>
                  <div className="font-mono text-[12px] text-text-muted">{t.heroChipTitle}</div>
                  <div className="text-[14px] font-semibold text-text-primary">{t.heroChipText}</div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* -------------------------------------------------------------------------------------------- facts */}
        <section className="border-y border-border bg-bg-elevated">
          <ul className="max-w-6xl mx-auto px-4 sm:px-6 py-10 grid sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {t.facts.map((fact, i) => {
              const Icon = [Gift, CloudOff, FileSpreadsheet, BadgePercent][i];
              return (
                <li key={i} className="flex gap-3.5">
                  <Icon size={22} className="text-accent shrink-0 mt-0.5" strokeWidth={1.8} />
                  <div>
                    <div className="font-display font-semibold text-[17px] text-text-primary">{fact.title(trialDays)}</div>
                    <p className="mt-1 text-[14px] leading-[1.5] text-text-muted">{fact.text}</p>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        {/* ------------------------------------------------------------------------------------------- sectors */}
        <section id="setores" className="scroll-mt-16">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20">
            <SectionTitle title={t.sectorsTitle} text={t.sectorsText} />
            <div className="mt-12 grid gap-3 sm:gap-5 grid-cols-2 lg:grid-cols-4">
              {ready.map((s) => (
                <article key={s.code} className="rounded-lg overflow-hidden border border-border bg-bg-elevated">
                  <img src={image('setor-' + s.code.toLowerCase())} alt="" width="720" height="440" loading="lazy" className="block w-full h-auto" />
                  <div className="p-3.5 sm:p-5">
                    <h3 className="font-display font-semibold text-[16px] sm:text-[19px] text-text-primary">{sectorName(s)}</h3>
                    <p className="mt-1 sm:mt-1.5 text-[13px] sm:text-[14px] leading-[1.5] text-text-muted">{sectorText(s)}</p>
                  </div>
                </article>
              ))}
            </div>
            {soon.length > 0 && (
              <p className="mt-8 text-[15px] text-text-muted">
                <span className="font-semibold text-accent">{t.soonTitle}:</span> {soon.map(sectorName).join(', ')}.
              </p>
            )}
          </div>
        </section>

        {/* ------------------------------------------------------------------------------------- the program */}
        <section id="programa" className="bg-bg-elevated border-y border-border scroll-mt-16">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20">
            <SectionTitle title={t.programTitle} text={t.programText} />
            <div className="mt-10 flex flex-wrap gap-2" role="tablist">
              {t.program.map((p) => (
                <button key={p.key} type="button" role="tab" aria-selected={screen === p.key} onClick={() => setScreen(p.key)}
                  className={'px-4 py-2 rounded-md text-[14px] font-semibold cursor-pointer border ' + (screen === p.key
                    ? 'bg-accent border-accent text-white' : 'border-border text-text-muted hover:text-text-primary')}>
                  {p.label}
                </button>
              ))}
            </div>
            <div className="mt-8 grid lg:grid-cols-[0.42fr_1fr] gap-10 items-start">
              <div className="lg:pt-6">
                <h3 className="font-display font-semibold text-[24px] text-text-primary">{current.title}</h3>
                <ul className="mt-5 flex flex-col gap-3.5">
                  {current.points.map((point) => (
                    <li key={point} className="flex gap-2.5 text-[15px] leading-[1.5] text-text-primary">
                      <Check size={18} className="text-success shrink-0 mt-0.5" /> {point}
                    </li>
                  ))}
                </ul>
              </div>
              <Screen key={screen} name={screen} theme={theme} alt={t.shotAlt(current.label)} className="screen-swap" />
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------------------------------------ AGT, offline */}
        <section className="scroll-mt-16">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20">
            <SectionTitle title={t.howTitle} />
            {site?.agt_validation_number && (
              <p className="mt-4 inline-flex items-center gap-2 text-[14px] font-semibold text-success">
                <FileCheck2 size={16} /> {t.validatedBadge(site.agt_validation_number)}
              </p>
            )}
            <div className="mt-10 grid md:grid-cols-3 gap-10">
              {t.how.map((item, i) => {
                const Icon = [FileCheck2, CloudOff, Server][i];
                return (
                  <div key={item.title} className="border-t-2 border-accent pt-5">
                    <Icon size={24} className="text-accent" strokeWidth={1.75} />
                    <h3 className="mt-3 font-display font-semibold text-[19px] text-text-primary">{item.title}</h3>
                    <p className="mt-2 text-[15px] leading-[1.6] text-text-muted max-w-[38ch]">{item.text}</p>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* -------------------------------------------------------------------------------------------- plans */}
        <section id="planos" className="border-t border-border scroll-mt-16">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 py-20">
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-6">
              <div>
                <SectionTitle title={t.plansTitle} text={t.plansText(trialDays)} />
              </div>
              {billings.length > 1 && (
                <div className="flex flex-wrap rounded-md border border-border p-1 gap-1 self-start md:self-end" role="tablist">
                  {billings.map((b) => (
                    <button key={b} type="button" role="tab" aria-selected={shownBilling === b} onClick={() => setBilling(b)}
                      className={'px-3 py-1.5 rounded text-[13px] font-medium cursor-pointer ' + (shownBilling === b ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}>
                      {t.billing[b]}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {failed && <p className="mt-10 text-[15px] text-danger">{t.loadError}</p>}
            {site && site.plans.length === 0 && <p className="mt-10 text-[15px] text-text-muted">{t.noPlans}</p>}
            {shownBilling === 'VITALICIA' && <p className="mt-6 text-[14px] text-text-muted">{t.lifetimeNote}</p>}

            {site && site.plans.length > 0 && (
              <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-[repeat(auto-fit,minmax(240px,1fr))] items-stretch">
                {site.plans.map((plan) => {
                  const price = shownBilling ? plan.prices[shownBilling] : null;
                  const anyPrice = BILLINGS.some((b) => plan.prices[b] != null);
                  return (
                    <article key={plan.id}
                      className={'relative flex flex-col rounded-lg p-6 ' + (plan.is_popular ? 'border-2 border-accent bg-bg-elevated' : 'border border-border')}>
                      {plan.is_popular && (
                        <span className="absolute -top-3 left-6 bg-accent text-white text-[12px] font-semibold px-2.5 py-0.5 rounded">{t.popular}</span>
                      )}
                      <h3 className="font-display font-semibold text-[22px] text-text-primary">{plan.name}</h3>
                      {plan.description && (
                        <p className="mt-1.5 text-[14px] leading-[1.5] text-text-muted min-h-[42px]">
                          {(lang === 'en' && plan.description_en) || plan.description}
                        </p>
                      )}
                      <div className="mt-5 min-h-[64px]">
                        {!anyPrice ? (
                          <div className="font-display font-semibold text-[26px] text-text-primary">{t.onRequest}</div>
                        ) : price == null ? (
                          <div className="text-[14px] text-text-muted pt-2">{t.notThisWay}</div>
                        ) : (
                          <>
                            <div className="font-display font-bold text-[30px] tracking-tight text-text-primary">{kz(price)}</div>
                            <div className="text-[13px] text-text-muted">{t.per[shownBilling]}</div>
                            {shownBilling === 'VITALICIA' && plan.maintenance_percent != null && (
                              <div className="text-[12px] text-text-muted mt-1">{t.maintenance(plan.maintenance_percent)}</div>
                            )}
                          </>
                        )}
                      </div>
                      <dl className="mt-5 pt-5 border-t border-border grid grid-cols-[1fr_auto] gap-x-3 gap-y-1.5 text-[14px]">
                        {site.limits.map((l) => (
                          <div key={l.code} className="contents">
                            <dt className="text-text-muted">{limitLabel(l)}</dt>
                            <dd className="text-text-primary font-medium text-right">{plan.limits[l.code] ?? t.unlimited}</dd>
                          </div>
                        ))}
                      </dl>
                      <ul className="mt-5 pt-5 border-t border-border flex flex-col gap-2 text-[14px] flex-1">
                        {site.options.map((o) => {
                          const has = plan.options.includes(o.code);
                          return (
                            <li key={o.code} className={'flex items-start gap-2 ' + (has ? 'text-text-primary' : 'text-text-muted/60')}>
                              {has ? <Check size={16} className="text-success shrink-0 mt-0.5" /> : <Minus size={16} className="shrink-0 mt-0.5" />}
                              <span>{optionLabel(o)}</span>
                            </li>
                          );
                        })}
                      </ul>
                      <a href="#contacto" onClick={() => setWantedPlan(plan.id)}
                        className={'mt-6 text-center font-semibold text-[14px] px-4 py-2.5 rounded-md ' + (plan.is_popular ? 'bg-accent hover:bg-accent-hover text-white' : 'border border-border hover:border-accent text-text-primary')}>
                        {t.choosePlan}
                      </a>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </section>

        {/* --------------------------------------------------------------------- final call: the demo form */}
        <section id="contacto" className="scroll-mt-16 px-4 sm:px-6 pb-20">
          <div className="max-w-6xl mx-auto rounded-2xl bg-accent text-white p-6 sm:p-10 lg:p-12 grid lg:grid-cols-[0.85fr_1.15fr] gap-10 items-start">
            <div className="lg:pt-2">
              <h2 className="font-display font-bold text-[28px] sm:text-[36px] leading-[1.12] tracking-[-0.015em]">{t.contactTitle}</h2>
              <p className="mt-4 text-[16px] sm:text-[17px] leading-[1.6] text-white/85 max-w-[44ch]">{t.contactText}</p>
              <ul className="mt-7 flex flex-col gap-3">
                {t.contactSteps.map((step) => (
                  <li key={step} className="flex gap-2.5 text-[15px] text-white/95"><Check size={18} className="shrink-0 mt-0.5" /> {step}</li>
                ))}
              </ul>
              <div className="mt-8 flex flex-col sm:flex-row lg:flex-col gap-3 sm:items-start">
                {whatsapp && (
                  <a href={whatsappLink()} target="_blank" rel="noreferrer"
                    className="inline-flex items-center justify-center gap-2.5 bg-white text-[#14532D] hover:bg-white/90 font-semibold text-[15px] px-5 py-3 rounded-md">
                    <MessageCircle size={18} className="text-[#1F9D55]" /> {t.whatsapp}
                  </a>
                )}
                {email && (
                  <a href={'mailto:' + email} className="inline-flex items-center justify-center gap-2.5 border border-white/50 hover:border-white text-white font-medium text-[15px] px-5 py-3 rounded-md">
                    <Mail size={18} /> {email}
                  </a>
                )}
              </div>
            </div>
            <DemoForm t={t} lang={lang} sectors={ready} sectorName={sectorName} plans={site?.plans || []}
              wantedPlan={wantedPlan} whatsappLink={whatsapp ? whatsappLink : null} />
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 flex flex-col sm:flex-row justify-between gap-3 text-[13px] text-text-muted">
          <span>{t.footer}{site?.vendor_tax_id ? ' ' + t.nif + ' ' + site.vendor_tax_id + '.' : ''}</span>
          <span>© {new Date().getFullYear()} RM SOFT</span>
        </div>
      </footer>

      {clientOpen && <ClientArea t={t} onClose={() => setClientOpen(false)} />}
    </div>
  );
}

// «Área de cliente»: every company has its own address (<name>.rmsystem.co.ao) - typed here, then opened.
function ClientArea({ t, onClose }) {
  const [name, setName] = useState('');
  const [invalid, setInvalid] = useState(false);
  const host = window.location.hostname.replace(/^www\./, '');
  const port = window.location.port ? ':' + window.location.port : '';

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  function open(e) {
    e.preventDefault();
    const value = name.trim().toLowerCase();
    if (!SUBDOMAIN_RE.test(value)) { setInvalid(true); return; }
    window.location.href = window.location.protocol + '//' + value + '.' + host + port + '/login';
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <form onSubmit={open} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="client-area-title"
        className="w-full max-w-md bg-bg-elevated border border-border rounded-lg p-6">
        <div className="flex items-start justify-between gap-4">
          <h2 id="client-area-title" className="font-display font-semibold text-[20px] text-text-primary">{t.clientAreaTitle}</h2>
          <button type="button" onClick={onClose} aria-label={t.close} className="text-text-muted hover:text-text-primary cursor-pointer"><X size={18} /></button>
        </div>
        <p className="mt-2 text-[14px] text-text-muted">{t.clientAreaHelp}</p>
        <div className={'mt-5 flex items-center rounded-md border bg-bg-inset ' + (invalid ? 'border-danger' : 'border-border focus-within:border-accent')}>
          <input autoFocus value={name} onChange={(e) => { setName(e.target.value); setInvalid(false); }}
            placeholder="padaria-kilamba" aria-label={t.clientAreaTitle}
            className="flex-1 min-w-0 bg-transparent px-3 py-2.5 text-[15px] text-text-primary outline-none" />
          <span className="pr-3 text-[14px] text-text-muted whitespace-nowrap">.{host}</span>
        </div>
        {invalid && <p className="mt-2 text-[13px] text-danger">{t.clientAreaInvalid}</p>}
        <button type="submit" className="mt-5 w-full bg-accent hover:bg-accent-hover text-white font-semibold text-[15px] py-2.5 rounded-md cursor-pointer">
          {t.clientAreaGo}
        </button>
      </form>
    </div>
  );
}

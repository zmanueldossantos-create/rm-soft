import DateInput from '../components/DateInput';
import { useState, useEffect } from 'react';
import { Settings, Globe, DollarSign, MapPin, Building2, Landmark, CreditCard, Calendar, Percent, Plus, Pencil, Loader2, X, FileText, Ruler, ShieldMinus, LayoutGrid, ShieldCheck, Save, Check, ArrowLeftRight, PiggyBank, Bot, Zap, FileCheck2, KeyRound, Copy } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import {
  countriesApi, currenciesApi, provincesApi, municipalitiesApi,
  banksApi, paymentMethodsApi, paymentTermsApi, vatCodesApi,
  documentTypesApi, unitsApi, withholdingTaxesApi, legalVatRatesApi, movementTypesApi,
  denominationsApi,
} from '../api/catalogs';
import { listFiscalRegimes, createFiscalRegime, updateFiscalRegime, toggleFiscalRegimeStatus } from '../api/fiscalRegime';
import { listModules, createModule, updateModule, toggleModuleStatus } from '../api/module';

const fiscalRegimesApi = {
  list: () => listFiscalRegimes(),
  create: (p) => createFiscalRegime(p.name, p.description, p.allows_nor, p.allows_red, p.allows_ise, p.allows_int, p.allows_out, p.required_exemption_id, p.input_vat_deductible_pct, p.turnover_vat_pct, p.kept_exemption_ids),
  update: (id, p) => updateFiscalRegime(id, p.name, p.description, p.allows_nor, p.allows_red, p.allows_ise, p.allows_int, p.allows_out, p.required_exemption_id, p.input_vat_deductible_pct, p.turnover_vat_pct, p.kept_exemption_ids),
  toggle: (id) => toggleFiscalRegimeStatus(id),
};

const modulesApi = {
  list: () => listModules(),
  create: (p) => createModule(p.name, p.description),
  update: (id, p) => updateModule(id, p.name, p.description),
  toggle: (id) => toggleModuleStatus(id),
};

import { extractErrorMessage } from '../utils/errors';
import { getPlatformSettings, updatePlatformSettings, getSiteSettings, updateSiteSettings } from '../api/admin';
import { getAgtSettings, updateAgtSettings, generateAgtSoftwareKey, getAgtTestTaxpayers, importAgtTestTaxpayers, deleteAgtTestTaxpayer } from '../api/agt';
import { getPlatformAi, updatePlatformAi, testPlatformAi, setTelegramBot, getWhatsAppSettings, updateWhatsAppSettings } from '../api/ai';
import { useToastState } from '../components/Toaster';
import { toast } from '../store/toastStore';

// The AI assistant: one provider, model and key for every company (the platform pays), a monthly message limit per
// company (each company's own limit, if any, is set in Empresas > Assistente IA). The key is never shown back.
function AiSettingsCard() {
  const [values, setValues] = useState({ provider: '', model: '', apiKey: '', monthlyLimit: '300' });
  const [info, setInfo] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useToastState('success');
  const [error, setError] = useToastState('error');

  function load(data) {
    setInfo(data);
    setValues({ provider: data.provider || '', model: data.model || '', apiKey: '', monthlyLimit: String(data.monthly_limit) });
  }

  useEffect(() => {
    getPlatformAi().then(load).catch(() => setInfo({ providers: [] }));
  }, []);

  function updateValue(field, value) {
    setValues((prev) => ({ ...prev, [field]: value }));
    setSaved(false);
  }

  async function handleSave(extra = {}) {
    setError('');
    setTestResult('');
    setSaving(true);
    try {
      load(await updatePlatformAi({
        provider: values.provider, model: values.model.trim(),
        apiKey: values.apiKey.trim() ? values.apiKey.trim() : null,
        monthlyLimit: parseInt(values.monthlyLimit, 10) || 0, ...extra,
      }));
      setSaved(true);
      toast.success('Alterações guardadas');
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setError('');
    setTestResult('');
    setTesting(true);
    try {
      const result = await testPlatformAi();
      setTestResult('Ligação estabelecida em ' + result.seconds + ' s - resposta: «' + result.answer + '»');
    } catch (err) {
      setError(extractErrorMessage(err, 'Falha no teste'));
    } finally {
      setTesting(false);
    }
  }

  if (!info) return null;
  const fieldClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors';
  const labelClass = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block';

  return (
    <div className="bg-bg-elevated border border-border rounded-lg px-5 py-4 mb-6">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="w-9 h-9 rounded-md bg-accent/10 flex items-center justify-center shrink-0">
          <Bot size={17} className="text-accent" />
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Assistente IA</p>
          <p className="text-[11px] text-text-muted/70">Um fornecedor e uma chave para todas as empresas - ativar por empresa em Empresas</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <div>
          <label className={labelClass}>Fornecedor</label>
          <Select value={values.provider} onChange={(v) => updateValue('provider', v)} options={(info.providers || []).map((p) => ({ value: p.value, label: p.label }))} placeholder="Nenhum" />
        </div>
        <div>
          <label className={labelClass}>Modelo</label>
          <input value={values.model} onChange={(e) => updateValue('model', e.target.value)} placeholder={values.provider === 'ANTHROPIC' ? 'Ex: claude-sonnet-4-5' : values.provider === 'OPENROUTER' ? 'Ex: openai/gpt-4o-mini' : 'Ex: gpt-4o-mini'} className={fieldClass} />
        </div>
        <div>
          <label className={labelClass}>Chave de acesso (API)</label>
          <input type="password" autoComplete="new-password" value={values.apiKey} onChange={(e) => updateValue('apiKey', e.target.value)} placeholder={info.api_key_hint || 'Colar a chave'} className={fieldClass} />
          {info.has_api_key && <p className="text-[11px] text-text-muted mt-1">Deixe vazio para manter a chave atual</p>}
        </div>
        <div>
          <label className={labelClass}>Mensagens / mês por empresa</label>
          <input type="number" min="0" value={values.monthlyLimit} onChange={(e) => updateValue('monthlyLimit', e.target.value)} className={fieldClass} />
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => handleSave()}
          disabled={saving}
          className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium px-3.5 py-2 rounded-md transition-colors cursor-pointer"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <Check size={14} /> : <Save size={14} />}
          {saved ? 'Guardado' : 'Guardar'}
        </button>
        <button
          onClick={handleTest}
          disabled={testing || !info.has_api_key || !info.provider}
          title={!info.has_api_key || !info.provider ? 'Guarde primeiro o fornecedor, o modelo e a chave' : undefined}
          className="flex items-center gap-1.5 border border-border hover:border-accent disabled:opacity-50 disabled:cursor-not-allowed text-text-primary text-sm font-medium px-3.5 py-2 rounded-md transition-colors cursor-pointer"
        >
          {testing ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
          Testar ligação
        </button>
        {info.has_api_key && (
          <button
            onClick={() => handleSave({ apiKey: '' })}
            disabled={saving}
            className="text-[12px] text-text-muted hover:text-danger transition-colors cursor-pointer"
          >
            Remover a chave
          </button>
        )}
      </div>

      <TelegramBotRow info={info} onChange={(t) => setInfo((p) => ({ ...p, telegram_configured: t.configured, telegram_bot_username: t.username }))} />
      <WhatsAppRow />
    </div>
  );
}

// The Telegram bot of the assistant: its token (from @BotFather), checked with Telegram and kept encrypted.
function TelegramBotRow({ info, onChange }) {
  const [token, setToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useToastState('error');

  async function save(value) {
    setError('');
    setSaving(true);
    try {
      onChange(await setTelegramBot(value));
      setToken('');
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mt-4 pt-4 border-t border-border flex items-end gap-3 flex-wrap">
      <div className="flex-1 min-w-[260px]">
        <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Bot do Telegram (token do @BotFather)</label>
        <input type="password" autoComplete="new-password" value={token} onChange={(e) => setToken(e.target.value)}
          placeholder={info.telegram_configured ? 'Bot ligado - colar um novo token para trocar' : 'Ex.: 123456789:AAH...'}
          className="w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
      </div>
      <button onClick={() => save(token.trim())} disabled={saving || !token.trim()}
        className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium px-3.5 py-2 rounded-md transition-colors cursor-pointer">
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}Guardar bot
      </button>
      {info.telegram_configured && (
        <>
          <span className="text-[12px] text-success font-medium py-2">Ligado: @{info.telegram_bot_username}</span>
          <button onClick={() => save('')} disabled={saving} className="text-[12px] text-text-muted hover:text-danger transition-colors cursor-pointer py-2">Remover o bot</button>
        </>
      )}
    </div>
  );
}

// The RM SOFT number on WhatsApp (WhatsApp Cloud API, Meta): the values of Meta's «API Setup» page, the token and the
// app secret kept encrypted; Meta's webhook is registered with the address and the verify token shown here.
function WhatsAppRow() {
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState({ phoneNumberId: '', displayNumber: '', accessToken: '', appSecret: '' });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useToastState('error');

  function load(data) {
    setInfo(data);
    setForm({ phoneNumberId: data.phone_number_id || '', displayNumber: data.display_number || '', accessToken: '', appSecret: '' });
  }

  useEffect(() => {
    getWhatsAppSettings().then(load).catch(() => {});
  }, []);

  async function save() {
    setError('');
    setSaving(true);
    try {
      load(await updateWhatsAppSettings({
        phoneNumberId: form.phoneNumberId, displayNumber: form.displayNumber,
        accessToken: form.accessToken.trim() ? form.accessToken.trim() : null, appSecret: form.appSecret.trim() ? form.appSecret.trim() : null,
      }));
      setSaved(true);
      toast.success('Alterações guardadas');
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setSaving(false);
    }
  }

  if (!info) return null;
  const field = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors';
  const label = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block';
  const webhook = 'https://<endereço público do servidor>' + info.webhook_path;

  return (
    <div className="mt-4 pt-4 border-t border-border flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">WhatsApp RM SOFT (WhatsApp Cloud API - Meta)</p>
        <span className={'text-[12px] font-medium ' + (info.configured ? 'text-success' : 'text-text-muted')}>{info.configured ? 'Configurado' : 'Não configurado'}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div>
          <label className={label}>Phone number ID</label>
          <input value={form.phoneNumberId} onChange={(e) => setForm((p) => ({ ...p, phoneNumberId: e.target.value }))} placeholder="Página API Setup da Meta" className={field} />
        </div>
        <div>
          <label className={label}>Número (mostrado ao gestor)</label>
          <input value={form.displayNumber} onChange={(e) => setForm((p) => ({ ...p, displayNumber: e.target.value }))} placeholder="+244 9..." className={field} />
        </div>
        <div>
          <label className={label}>Access token</label>
          <input type="password" autoComplete="new-password" value={form.accessToken} onChange={(e) => setForm((p) => ({ ...p, accessToken: e.target.value }))} placeholder={info.access_token_hint || 'Token permanente'} className={field} />
        </div>
        <div>
          <label className={label}>App secret</label>
          <input type="password" autoComplete="new-password" value={form.appSecret} onChange={(e) => setForm((p) => ({ ...p, appSecret: e.target.value }))} placeholder={info.has_app_secret ? '••••••• (guardado)' : 'App → Definições → Básico'} className={field} />
        </div>
      </div>
      {info.verify_token && (
        <div className="bg-bg-inset border border-border rounded-md px-3 py-2.5 text-[12px] text-text-muted flex flex-col gap-1">
          <span>Na Meta (WhatsApp → Configuração → Webhook): <span className="text-text-primary">Callback URL</span> <span className="font-mono text-text-primary select-all">{webhook}</span> (o servidor da aplicação: em SaaS o seu domínio, para testar um túnel)</span>
          <span><span className="text-text-primary">Verify token</span> <span className="font-mono text-text-primary select-all">{info.verify_token}</span> - depois subscrever o campo «messages».</span>
        </div>
      )}
      <div className="flex items-center gap-3">
        <button onClick={save} disabled={saving} className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium px-3.5 py-2 rounded-md transition-colors cursor-pointer">
          {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <Check size={14} /> : <Save size={14} />}{saved ? 'Guardado' : 'Guardar WhatsApp'}
        </button>
      </div>
    </div>
  );
}

function PlatformSettingsCard() {
  const [values, setValues] = useState({ softwareValidationNumber: '', vendorTaxId: '', productId: '', productVersion: '' });
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useToastState('error');

  useEffect(() => {
    getPlatformSettings()
      .then((data) => {
        setValues({
          softwareValidationNumber: data.software_validation_number || '',
          vendorTaxId: data.vendor_tax_id || '',
          productId: data.product_id || '',
          productVersion: data.product_version || '',
        });
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, []);

  function updateValue(field, value) {
    setValues((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSave() {
    setError('');
    setSaving(true);
    setSaved(false);
    try {
      await updatePlatformSettings(
        values.softwareValidationNumber.trim() || null,
        values.vendorTaxId.trim() || null,
        values.productId.trim() || null,
        values.productVersion.trim() || null,
      );
      setSaved(true);
      toast.success('Alterações guardadas');
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setSaving(false);
    }
  }

  if (!loaded) return null;

  return (
    <div className="bg-bg-elevated border border-border rounded-lg px-5 py-4 mb-6">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="w-9 h-9 rounded-md bg-accent/10 flex items-center justify-center shrink-0">
          <ShieldCheck size={17} className="text-accent" />
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Identificação do software (SAF-T)</p>
          <p className="text-[11px] text-text-muted/70">Aplica-se a todas as empresas na exportação SAF-T</p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Nº validação AGT</label>
          <input
            value={values.softwareValidationNumber}
            onChange={(e) => updateValue('softwareValidationNumber', e.target.value)}
            placeholder="Ex: 326/AGT/2026"
            className="w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
          />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">NIF do fornecedor</label>
          <input
            value={values.vendorTaxId}
            onChange={(e) => updateValue('vendorTaxId', e.target.value)}
            placeholder="NIF da RM SOFT"
            className="w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
          />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">ProductID</label>
          <input
            value={values.productId}
            onChange={(e) => updateValue('productId', e.target.value)}
            placeholder="RMSOFT/RMSOFT"
            className="w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
          />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Versão</label>
          <input
            value={values.productVersion}
            onChange={(e) => updateValue('productVersion', e.target.value)}
            placeholder="1.0"
            className="w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
          />
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium px-3.5 py-2 rounded-md transition-colors cursor-pointer"
        >
          {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <Check size={14} /> : <Save size={14} />}
          {saved ? 'Guardado' : 'Guardar'}
        </button>
      </div>
    </div>
  );
}

// Faturação Eletrónica (AGT), for every company of this installation: the environment, the producer's access (Basic
// Auth - the password kept encrypted), the software's identity and its signature (jwsSoftwareSignature). On the RM SOFT
// platform the producer's key is here and signs the identity again whenever it changes; on a client's server only the
// signature's text is pasted (given by RM SOFT) - the producer's key never leaves the platform.
const AGT_STATUS = {
  OK: { label: 'Assinatura válida para esta versão', className: 'text-success' },
  EM_FALTA: { label: 'Assinatura em falta', className: 'text-amber-500' },
  DESATUALIZADA: { label: 'Assinatura desatualizada - a identificação mudou', className: 'text-danger' },
};

function AgtSettingsCard() {
  const [info, setInfo] = useState(null);
  const [form, setForm] = useState({ environment: 'HOMOLOGACAO', username: '', password: '', productId: '', signatureVersion: '', softwareKey: '', softwareSignature: '' });
  const [busy, setBusy] = useState('');
  const [showPublic, setShowPublic] = useState(false);
  const [confirmNewPair, setConfirmNewPair] = useState(false);

  function load(data) {
    setInfo(data);
    setForm({
      environment: data.environment, username: data.username || '', password: '', productId: data.product_id || '',
      signatureVersion: data.signature_version ?? '', softwareKey: '', softwareSignature: data.has_software_key ? '' : (data.software_signature || ''),
    });
  }

  useEffect(() => {
    getAgtSettings().then(load).catch(() => {});
  }, []);

  function update(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function save(extra = {}) {
    setBusy('save');
    try {
      load(await updateAgtSettings({
        ...form,
        password: form.password ? form.password : null,
        softwareKey: form.softwareKey.trim() ? form.softwareKey : null,
        softwareSignature: info.has_software_key ? null : form.softwareSignature,
        ...extra,
      }));
      toast.success('Configuração AGT guardada');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setBusy('');
    }
  }

  async function newPair() {
    setBusy('pair');
    try {
      load(await generateAgtSoftwareKey(info.has_software_key));
      setConfirmNewPair(false);
      setShowPublic(true);
      toast.success('Par de chaves do produtor gerado - registe a chave pública no portal do parceiro da AGT');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao gerar as chaves'));
    } finally {
      setBusy('');
    }
  }

  async function copy(text, what) {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(what + ' copiada');
    } catch {
      toast.error('Não foi possível copiar - selecione o texto');
    }
  }

  if (!info) return null;
  const field = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors';
  const label = 'text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block';
  const button = 'flex items-center gap-1.5 text-sm font-medium px-3.5 py-2 rounded-md transition-colors cursor-pointer disabled:opacity-50';
  const status = AGT_STATUS[info.signature_status] || AGT_STATUS.EM_FALTA;

  return (
    <div className="bg-bg-elevated border border-border rounded-lg px-5 py-4 mb-6">
      <div className="flex items-center justify-between gap-2.5 mb-4 flex-wrap">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-md bg-accent/10 flex items-center justify-center shrink-0">
            <FileCheck2 size={17} className="text-accent" />
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wide text-text-muted">Faturação Eletrónica - AGT</p>
            <p className="text-[11px] text-text-muted/70">Acesso do produtor e assinatura do software - para todas as empresas desta instalação</p>
          </div>
        </div>
        <span className={'text-[12px] font-medium ' + status.className}>{status.label}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
        <div>
          <label className={label}>Ambiente</label>
          <Select value={form.environment} onChange={(v) => update('environment', v)} options={[{ value: 'HOMOLOGACAO', label: 'Homologação (testes)' }, { value: 'PRODUCAO', label: 'Produção' }]} />
        </div>
        <div>
          <label className={label}>Utilizador AGT</label>
          <input value={form.username} onChange={(e) => update('username', e.target.value)} autoComplete="off" className={field} />
        </div>
        <div>
          <label className={label}>Palavra-passe AGT</label>
          <input type="password" autoComplete="new-password" value={form.password} onChange={(e) => update('password', e.target.value)}
            placeholder={info.has_password ? info.password_hint + ' (vazio: manter)' : 'Dada pela AGT'} className={field} />
        </div>
        <div>
          <label className={label}>Nome do software (productId)</label>
          <input value={form.productId} onChange={(e) => update('productId', e.target.value)} placeholder="Como registado na AGT" className={field} />
        </div>
        <div>
          <label className={label}>Versão da assinatura</label>
          <input type="number" min="0" value={form.signatureVersion} onChange={(e) => update('signatureVersion', e.target.value)} placeholder="Vazio: não enviada" className={field} />
        </div>
      </div>
      <p className="text-[11px] text-text-muted mb-4">
        Versão e Nº de validação: os do cartão «Identificação do software» acima. Endereço: <span className="font-mono">{info.base_url}</span>
      </p>

      <div className="border-t border-border pt-4 flex flex-col gap-3">
        {info.has_software_key ? (
          <div className="flex items-center gap-3 flex-wrap text-[12px]">
            <span className="text-text-muted">Chave do produtor (só nesta plataforma): RSA {info.software_key.bits} bits · <span className="font-mono text-text-primary">{info.software_key.fingerprint}</span></span>
            <button type="button" onClick={() => setShowPublic(true)} className="text-accent hover:underline cursor-pointer">Ver a chave pública</button>
            {confirmNewPair ? (
              <span className="flex items-center gap-2">
                <span className="text-danger">Gerar outro par obriga a registar a nova chave na AGT e a dar a nova assinatura a todos os servidores.</span>
                <button type="button" onClick={newPair} disabled={!!busy} className="text-danger font-medium cursor-pointer">Confirmar</button>
                <button type="button" onClick={() => setConfirmNewPair(false)} className="text-text-muted cursor-pointer">Cancelar</button>
              </span>
            ) : (
              <button type="button" onClick={() => setConfirmNewPair(true)} className="text-text-muted hover:text-danger cursor-pointer">Gerar outro par</button>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-3 flex-wrap text-[12px] text-text-muted">
              <span>Servidor de um cliente: cole só a assinatura dada pela RM SOFT. Plataforma RM SOFT: cole a chave privada do produtor que já tem, ou</span>
              <button type="button" onClick={newPair} disabled={!!busy} className="flex items-center gap-1 text-accent hover:underline cursor-pointer">
                {busy === 'pair' ? <Loader2 size={12} className="animate-spin" /> : <KeyRound size={12} />} gere um par novo
              </button>
            </div>
            <div>
              <label className={label}>Chave privada do produtor (só na plataforma RM SOFT)</label>
              <textarea value={form.softwareKey} onChange={(e) => update('softwareKey', e.target.value)} rows={3} spellCheck={false} autoComplete="off"
                placeholder={'-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----'} className={field + ' text-[11px]'} />
              <p className="text-[11px] text-text-muted mt-1">Guardada cifrada e nunca mais mostrada - a assinatura do software passa a ser calculada aqui.</p>
            </div>
          </div>
        )}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className={label + ' mb-0'}>Assinatura do software (jwsSoftwareSignature)</label>
            {info.software_signature && (
              <button type="button" onClick={() => copy(info.software_signature, 'Assinatura')} className="flex items-center gap-1 text-[12px] text-accent cursor-pointer"><Copy size={12} /> Copiar</button>
            )}
          </div>
          {info.has_software_key ? (
            <textarea readOnly value={info.software_signature || 'Complete o nome do software, a versão e o nº de validação'} rows={3} className={field + ' text-[11px]'} />
          ) : (
            <textarea value={form.softwareSignature} onChange={(e) => update('softwareSignature', e.target.value)} rows={3} spellCheck={false}
              placeholder="eyJhbGciOiJSUzI1NiIs..." className={field + ' text-[11px]'} />
          )}
          {info.signed_detail && <p className="text-[11px] text-text-muted mt-1">Assina: <span className="font-mono">{JSON.stringify(info.signed_detail)}</span></p>}
        </div>
      </div>

      <div className="flex items-center gap-3 mt-4">
        <button type="button" onClick={() => save()} disabled={!!busy} className={button + ' bg-accent hover:bg-accent-hover text-white'}>
          {busy === 'save' ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Guardar
        </button>
        {info.has_password && (
          <button type="button" onClick={() => save({ password: '' })} disabled={!!busy} className="text-[12px] text-text-muted hover:text-danger transition-colors cursor-pointer">Remover a palavra-passe</button>
        )}
      </div>

      <AgtTestNifsRow />

      <Modal open={showPublic} onClose={() => setShowPublic(false)} title="Chave pública do produtor" maxWidthClass="max-w-xl"
        subtitle="Registar no portal do parceiro da AGT (a chave privada fica nesta plataforma)">
        <pre className="bg-bg-inset border border-border rounded-md p-3 text-[11px] font-mono text-text-primary overflow-auto select-all">{info.software_public_key}</pre>
        <button type="button" onClick={() => copy(info.software_public_key, 'Chave pública')} className={button + ' mt-3 border border-border hover:border-accent text-text-primary'}>
          <Copy size={14} /> Copiar
        </button>
      </Modal>
    </div>
  );
}

// The AGT's test NIFs (homologação): the TEST_NIF file of the AGT pasted once - each NIF with its name and private key
// (kept encrypted, never shown again). A company then picks one in Definições da Empresa → Faturação Eletrónica.
function AgtTestNifsRow() {
  const [items, setItems] = useState(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAgtTestTaxpayers().then(setItems).catch(() => setItems([]));
  }, []);

  async function importText() {
    setBusy(true);
    try {
      const result = await importAgtTestTaxpayers(text);
      setItems(result.items);
      setText('');
      toast.success(result.imported + (result.imported === 1 ? ' NIF de teste importado' : ' NIFs de teste importados'));
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao importar'));
    } finally {
      setBusy(false);
    }
  }

  async function remove(nif) {
    try {
      setItems(await deleteAgtTestTaxpayer(nif));
      toast.success('NIF de teste ' + nif + ' removido');
    } catch (err) {
      toast.error(extractErrorMessage(err, 'Erro ao remover'));
    }
  }

  if (!items) return null;
  return (
    <div className="border-t border-border mt-4 pt-4 flex flex-col gap-3">
      <div>
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">NIFs de teste da AGT (homologação)</p>
        <p className="text-[11px] text-text-muted/70">Cada empresa pode escolher um, em Definições da Empresa, para testar enquanto o ambiente for Homologação</p>
      </div>
      {items.length > 0 && (
        <div className="border border-border rounded-md divide-y divide-border">
          {items.map((t) => (
            <div key={t.nif} className="flex items-center gap-3 px-3 py-2 text-[12px] flex-wrap">
              <span className="font-mono text-text-primary w-28">{t.nif}</span>
              <span className="text-text-primary flex-1 min-w-[180px]">{t.name}</span>
              {t.key && <span className="text-text-muted font-mono">RSA {t.key.bits} · {t.key.fingerprint}</span>}
              <button type="button" onClick={() => remove(t.nif)} className="text-text-muted hover:text-danger cursor-pointer"><X size={14} /></button>
            </div>
          ))}
        </div>
      )}
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} spellCheck={false} autoComplete="off"
        placeholder={'Colar aqui o conteúdo do ficheiro TEST_NIF da AGT (NIF, nome, chave privada, chave pública)'}
        className="w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-[11px] text-text-primary font-mono outline-none focus:border-accent transition-colors" />
      <div>
        <button type="button" onClick={importText} disabled={busy || !text.trim()}
          className="flex items-center gap-1.5 border border-border hover:border-accent disabled:opacity-50 text-text-primary text-sm font-medium px-3.5 py-2 rounded-md transition-colors cursor-pointer">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Importar NIFs de teste
        </button>
      </div>
    </div>
  );
}

// «Site público» (rmsystem.co.ao): the WhatsApp number and the email its «Contacto» buttons open.
function SiteSettingsCard() {
  const [values, setValues] = useState({ whatsapp: '', email: '' });
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [, setError] = useToastState('error');

  useEffect(() => {
    getSiteSettings()
      .then((data) => setValues({ whatsapp: data.site_whatsapp || '', email: data.site_email || '' }))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  async function handleSave() {
    setError('');
    setSaving(true);
    try {
      const data = await updateSiteSettings(values.whatsapp.trim(), values.email.trim());
      setValues({ whatsapp: data.site_whatsapp || '', email: data.site_email || '' });
      toast.success('Contactos do site guardados');
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao guardar'));
    } finally {
      setSaving(false);
    }
  }

  if (!loaded) return null;
  const inputClass = 'w-full bg-bg-inset border border-border rounded-md px-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors';

  return (
    <div className="bg-bg-elevated border border-border rounded-lg px-5 py-4 mb-6">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="w-9 h-9 rounded-md bg-accent/10 flex items-center justify-center shrink-0">
          <Globe size={17} className="text-accent" />
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Site público</p>
          <p className="text-[11px] text-text-muted/70">Os contactos mostrados em rmsystem.co.ao (botões WhatsApp e email)</p>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">WhatsApp</label>
          <input value={values.whatsapp} onChange={(e) => setValues((v) => ({ ...v, whatsapp: e.target.value }))}
            placeholder="+244923000000" className={inputClass + ' font-mono'} />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Email</label>
          <input type="email" value={values.email} onChange={(e) => setValues((v) => ({ ...v, email: e.target.value }))}
            placeholder="geral@rmsystem.co.ao" className={inputClass} />
        </div>
      </div>
      <button onClick={handleSave} disabled={saving}
        className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium px-3.5 py-2 rounded-md transition-colors cursor-pointer">
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Guardar
      </button>
    </div>
  );
}

function ToggleSwitch({ checked, onChange, disabled }) {
  const trackClass = 'relative w-9 h-5 rounded-full transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ' + (checked ? 'bg-success' : 'bg-border');
  const knobClass = 'absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform ' + (checked ? 'translate-x-4' : 'translate-x-0');
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={onChange} disabled={disabled} className={trackClass}>
      <span className={knobClass} />
    </button>
  );
}

const CATALOGS = [
  { key: 'countries', label: 'Países', icon: Globe, api: countriesApi },
  { key: 'provinces', label: 'Províncias', icon: MapPin, api: provincesApi },
  { key: 'municipalities', label: 'Municípios', icon: MapPin, api: municipalitiesApi },
  { key: 'currencies', label: 'Moedas', icon: DollarSign, api: currenciesApi },
  { key: 'banks', label: 'Bancos', icon: Landmark, api: banksApi },
  { key: 'denominations', label: 'Denominações (Billetagem)', icon: PiggyBank, api: denominationsApi },
  { key: 'payment_methods', label: 'Métodos de Pagamento', icon: CreditCard, api: paymentMethodsApi },
  { key: 'payment_terms', label: 'Condições de Pagamento', icon: Calendar, api: paymentTermsApi },
  { key: 'vat_codes', label: 'Códigos IVA', icon: Percent, api: vatCodesApi },
  { key: 'document_types', label: 'Tipos de Documento', icon: FileText, api: documentTypesApi },
  { key: 'units', label: 'Unidades', icon: Ruler, api: unitsApi },
  { key: 'withholding_taxes', label: 'Retenções', icon: ShieldMinus, api: withholdingTaxesApi },
  { key: 'fiscal_regimes', label: 'Regimes Fiscais', icon: Landmark, api: fiscalRegimesApi },

  { key: 'legal_vat_rates', label: 'Taxas legais de IVA', icon: Percent, api: legalVatRatesApi },
  { key: 'movement_types', label: 'Tipos de Movimento', icon: ArrowLeftRight, api: movementTypesApi },
  { key: 'modules', label: 'Módulos', icon: LayoutGrid, api: modulesApi },
];

// Rules of a document type: [field, label, what it does, already read by the code]
const RULE_INFO = [
  ['electronic_eligible', 'Fatura\u00e7\u00e3o eletr\u00f3nica', 'Necess\u00e1rio para criar s\u00e9ries deste tipo no modo eletr\u00f3nico', true],
  ['is_fiscal', 'Documento fiscal', 'Tipo fiscal. Desmarcado: o PDF indica que n\u00e3o serve como fatura', true],
  ['paid_on_issue', 'Pago na emiss\u00e3o', 'Cria logo o pagamento ao emitir (ex.: Fatura/Recibo)', true],
  ['sent_to_agt', 'Enviado \u00e0 AGT', 'Entra na fila de envio \u00e0 AGT e conta nos estados do painel', true],
  ['deducts_stock', 'Deduz stock', 'Retira do stock os artigos vendidos', true],
  ['accepts_receipt', 'Aceita recibo', 'Permite emitir recibos sobre este tipo', true],
  ['requires_payment_term', 'Exige condi\u00e7\u00e3o de pagamento', 'Obriga a escolher uma condi\u00e7\u00e3o de pagamento ao emitir este tipo', true],
  ['requires_customer', 'Exige cliente identificado', 'Obriga a escolher um cliente ao emitir este tipo (não permite consumidor final)', true],
  ['accepts_credit_note', 'Aceita nota de cr\u00e9dito', 'Permite emitir notas de cr\u00e9dito sobre este tipo', true],
  ['accepts_debit_note', 'Aceita nota de d\u00e9bito', 'Permite emitir notas de d\u00e9bito sobre este tipo', true],
  ['convertible', 'Convert\u00edvel em FT/FR', 'Pode ser transformado em fatura (ex.: pro-forma)', false],
  ['issuable_in_invoices', 'Emitido em Nova Fatura', 'Aparece na lista de tipos do ecr\u00e3 Nova Fatura', true],
  ['issuable_at_pos', 'Emitido na Caixa', 'Aparece na lista de tipos da Caixa', true],
  ['requires_origin', 'Exige documento de origem', 'Tem de referir um documento anterior (ex.: NC, ND, recibo)', false],
  ['has_lines', 'Tem linhas de artigos', 'Desmarcado: documento sem linhas (ex.: recibo)', false],
];

// section «sistema»: the platform's settings cards; «catalogos»: the base catalogs only.
export default function Configuracoes({ section = 'sistema' }) {
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useToastState('error');
  const [countries, setCountries] = useState([]);
  const [provinces, setProvinces] = useState([]);
  const [currencies, setCurrencies] = useState([]);

  const [activeCatalog, setActiveCatalog] = useState(null);

  // Active exemption motives, for the regime form's imposed motive (loaded when the regimes catalog is open).
  const [exemptionMotives, setExemptionMotives] = useState([]);
  useEffect(() => {
    if (activeCatalog?.key !== 'fiscal_regimes') return;
    vatCodesApi.list().then((data) => setExemptionMotives(Array.isArray(data) ? data : [])).catch(() => setExemptionMotives([]));
  }, [activeCatalog]);
  const [items, setItems] = useState([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [togglingId, setTogglingId] = useState(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useToastState('error');

  async function loadCounts() {
    setLoading(true);
    setError('');
    try {
      const [countriesData, provincesData, currenciesData, ...results] = await Promise.all([
        countriesApi.list(), provincesApi.list(), currenciesApi.list(),
        ...CATALOGS.map((c) => c.api.list()),
      ]);
      setCurrencies(currenciesData);
      setCountries(countriesData);
      setProvinces(provincesData);
      const newCounts = {};
      CATALOGS.forEach((c, i) => { newCounts[c.key] = results[i].length; });
      setCounts(newCounts);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar configurações'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCounts();
  }, []);

  async function openCatalog(catalog) {
    setActiveCatalog(catalog);
    setItemsLoading(true);
    try {
      const data = await catalog.api.list();
      setItems(data);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar itens'));
    } finally {
      setItemsLoading(false);
    }
  }

  function closeCatalogModal() {
    setActiveCatalog(null);
    setItems([]);
  }

  async function refreshItems() {
    if (!activeCatalog) return;
    const data = await activeCatalog.api.list();
    setItems(data);
    setCounts((prev) => ({ ...prev, [activeCatalog.key]: data.length }));
  }

  async function handleToggle(id) {
    setTogglingId(id);
    try {
      await activeCatalog.api.toggle(id);
      await refreshItems();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado'));
    } finally {
      setTogglingId(null);
    }
  }

  function emptyFormFor(key) {
    switch (key) {
      case 'countries': return { code: '', name: '' };
      case 'currencies': return { code: '', name: '', symbol: '' };
      case 'provinces': return { country_id: countries[0]?.id || '', name: '' };
      case 'municipalities': return { province_id: provinces[0]?.id || '', name: '' };
      case 'banks': return { acronym: '', full_name: '' };
      case 'payment_methods': return { code: '', name: '', allows_payment: true, allows_receipt: true, is_cash: false, uses_bank_account: false };
      case 'payment_terms': return { name: '', fixed_days: false, days: 0, months_fixed_day: 0, discount: 0 };
      case 'vat_codes': return { code: '', name: '', rate: 0, country_id: countries[0]?.id || '', valid_from: '', valid_until: '', observations: '' };
      case 'document_types': return { code: '', name: '', description: '', area: '', electronic_eligible: false, is_fiscal: true, rules_locked: false, saft_section: 'NONE', revenue_sign: 0, requires_origin: false, has_lines: true, paid_on_issue: false, sent_to_agt: false, deducts_stock: false, accepts_credit_note: false, accepts_debit_note: false, accepts_receipt: false, convertible: false, issuable_in_invoices: false, issuable_at_pos: false, requires_payment_term: false, requires_customer: false };
      case 'movement_types': return { code: '', name: '', direction: 'ENTRADA', is_auto: false, description: '' };
      case 'units': return { code: '', name: '', fixed_factor: '', is_fractional: false };
      case 'withholding_taxes': return { name: '', rate: 0, tax_type: '' };

      case 'legal_vat_rates': return { tax_category: '', name: '', rate: 0 };
      case 'fiscal_regimes': return { name: '', description: '', allows_nor: true, allows_red: true, allows_ise: true, allows_int: false, allows_out: false, required_exemption_id: '', input_vat_deductible_pct: 100, turnover_vat_pct: 0, kept_exemption_ids: [] };
      case 'modules': return { name: '', description: '' };
      case 'denominations': return { currency_id: '', value: '', denomination_type: 'NOTA' };
      default: return {};
    }
  }

  function openCreateForm() {
    setEditingId(null);
    setForm(emptyFormFor(activeCatalog.key));
    setFormError('');
    setFormOpen(true);
  }

  function openEditForm(item) {
    setEditingId(item.id);
    const base = emptyFormFor(activeCatalog.key);
    const next = { ...base };
    Object.keys(base).forEach((k) => { next[k] = item[k] ?? base[k]; });
    setForm(next);
    setFormError('');
    setFormOpen(true);
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      const payload = { ...form };
      if (activeCatalog.key === 'vat_codes') {
        payload.rate = parseFloat(payload.rate);
        payload.valid_until = payload.valid_until || null;
      }
      if (activeCatalog.key === 'payment_terms') {
        payload.days = parseInt(payload.days, 10);
        payload.months_fixed_day = parseInt(payload.months_fixed_day, 10);
        payload.discount = parseFloat(payload.discount);
      }
      if (activeCatalog.key === 'legal_vat_rates') {
        payload.rate = parseFloat(payload.rate);
      }
      if (activeCatalog.key === 'withholding_taxes') {
        payload.rate = parseFloat(payload.rate);
        payload.tax_type = payload.tax_type || null;
      }
      if (activeCatalog.key === 'document_types') {
        payload.revenue_sign = parseInt(payload.revenue_sign, 10);
      }
      if (activeCatalog.key === 'units') {
        payload.fixed_factor = payload.fixed_factor === '' || payload.fixed_factor == null ? null : parseFloat(payload.fixed_factor);
      }
      if (editingId) {
        await activeCatalog.api.update(editingId, payload);
      } else {
        await activeCatalog.api.create(payload);
      }
      setFormOpen(false);
      await refreshItems();
    } catch (err) {
      setFormError(extractErrorMessage(err, editingId ? 'Erro ao atualizar' : 'Erro ao criar'));
    } finally {
      setSaving(false);
    }
  }

  function renderFormFields() {
    const key = activeCatalog.key;
    if (key === 'countries') {
      return (
        <>
          <Field label="Código *"><input value={form.code} onChange={(e) => updateField('code', e.target.value)} required maxLength={3} className={inputClass} /></Field>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
        </>
      );
    }
    if (key === 'currencies') {
      return (
        <>
          <Field label="Código *"><input value={form.code} onChange={(e) => updateField('code', e.target.value)} required maxLength={3} className={inputClass} /></Field>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
          <Field label="Símbolo"><input value={form.symbol || ''} onChange={(e) => updateField('symbol', e.target.value)} className={inputClass} /></Field>
        </>
      );
    }
    if (key === 'provinces') {
      return (
        <>
          <Field label="País *"><Select value={form.country_id} onChange={(v) => updateField('country_id', v)} options={countries.map((c) => ({ value: c.id, label: c.name }))} /></Field>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
        </>
      );
    }
    if (key === 'denominations') {
      return (
        <>
          <Field label="Moeda *"><Select value={form.currency_id} onChange={(v) => updateField('currency_id', v)} options={currencies.map((c) => ({ value: c.id, label: c.code }))} /></Field>
          <Field label="Tipo *"><Select value={form.denomination_type} onChange={(v) => updateField('denomination_type', v)} options={[{ value: 'NOTA', label: 'Nota' }, { value: 'MOEDA', label: 'Moeda' }]} /></Field>
          <Field label="Valor *"><input type="number" step="0.01" min="0.01" value={form.value} onChange={(e) => updateField('value', e.target.value)} required className={inputClass} /></Field>
        </>
      );
    }
    if (key === 'municipalities') {
      return (
        <>
          <Field label="Província *"><Select value={form.province_id} onChange={(v) => updateField('province_id', v)} options={provinces.map((p) => ({ value: p.id, label: p.name }))} /></Field>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
        </>
      );
    }
    if (key === 'banks') {
      return (
        <>
          <Field label="Sigla *"><input value={form.acronym} onChange={(e) => updateField('acronym', e.target.value)} required className={inputClass} /></Field>
          <Field label="Nome completo *"><input value={form.full_name} onChange={(e) => updateField('full_name', e.target.value)} required className={inputClass} /></Field>
        </>
      );
    }
    if (key === 'payment_methods') {
      return (
        <>
          <Field label="Código *"><input value={form.code} onChange={(e) => updateField('code', e.target.value)} required maxLength={4} className={inputClass} /></Field>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
          <div className="flex gap-5">
            <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer">
              <input type="checkbox" checked={form.allows_payment} onChange={(e) => updateField('allows_payment', e.target.checked)} />
              Pagamento
            </label>
            <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer">
              <input type="checkbox" checked={form.allows_receipt} onChange={(e) => updateField('allows_receipt', e.target.checked)} />
              Recebimento
            </label>
          </div>
          <div className="flex gap-5">
            <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer">
              <input type="checkbox" checked={form.is_cash} onChange={(e) => updateField('is_cash', e.target.checked)} />
              Numerário (dinheiro físico)
            </label>
            <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer">
              <input type="checkbox" checked={!!form.uses_bank_account} onChange={(e) => updateField('uses_bank_account', e.target.checked)} />
              Usa conta bancária
            </label>
          </div>
        </>
      );
    }
    if (key === 'payment_terms') {
      return (
        <>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
          <label className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer">
            <input type="checkbox" checked={form.fixed_days} onChange={(e) => updateField('fixed_days', e.target.checked)} />
            Dia fixo do mês (em vez de X dias após a data)
          </label>
          <Field label={form.fixed_days ? 'Dia do mês' : 'Dias'}><input type="number" value={form.days} onChange={(e) => updateField('days', e.target.value)} className={inputClass} /></Field>
          {form.fixed_days && (
            <Field label="Mês (0 = actual, 1 = seguinte)"><input type="number" min="0" max="1" value={form.months_fixed_day} onChange={(e) => updateField('months_fixed_day', e.target.value)} className={inputClass} /></Field>
          )}
          <Field label="Desconto (%)"><input type="number" step="0.01" value={form.discount} onChange={(e) => updateField('discount', e.target.value)} className={inputClass} /></Field>
        </>
      );
    }
    if (key === 'vat_codes') {
      return (
        <>
          <Field label="Código *"><input value={form.code} onChange={(e) => updateField('code', e.target.value)} required className={inputClass} /></Field>
          <Field label="Designação *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
          <Field label="Taxa (%) *"><input type="number" step="0.01" value={form.rate} onChange={(e) => updateField('rate', e.target.value)} required className={inputClass} /></Field>
          <Field label="País *"><Select value={form.country_id} onChange={(v) => updateField('country_id', v)} options={countries.map((c) => ({ value: c.id, label: c.name }))} /></Field>
          <Field label="Válido desde *"><DateInput value={form.valid_from} onChange={(e) => updateField('valid_from', e.target.value)} required className={inputClass} /></Field>
          <Field label="Válido até (vazio = sem fim)"><DateInput value={form.valid_until || ''} onChange={(e) => updateField('valid_until', e.target.value)} className={inputClass} /></Field>
          <Field label="Observações"><textarea value={form.observations || ''} onChange={(e) => updateField('observations', e.target.value)} rows={2} className={inputClass} /></Field>
        </>
      );
    }
    if (key === 'document_types') {
      const rule = ([field, label]) => (
        <label key={field} className="flex items-start gap-2 cursor-pointer select-none">
          <input type="checkbox" checked={!!form[field]} onChange={(e) => updateField(field, e.target.checked)} className="w-4 h-4 mt-0.5 accent-accent cursor-pointer shrink-0" />
          <span className="flex flex-col">
            <span className="text-sm text-text-primary">
              {label}
            </span>
          </span>
        </label>
      );
      return (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <Field label={'C\u00f3digo *'}><input value={form.code} onChange={(e) => updateField('code', e.target.value)} required className={inputClass} /></Field>
            <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
            <Field label="Descrição (cartao de seleção)" hint="Frase curta mostrada ao escolher o tipo de documento, ex: A pagar mais tarde - emite FT">
              <input value={form.description || ''} onChange={(e) => updateField('description', e.target.value)} maxLength={200} className={inputClass} />
            </Field>
            <Field label={'\u00c1rea'}>
              <Select value={form.area} onChange={(v) => updateField('area', v)} options={[{ value: 'FACTURACAO', label: 'Factura\u00e7\u00e3o' }, { value: 'TESOURARIA', label: 'Tesouraria' }, { value: 'COMPRAS', label: 'Compras' }]} placeholder="Selecionar" />
            </Field>
            <Field label={'Sec\u00e7\u00e3o do SAF-T'}>
              <select value={form.saft_section} onChange={(e) => updateField('saft_section', e.target.value)} className={inputClass}>
                <option value="INVOICES">Faturas (SalesInvoices)</option>
                <option value="PAYMENTS">Pagamentos (Payments)</option>
                <option value="WORKING">Documentos de trabalho (Working)</option>
                <option value="NONE">{'N\u00e3o exportado'}</option>
              </select>
            </Field>
            <Field label={'Sinal no volume de neg\u00f3cios'}>
              <select value={String(form.revenue_sign)} onChange={(e) => updateField('revenue_sign', e.target.value)} className={inputClass}>
                <option value="1">+ Venda (soma)</option>
                <option value="-1">{'- Nota de cr\u00e9dito (subtrai)'}</option>
                <option value="0">{'0 N\u00e3o conta'}</option>
              </select>
            </Field>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-x-4 gap-y-3">
            {RULE_INFO.map(rule)}
          </div>
        </>
      );
    }
    if (key === 'movement_types') {
      return (
        <>
          <Field label="Código *"><input value={form.code} onChange={(e) => updateField('code', e.target.value)} required className={inputClass} /></Field>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
          <Field label="Direção *">
            <Select value={form.direction} onChange={(v) => updateField('direction', v)} options={[{ value: 'ENTRADA', label: 'Entrada' }, { value: 'SAIDA', label: 'Saída' }]} />
          </Field>
          <Field label="Descrição"><input value={form.description || ''} onChange={(e) => updateField('description', e.target.value)} className={inputClass} /></Field>
          <label className="flex items-center gap-2.5 cursor-pointer select-none">
            <input type="checkbox" checked={form.is_auto} onChange={(e) => updateField('is_auto', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
            <span className="text-sm text-text-primary">Automático (importação via Excel)</span>
          </label>
        </>
      );
    }
    if (key === 'units') {
      return (
        <>
          <Field label="Código *"><input value={form.code} onChange={(e) => updateField('code', e.target.value)} required className={inputClass} /></Field>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
          <Field label="Fator fixo (opcional)"><input type="number" step="0.001" min="0" value={form.fixed_factor ?? ''} onChange={(e) => updateField('fixed_factor', e.target.value)} placeholder="Ex: 12 para duzia" className={inputClass} /></Field><label className="flex items-center gap-2.5 cursor-pointer select-none"><input type="checkbox" checked={!!form.is_fractional} onChange={(e) => updateField('is_fractional', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" /><span className="text-sm text-text-primary">Fracionavel (aceita quantidades decimais, ex: 1,250 kg)</span></label>
        </>
      );
    }
    if (key === 'legal_vat_rates') {
      return (
        <>
          <Field label="Categoria (SAF-T) *">
            <select value={form.tax_category || ''} onChange={(e) => updateField('tax_category', e.target.value)} required className={inputClass}>
              <option value="">Selecionar</option>
              <option value="NOR">NOR - Taxa normal</option>
              <option value="RED">RED - Taxa reduzida</option>
              <option value="INT">{'INT - Taxa interm\u00e9dia'}</option>
              <option value="ISE">ISE - Isento</option>
              <option value="OUT">OUT - Outra</option>
            </select>
          </Field>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
          <Field label="Taxa (%) *"><input type="number" step="0.01" value={form.rate} onChange={(e) => updateField('rate', e.target.value)} required className={inputClass} /></Field>
        </>
      );
    }
    if (key === 'withholding_taxes') {
      return (
        <>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
          <Field label="Taxa (%)"><input type="number" step="0.01" value={form.rate} onChange={(e) => updateField('rate', e.target.value)} className={inputClass} /></Field>
          <Field label="Tipo de imposto (SAF-T)">
            <select value={form.tax_type || ''} onChange={(e) => updateField('tax_type', e.target.value)} className={inputClass}>
              <option value="">{'N\u00e3o definido (exportado como Outros)'}</option>
              <option value="II">II - Imposto Industrial</option>
              <option value="IPU">IPU - Imposto Predial Urbano</option>
              <option value="IRT">IRT - Imposto sobre os Rendimentos do Trabalho</option>
              <option value="IS">IS - Imposto de Selo</option>
              <option value="IVA">IVA - IVA cativo</option>
              <option value="IAC">{'IAC - Imposto sobre a Aplica\u00e7\u00e3o de Capitais'}</option>
              <option value="OU">OU - Outros</option>
            </select>
          </Field>
        </>
      );
    }
    if (key === 'fiscal_regimes') {
      return (
        <>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
          <Field label="Descrição"><input value={form.description || ''} onChange={(e) => updateField('description', e.target.value)} className={inputClass} /></Field>
          <div className="grid grid-cols-2 gap-2.5">
            {[['allows_nor', 'NOR (normal)'], ['allows_red', 'RED (reduzida)'], ['allows_ise', 'ISE (isenta)'], ['allows_int', 'INT'], ['allows_out', 'OUT']].map(([f, label]) => (
              <label key={f} className="flex items-center gap-2 text-[13px] text-text-primary cursor-pointer">
                <input type="checkbox" checked={form[f]} onChange={(e) => updateField(f, e.target.checked)} />
                {label}
              </label>
            ))}
          </div>
          <Field label={'Motivo de isen\u00e7\u00e3o obrigat\u00f3rio'}>
            <select value={form.required_exemption_id || ''} onChange={(e) => updateField('required_exemption_id', e.target.value)} className={inputClass}>
              <option value="">{'Nenhum (cada artigo escolhe o seu motivo)'}</option>
              {exemptionMotives.filter((x) => x.is_active).map((x) => <option key={x.id} value={x.id}>{x.code + ' - ' + x.name}</option>)}
            </select>
          </Field>
          {form.required_exemption_id && (
            <Field label="Isenções que continuam a aplicar-se neste regime">
              <p className="text-[11px] text-text-muted -mt-0.5 mb-2">
                Um artigo isento por uma destas razões guarda o seu motivo (em vez do motivo obrigatório) e as suas vendas ficam fora da base do IVA sobre o volume de negócios. Deixe vazio se todas as vendas entram na base.
              </p>
              <div className="max-h-44 overflow-y-auto scrollbar-thin border border-border rounded-md p-2 flex flex-col gap-1.5">
                {exemptionMotives.filter((x) => x.is_active && x.id !== form.required_exemption_id).map((x) => {
                  const kept = (form.kept_exemption_ids || []).includes(x.id);
                  return (
                    <label key={x.id} className="flex items-start gap-2 text-[12px] text-text-primary cursor-pointer">
                      <input type="checkbox" className="mt-0.5" checked={kept} onChange={(e) => updateField('kept_exemption_ids', e.target.checked ? [...(form.kept_exemption_ids || []), x.id] : (form.kept_exemption_ids || []).filter((id) => id !== x.id))} />
                      <span><span className="font-mono">{x.code}</span>{' - ' + x.name}</span>
                    </label>
                  );
                })}
              </div>
            </Field>
          )}
          <Field label={'IVA dedut\u00edvel nas compras (%)'}>
            <input type="number" min="0" max="100" step="0.01" value={form.input_vat_deductible_pct ?? 100} onChange={(e) => updateField('input_vat_deductible_pct', e.target.value)} className={inputClass} />
          </Field>
          <Field label={'IVA sobre o volume de neg\u00f3cios (%)'}>
            <input type="number" min="0" max="100" step="0.01" value={form.turnover_vat_pct ?? 0} onChange={(e) => updateField('turnover_vat_pct', e.target.value)} className={inputClass} />
          </Field>
        </>
      );
    }
    if (key === 'modules') {
      return (
        <>
          <Field label="Nome *"><input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} /></Field>
          <Field label="Descrição"><input value={form.description || ''} onChange={(e) => updateField('description', e.target.value)} className={inputClass} /></Field>
        </>
      );
    }
    return null;
  }

  function itemPrimaryLabel(item) {
    const key = activeCatalog.key;
    if (key === 'countries' || key === 'currencies' || key === 'vat_codes' || key === 'payment_methods' || key === 'document_types' || key === 'units' || key === 'movement_types') return item.code + ' - ' + item.name;
    if (key === 'banks') return item.acronym + ' - ' + item.full_name;
    if (key === 'denominations') return (item.denomination_type === 'NOTA' ? 'Nota ' : 'Moeda ') + Number(item.value).toFixed(2) + ' Kz';
    return item.name;
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Settings size={22} className="text-accent" />
        {section === 'catalogos' ? 'Configurações - Catálogos' : 'Configurações - Sistema'}
      </h2>
      <p className="text-text-muted text-sm mb-6">
        {section === 'catalogos'
          ? 'Catálogos base da plataforma - usados em toda a configuração de empresas, produtos e faturação'
          : 'Identificação do software, Faturação Eletrónica (AGT), site público e assistente - para todas as empresas'}
      </p>

      {section === 'sistema' && (
        <>
          <PlatformSettingsCard />
          <AgtSettingsCard />
          <SiteSettingsCard />
          <AiSettingsCard />
        </>
      )}

      {section !== 'catalogos' ? null : loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {CATALOGS.map((c) => (
            <button
              key={c.key}
              onClick={() => openCatalog(c)}
              className="bg-bg-elevated border border-border hover:border-accent rounded-lg p-5 text-left transition-colors cursor-pointer"
            >
              <c.icon size={20} className="text-accent mb-3" />
              <p className="font-display font-semibold text-text-primary text-sm mb-1">{c.label}</p>
              <p className="text-text-muted text-[12px] font-mono">{counts[c.key] ?? 0} itens</p>
            </button>
          ))}
        </div>
      )}

      <Modal open={!!activeCatalog} onClose={closeCatalogModal} title={activeCatalog?.label || ''} maxWidthClass="max-w-2xl">
        <div className="flex flex-col gap-4">
          <button
            onClick={openCreateForm}
            className="flex items-center justify-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer self-start"
          >
            <Plus size={16} />
            Novo
          </button>

          {itemsLoading ? (
            <div className="flex items-center justify-center py-8 text-text-muted text-sm">
              <Loader2 size={16} className="animate-spin mr-2" />
              A carregar...
            </div>
          ) : (
            <div className="flex flex-col gap-1.5 max-h-[420px] overflow-y-auto scrollbar-thin">
              {items.length === 0 && <p className="text-text-muted text-[13px] text-center py-6">Nenhum item registado</p>}
              {items.map((item) => (
                <div key={item.id} className="flex items-center justify-between gap-2 border border-border rounded-md px-3.5 py-2.5">
                  <span className="text-[13px] text-text-primary truncate">{itemPrimaryLabel(item)}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    <ToggleSwitch checked={item.is_active} disabled={togglingId === item.id} onChange={() => handleToggle(item.id)} />
                    <button onClick={() => openEditForm(item)} className="flex items-center justify-center w-7 h-7 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
                      <Pencil size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      <Modal maxWidthClass={activeCatalog?.key === 'document_types' ? 'max-w-4xl' : undefined} open={formOpen} onClose={() => setFormOpen(false)} title={(editingId ? 'Editar' : 'Novo') + ' - ' + (activeCatalog?.label || '')}>
        {activeCatalog && (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {renderFormFields()}
            <button
              type="submit"
              disabled={saving}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
            >
              {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
              {saving ? 'A guardar...' : editingId ? 'Guardar alterações' : 'Criar'}
            </button>
          </form>
        )}
      </Modal>
    </main>
  );
}

const inputClass = "w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors";

function Field({ label, children }) {
  return (
    <div>
      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{label}</label>
      {children}
    </div>
  );
}

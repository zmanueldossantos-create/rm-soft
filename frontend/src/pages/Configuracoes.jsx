import { useState, useEffect } from 'react';
import { Settings, Globe, DollarSign, MapPin, Building2, Landmark, CreditCard, Calendar, Percent, Plus, Pencil, Loader2, X, FileText, Ruler, ShieldMinus, LayoutGrid, ShieldCheck, Save, Check, ArrowLeftRight, PiggyBank } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import {
  countriesApi, currenciesApi, provincesApi, municipalitiesApi,
  banksApi, paymentMethodsApi, paymentTermsApi, vatCodesApi,
  documentTypesApi, unitsApi, withholdingTaxesApi, movementTypesApi,
  denominationsApi,
} from '../api/catalogs';
import { listFiscalRegimes, createFiscalRegime, updateFiscalRegime, toggleFiscalRegimeStatus } from '../api/fiscalRegime';
import { listModules, createModule, updateModule, toggleModuleStatus } from '../api/module';

const fiscalRegimesApi = {
  list: () => listFiscalRegimes(),
  create: (p) => createFiscalRegime(p.name, p.description, p.allows_nor, p.allows_red, p.allows_ise, p.allows_int, p.allows_out, p.required_exemption_id),
  update: (id, p) => updateFiscalRegime(id, p.name, p.description, p.allows_nor, p.allows_red, p.allows_ise, p.allows_int, p.allows_out, p.required_exemption_id),
  toggle: (id) => toggleFiscalRegimeStatus(id),
};

const modulesApi = {
  list: () => listModules(),
  create: (p) => createModule(p.name, p.description),
  update: (id, p) => updateModule(id, p.name, p.description),
  toggle: (id) => toggleModuleStatus(id),
};

import { extractErrorMessage } from '../utils/errors';
import { getPlatformSettings, updatePlatformSettings } from '../api/admin';

function PlatformSettingsCard() {
  const [values, setValues] = useState({ softwareValidationNumber: '', vendorTaxId: '', productId: '', productVersion: '' });
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

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
        {error && (
          <div className="bg-danger/10 border-l-2 border-danger text-danger px-3 py-2 text-[12px] rounded-r">
            {error}
          </div>
        )}
      </div>
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
  ['requires_customer', 'Exige cliente identificado', 'Obriga a escolher um cliente ao emitir este tipo (nao permite consumidor final)', true],
  ['accepts_credit_note', 'Aceita nota de cr\u00e9dito', 'Permite emitir notas de cr\u00e9dito sobre este tipo', true],
  ['accepts_debit_note', 'Aceita nota de d\u00e9bito', 'Permite emitir notas de d\u00e9bito sobre este tipo', true],
  ['convertible', 'Convert\u00edvel em FT/FR', 'Pode ser transformado em fatura (ex.: pro-forma)', false],
  ['issuable_in_invoices', 'Emitido em Nova Fatura', 'Aparece na lista de tipos do ecr\u00e3 Nova Fatura', true],
  ['issuable_at_pos', 'Emitido na Caixa', 'Aparece na lista de tipos da Caixa', true],
  ['requires_origin', 'Exige documento de origem', 'Tem de referir um documento anterior (ex.: NC, ND, recibo)', false],
  ['has_lines', 'Tem linhas de artigos', 'Desmarcado: documento sem linhas (ex.: recibo)', false],
];

export default function Configuracoes() {
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
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
  const [formError, setFormError] = useState('');

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
      case 'fiscal_regimes': return { name: '', description: '', allows_nor: true, allows_red: true, allows_ise: true, allows_int: false, allows_out: false, required_exemption_id: '' };
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
              Usa conta bancaria
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
          <Field label="Válido desde *"><input type="date" value={form.valid_from} onChange={(e) => updateField('valid_from', e.target.value)} required className={inputClass} /></Field>
          <Field label="Válido até (vazio = sem fim)"><input type="date" value={form.valid_until || ''} onChange={(e) => updateField('valid_until', e.target.value)} className={inputClass} /></Field>
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
            <Field label="Descricao (cartao de selecao)" hint="Frase curta mostrada ao escolher o tipo de documento, ex: A pagar mais tarde - emite FT">
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
        Configurações
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Catálogos base da plataforma - usados em toda a configuração de empresas, produtos e faturação
      </p>

      <PlatformSettingsCard />

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {loading ? (
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
            {formError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>
            )}
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

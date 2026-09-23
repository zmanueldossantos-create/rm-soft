import { useState, useEffect, useMemo } from 'react';
import { Building2, Plus, Loader2, Search, Mail, Phone, Pencil, UserCog, Check, X, KeyRound, Landmark } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import {
  listCompanies, createCompany, updateCompany, toggleCompanyStatus,
  getCompanyGestor,
  listBankAccounts, addBankAccount, updateBankAccount, toggleBankAccountStatus,
} from '../api/admin';
import { extractErrorMessage } from '../utils/errors';
import { listFiscalRegimes } from '../api/fiscalRegime';
import { listModules, getCompanyModules, setCompanyModules, getAdminOverview } from '../api/module';
import { resetUserPassword } from '../api/users';
import { listCompanyVatRates, createCompanyVatRate, updateCompanyVatRate, toggleCompanyVatRate } from '../api/vat';
import { countriesApi, provincesApi, municipalitiesApi, currenciesApi, banksApi } from '../api/catalogs';

function ToggleSwitch({ checked, onChange, disabled }) {
  const trackClass = 'relative w-10 h-5.5 rounded-full transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ' + (checked ? 'bg-success' : 'bg-border');
  const knobClass = 'absolute top-0.5 left-0.5 w-4.5 h-4.5 bg-white rounded-full transition-transform ' + (checked ? 'translate-x-4.5' : 'translate-x-0');

  return (
    <button type="button" role="switch" aria-checked={checked} onClick={onChange} disabled={disabled} className={trackClass}>
      <span className={knobClass} />
    </button>
  );
}

function Field({ label, children, hint }) {
  return (
    <div>
      <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-text-muted mt-1">{hint}</p>}
    </div>
  );
}

const inputClass = "w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors";

const emptyForm = {
  name: '', shortName: '', legalPersonType: 'JURIDICA', nif: '', email: '', phone: '', phone2: '',
  website: '', address: '', city: '', countryId: '', provinceId: '', municipalityId: '',
  commercialRegistrationNumber: '',
  primaryCurrencyId: '', secondaryCurrencyId: '',
  fiscalRegimeId: '',
  usesInvoicing: true, autoSeriesYear: true, allowsFutureSaleDate: false, suggestsLastDocumentDate: false,
  issuanceMode: 'MANUAL', electronicSignatureKey: '',
  moduleIds: [],
  gestorName: '', gestorPhone: '', gestorPassword: '',
};

const emptyBankRow = { bankId: '', accountNumber: '', iban: '', currencyId: '' };

export default function AdminCompanies() {
  const [companies, setCompanies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [togglingId, setTogglingId] = useState(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('gestor');

  const [companyVatRates, setCompanyVatRates] = useState([]);
  const [vatLoading, setVatLoading] = useState(false);
  const [vatFormOpen, setVatFormOpen] = useState(false);
  const [vatEditingId, setVatEditingId] = useState(null);
  const [vatName, setVatName] = useState('');
  const [vatRate, setVatRate] = useState('');
  const [vatCategory, setVatCategory] = useState('NOR');
  const [vatSaving, setVatSaving] = useState(false);
  const [vatFormError, setVatFormError] = useState('');
  const [vatTogglingId, setVatTogglingId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [nifLookupLoading, setNifLookupLoading] = useState(false);
  const [nifLookupMessage, setNifLookupMessage] = useState('');

  const [regimes, setRegimes] = useState([]);
  const [modules, setModules] = useState([]);
  // Sector readiness (from the SUPER_ADMIN overview): id -> { is_ready, ready_note }. A sector
  // still in development is greyed out below - the server refuses it anyway.
  const [sectorInfo, setSectorInfo] = useState({});
  const [countries, setCountries] = useState([]);
  const [provinces, setProvinces] = useState([]);
  const [municipalities, setMunicipalities] = useState([]);
  const [currencies, setCurrencies] = useState([]);
  const [banks, setBanks] = useState([]);

  // Bank accounts - pending rows when creating, fetched+persisted rows when editing.
  const [bankRows, setBankRows] = useState([]);
  const [existingBankAccounts, setExistingBankAccounts] = useState([]);
  const [bankRowSaving, setBankRowSaving] = useState(null);

  const [resetModalOpen, setResetModalOpen] = useState(false);
  const [resetPassword, setResetPassword] = useState('');
  const [resetSaving, setResetSaving] = useState(false);
  const [resetError, setResetError] = useState('');
  const [resetSuccess, setResetSuccess] = useState(false);

  async function openResetModal() {
    setResetPassword('');
    setResetError('');
    setResetSuccess(false);
    setResetModalOpen(true);
  }

  async function handleResetPassword(e) {
    e.preventDefault();
    setResetError('');
    setResetSaving(true);
    try {
      const gestor = await getCompanyGestor(editingId);
      await resetUserPassword(gestor.id, resetPassword);
      setResetSuccess(true);
    } catch (err) {
      setResetError(extractErrorMessage(err, 'Erro ao redefinir palavra-passe'));
    } finally {
      setResetSaving(false);
    }
  }

  useEffect(() => {
    listFiscalRegimes().then((data) => setRegimes(data.filter((r) => r.is_active))).catch(() => {});
    listModules().then((data) => setModules(data.filter((m) => m.is_active))).catch(() => {});
    getAdminOverview().then((ov) => setSectorInfo(Object.fromEntries(ov.modules.map((m) => [m.id, m])))).catch(() => {});
    countriesApi.list().then((data) => setCountries(data.filter((c) => c.is_active))).catch(() => {});
    provincesApi.list().then((data) => setProvinces(data.filter((p) => p.is_active))).catch(() => {});
    municipalitiesApi.list().then((data) => setMunicipalities(data.filter((m) => m.is_active))).catch(() => {});
    currenciesApi.list().then((data) => setCurrencies(data.filter((c) => c.is_active))).catch(() => {});
    banksApi.list().then((data) => setBanks(data.filter((b) => b.is_active))).catch(() => {});
  }, []);

  function toggleModuleSelection(moduleId) {
    setForm((prev) => ({
      ...prev,
      moduleIds: prev.moduleIds.includes(moduleId)
        ? prev.moduleIds.filter((id) => id !== moduleId)
        : [...prev.moduleIds, moduleId],
    }));
  }

  async function loadCompanies() {
    setLoading(true);
    setError('');
    try {
      const data = await listCompanies();
      setCompanies(data);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar empresas'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCompanies();
  }, []);

  const filteredCompanies = useMemo(() => {
    if (!search.trim()) return companies;
    const q = search.toLowerCase();
    return companies.filter(
      (c) => c.name.toLowerCase().includes(q) || c.nif.includes(q) || c.email.toLowerCase().includes(q)
    );
  }, [companies, search]);

  const municipalitiesForProvince = useMemo(
    () => municipalities.filter((m) => m.province_id === form.provinceId),
    [municipalities, form.provinceId]
  );

  const primaryCurrencyOptions = useMemo(
    () => currencies.filter((c) => c.id !== form.secondaryCurrencyId),
    [currencies, form.secondaryCurrencyId]
  );
  const secondaryCurrencyOptions = useMemo(
    () => currencies.filter((c) => c.id !== form.primaryCurrencyId),
    [currencies, form.primaryCurrencyId]
  );

  function openCreateModal() {
    setEditingId(null);
    setForm(emptyForm);
    setBankRows([]);
    setActiveTab('gestor');
    setFormError('');
    setModalOpen(true);
  }

  async function openEditModal(company) {
    setEditingId(company.id);
    setActiveTab('dados');
    setForm({
      name: company.name,
      shortName: company.short_name || '',
      legalPersonType: company.legal_person_type || 'JURIDICA',
      nif: company.nif,
      email: company.email,
      phone: company.phone_number.replace('+244', ''),
      phone2: (company.phone_number_2 || '').replace('+244', ''),
      website: company.website || '',
      address: company.address || '',
      city: company.city || '',
      countryId: '',
      provinceId: company.province_id || '',
      municipalityId: company.municipality_id || '',
      commercialRegistrationNumber: company.commercial_registration_number || '',
      primaryCurrencyId: company.primary_currency_id || '',
      secondaryCurrencyId: company.secondary_currency_id || '',
      fiscalRegimeId: company.fiscal_regime_id || '',
      usesInvoicing: company.uses_invoicing,
      autoSeriesYear: company.auto_series_year,
      allowsFutureSaleDate: company.allows_future_sale_date,
      suggestsLastDocumentDate: company.suggests_last_document_date,
      issuanceMode: company.issuance_mode || 'MANUAL',
      electronicSignatureKey: company.electronic_signature_key || '',
      moduleIds: [],
      gestorName: '', gestorPhone: '', gestorPassword: '',
    });
    setFormError('');
    setModalOpen(true);
    getCompanyModules(company.id).then((data) => setForm((prev) => ({ ...prev, moduleIds: data.map((m) => m.id) }))).catch(() => {});
    listBankAccounts(company.id).then(setExistingBankAccounts).catch(() => setExistingBankAccounts([]));
    loadCompanyVatRates(company.id);
  }

  async function loadCompanyVatRates(companyId) {
    setVatLoading(true);
    try {
      const data = await listCompanyVatRates(companyId);
      setCompanyVatRates(data);
    } catch {
      setCompanyVatRates([]);
    } finally {
      setVatLoading(false);
    }
  }

  function openVatCreateForm() {
    setVatEditingId(null);
    setVatName('');
    setVatRate('');
    setVatCategory('NOR');
    setVatFormError('');
    setVatFormOpen(true);
  }

  function openVatEditForm(vat) {
    setVatEditingId(vat.id);
    setVatName(vat.name);
    setVatRate(String(vat.rate));
    setVatCategory(vat.tax_category);
    setVatFormError('');
    setVatFormOpen(true);
  }

  async function handleVatSubmit(e) {
    e.preventDefault();
    setVatFormError('');
    setVatSaving(true);
    try {
      if (vatEditingId) {
        await updateCompanyVatRate(editingId, vatEditingId, vatName, parseFloat(vatRate), vatCategory);
      } else {
        await createCompanyVatRate(editingId, vatName, parseFloat(vatRate), vatCategory);
      }
      setVatFormOpen(false);
      await loadCompanyVatRates(editingId);
    } catch (err) {
      setVatFormError(extractErrorMessage(err, 'Erro ao guardar taxa de IVA'));
    } finally {
      setVatSaving(false);
    }
  }

  async function handleVatToggle(vatId) {
    setVatTogglingId(vatId);
    try {
      await toggleCompanyVatRate(editingId, vatId);
      await loadCompanyVatRates(editingId);
    } catch {
      // silently ignore - the row's own state stays unchanged, user can retry
    } finally {
      setVatTogglingId(null);
    }
  }

  function closeModal() {
    setModalOpen(false);
    setEditingId(null);
    setForm(emptyForm);
    setBankRows([]);
    setExistingBankAccounts([]);
    setFormError('');
  }

  async function handleNifLookup() {
    setNifLookupMessage('');
    setNifLookupLoading(true);
    try {
      // Placeholder - the real AGT lookup API is not yet available/integrated.
      await new Promise((resolve) => setTimeout(resolve, 500));
      setNifLookupMessage('Funcionalidade dependente da API da AGT - ainda não disponível.');
    } finally {
      setNifLookupLoading(false);
    }
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleProvinceChange(provinceId) {
    setForm((prev) => ({ ...prev, provinceId, municipalityId: '' }));
  }

  function handleUsesInvoicingChange(checked) {
    setForm((prev) => ({
      ...prev,
      usesInvoicing: checked,
      autoSeriesYear: checked ? prev.autoSeriesYear : false,
      allowsFutureSaleDate: checked ? prev.allowsFutureSaleDate : false,
      suggestsLastDocumentDate: checked ? prev.suggestsLastDocumentDate : false,
    }));
  }

  function handleIssuanceModeChange(mode) {
    // Electronic mode uses AGT-issued series codes, not year-based ones - "por ano" is meaningless there.
    setForm((prev) => ({ ...prev, issuanceMode: mode, autoSeriesYear: mode === 'ELETRONICA' ? false : prev.autoSeriesYear }));
  }

  function addBankRow() {
    setBankRows((prev) => [...prev, { ...emptyBankRow }]);
  }

  function updateBankRow(index, field, value) {
    setBankRows((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  }

  function formatIbanRest(raw) {
    // The IBAN's "AO06" is a fixed read-only prefix shown separately - this
    // formats only the part the person actually types, dot-grouped every 4
    // characters for readability (e.g. "1234.5678.9012.3456").
    const alnum = raw.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 21);
    return alnum.match(/.{1,4}/g)?.join('.') || '';
  }

  function removeBankRow(index) {
    setBankRows((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleAddExistingBankAccount(row) {
    setBankRowSaving('new');
    try {
      await addBankAccount(editingId, { bank_id: row.bankId, account_number: row.accountNumber, iban: 'AO06' + row.iban, currency_id: row.currencyId });
      const data = await listBankAccounts(editingId);
      setExistingBankAccounts(data);
      setBankRows([]);
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao adicionar conta bancaria'));
    } finally {
      setBankRowSaving(null);
    }
  }

  async function handleToggleExistingBankAccount(accountId) {
    setBankRowSaving(accountId);
    try {
      await toggleBankAccountStatus(editingId, accountId);
      const data = await listBankAccounts(editingId);
      setExistingBankAccounts(data);
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao atualizar conta bancaria'));
    } finally {
      setBankRowSaving(null);
    }
  }

  function buildPayload() {
    const fullPhone = form.phone.startsWith('+') ? form.phone : '+244' + form.phone.replace(/\s/g, '');
    const fullPhone2 = form.phone2 ? (form.phone2.startsWith('+') ? form.phone2 : '+244' + form.phone2.replace(/\s/g, '')) : null;
    return {
      name: form.name,
      short_name: form.shortName || null,
      legal_person_type: form.legalPersonType,
      nif: form.nif,
      email: form.email,
      phone_number: fullPhone,
      phone_number_2: fullPhone2,
      website: form.website || null,
      address: form.address || null,
      city: form.city || null,
      province_id: form.provinceId || null,
      municipality_id: form.municipalityId || null,
      commercial_registration_number: form.commercialRegistrationNumber || null,
      primary_currency_id: form.primaryCurrencyId || null,
      secondary_currency_id: form.secondaryCurrencyId || null,
      uses_invoicing: form.usesInvoicing,
      auto_series_year: form.autoSeriesYear,
      allows_future_sale_date: form.allowsFutureSaleDate,
      suggests_last_document_date: form.suggestsLastDocumentDate,
      issuance_mode: form.issuanceMode,
      electronic_signature_key: form.issuanceMode === 'ELETRONICA' ? (form.electronicSignatureKey || null) : null,
      fiscal_regime_id: form.fiscalRegimeId || null,
    };
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);

    try {
      if (editingId) {
        await updateCompany(editingId, buildPayload());
        await setCompanyModules(editingId, form.moduleIds);
      } else {
        const fullGestorPhone = form.gestorPhone.startsWith('+') ? form.gestorPhone : '+244' + form.gestorPhone.replace(/\s/g, '');
        const validBankRows = bankRows.filter((r) => r.bankId && r.accountNumber && r.iban && r.currencyId);
        await createCompany({
          ...buildPayload(),
          fiscal_regime_id: form.fiscalRegimeId || null,
          module_ids: form.moduleIds,
          gestor_full_name: form.gestorName,
          gestor_phone_number: fullGestorPhone,
          gestor_password: form.gestorPassword,
          bank_accounts: validBankRows.map((r) => ({ bank_id: r.bankId, account_number: r.accountNumber, iban: 'AO06' + r.iban, currency_id: r.currencyId })),
        });
      }
      closeModal();
      await loadCompanies();
    } catch (err) {
      setFormError(extractErrorMessage(err, editingId ? 'Erro ao atualizar empresa' : 'Erro ao criar empresa'));
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(companyId) {
    setTogglingId(companyId);
    try {
      await toggleCompanyStatus(companyId);
      await loadCompanies();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado da empresa'));
    } finally {
      setTogglingId(null);
    }
  }

  const isFormValid = editingId
    ? form.name && form.nif && form.email && form.phone
    : form.name && form.nif && form.email && form.phone && form.fiscalRegimeId && form.gestorName && form.gestorPhone && form.gestorPassword.length >= 8;

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Building2 size={22} className="text-accent" />
        Gestão de Empresas
      </h2>
      <p className="text-text-muted text-sm mb-6">Criar e gerir as empresas clientes da plataforma</p>

      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="relative max-w-sm w-full sm:w-auto sm:min-w-[260px]">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Pesquisar por nome, NIF ou email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
          />
        </div>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer"
        >
          <Plus size={17} />
          Nova empresa
        </button>
      </div>

      <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
        {loading && (
          <div className="flex items-center justify-center py-16 text-text-muted text-sm">
            <Loader2 size={18} className="animate-spin mr-2" />
            A carregar...
          </div>
        )}
        {error && <div className="px-6 py-4 text-danger text-sm bg-danger/10">{error}</div>}
        {!loading && !error && filteredCompanies.length === 0 && (
          <div className="text-center py-16 text-text-muted text-sm">
            <span className="flex flex-col items-center gap-3">
              {search ? 'Nenhuma empresa encontrada' : 'Nenhuma empresa registada ainda'}
              <Search size={22} className="text-text-muted/40 mt-1" />
            </span>
          </div>
        )}
        {!loading && !error && filteredCompanies.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[680px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Nome</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">NIF</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Contacto</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Estado</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredCompanies.map((c) => (
                  <tr key={c.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                    <td className="px-6 py-4 font-display font-medium text-text-primary">{c.short_name || c.name}</td>
                    <td className="px-6 py-4 font-mono text-text-muted">{c.nif}</td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1 text-[13px] font-mono text-text-muted">
                        <span className="flex items-center gap-1.5"><Mail size={12} className="text-accent shrink-0" />{c.email}</span>
                        <span className="flex items-center gap-1.5"><Phone size={12} className="text-accent shrink-0" />{c.phone_number}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2.5">
                        <ToggleSwitch checked={c.is_active} disabled={togglingId === c.id} onChange={() => handleToggle(c.id)} />
                        <span className={'text-[12px] font-medium ' + (c.is_active ? 'text-success' : 'text-text-muted')}>
                          {c.is_active ? 'Ativa' : 'Inativa'}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => openEditModal(c)}
                        aria-label="Editar empresa"
                        className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer"
                      >
                        <Pencil size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal open={modalOpen} onClose={closeModal} title={editingId ? 'Editar empresa' : 'Nova empresa'} maxWidthClass="max-w-5xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex items-center bg-bg-inset border border-border rounded-md p-0.5 self-start flex-wrap">
            {[
              ...(editingId ? [] : [['gestor', 'Conta do Gestor']]),
              ['dados', 'Dados da Empresa'],
                        ['bancarias', 'Coordenadas Bancárias'],
              ...(editingId ? [['iva', 'Taxas de IVA']] : []),
              ['modulos', 'Módulos'],
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => setActiveTab(key)}
                className={'px-3.5 py-2 rounded text-[12px] font-medium transition-colors cursor-pointer ' + (activeTab === key ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}
              >
                {label}
              </button>
            ))}
          </div>

          {activeTab === 'dados' && (
            <div className="flex flex-col gap-4 min-h-[420px] max-h-[420px] overflow-y-auto scrollbar-thin pr-1">
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <Field label="NIF *">
                  <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
                    <input value={form.nif} onChange={(e) => updateField('nif', e.target.value)} required className="flex-1 bg-transparent border-none px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none" />
                    <button
                      type="button"
                      onClick={handleNifLookup}
                      disabled={!form.nif || nifLookupLoading}
                      aria-label="Consultar NIF na AGT"
                      className="flex items-center justify-center w-11 h-11 text-text-muted hover:text-accent border-l border-border transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                    >
                      {nifLookupLoading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                    </button>
                  </div>
                  {nifLookupMessage && <p className="text-[11px] text-text-muted mt-1">{nifLookupMessage}</p>}
                </Field>
                <Field label="Tipo de pessoa">
                  <Select value={form.legalPersonType} onChange={(v) => updateField('legalPersonType', v)} options={[{ value: 'JURIDICA', label: 'Pessoa coletiva' }, { value: 'FISICA', label: 'Pessoa singular' }]} />
                </Field>
                <Field label="Denominação fiscal *">
                  <input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} />
                </Field>
                <Field label="Nome curto">
                  <input value={form.shortName} onChange={(e) => updateField('shortName', e.target.value)} placeholder="Usado nas listagens" className={inputClass} />
                </Field>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <Field label="Email *">
                  <input type="email" value={form.email} onChange={(e) => updateField('email', e.target.value)} required className={inputClass} />
                </Field>
                <Field label="Website">
                  <input value={form.website} onChange={(e) => updateField('website', e.target.value)} className={inputClass} />
                </Field>
                <Field label="Telefone 1 *">
                  <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
                    <span className="px-3 py-2.5 text-text-muted border-r border-border font-mono text-sm">+244</span>
                    <input value={form.phone} onChange={(e) => updateField('phone', e.target.value)} placeholder="923 456 789" required className="flex-1 bg-transparent border-none px-3 py-2.5 text-sm text-text-primary font-mono outline-none" />
                  </div>
                </Field>
                <Field label="Telefone 2">
                  <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
                    <span className="px-3 py-2.5 text-text-muted border-r border-border font-mono text-sm">+244</span>
                    <input value={form.phone2} onChange={(e) => updateField('phone2', e.target.value)} placeholder="923 456 789" className="flex-1 bg-transparent border-none px-3 py-2.5 text-sm text-text-primary font-mono outline-none" />
                  </div>
                </Field>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <Field label="Moeda principal">
                  <Select value={form.primaryCurrencyId} onChange={(v) => updateField('primaryCurrencyId', v)} options={primaryCurrencyOptions.map((c) => ({ value: c.id, label: c.code + ' - ' + c.name }))} placeholder="Selecionar" />
                </Field>
                <Field label="Moeda secundária">
                  <Select value={form.secondaryCurrencyId} onChange={(v) => updateField('secondaryCurrencyId', v)} options={secondaryCurrencyOptions.map((c) => ({ value: c.id, label: c.code + ' - ' + c.name }))} placeholder="Selecionar" />
                </Field>
                <Field label="Província">
                  <Select value={form.provinceId} onChange={handleProvinceChange} options={provinces.map((p) => ({ value: p.id, label: p.name }))} placeholder="Selecionar" />
                </Field>
                <Field label="Município">
                  <Select value={form.municipalityId} onChange={(v) => updateField('municipalityId', v)} options={municipalitiesForProvince.map((m) => ({ value: m.id, label: m.name }))} placeholder="Selecionar" />
                </Field>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-12 gap-4">
                <div className="sm:col-span-3">
                  <Field label="Cidade">
                    <input value={form.city} onChange={(e) => updateField('city', e.target.value)} className={inputClass} />
                  </Field>
                </div>
                <div className="sm:col-span-3">
                  <Field label="Morada">
                    <input value={form.address} onChange={(e) => updateField('address', e.target.value)} className={inputClass} />
                  </Field>
                </div>
                <div className="sm:col-span-6">
                  <Field label="Número de registo comercial">
                    <input value={form.commercialRegistrationNumber} onChange={(e) => updateField('commercialRegistrationNumber', e.target.value)} className={inputClass} />
                  </Field>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-12 gap-4">
                <div className="sm:col-span-6">
                  <Field label="Regime fiscal">
                    <Select value={form.fiscalRegimeId} onChange={(v) => updateField('fiscalRegimeId', v)} options={regimes.map((r) => ({ value: r.id, label: r.name }))} placeholder="Selecionar regime fiscal" />
                  </Field>
                </div>
                <div className="sm:col-span-6">
                  <Field label="Modo de emissão">
                    <Select value={form.issuanceMode} onChange={handleIssuanceModeChange} options={[{ value: 'MANUAL', label: 'Manual' }, { value: 'ELETRONICA', label: 'Eletrónica' }]} />
                  </Field>
                </div>
              </div>

              {form.issuanceMode === 'ELETRONICA' && (
                <Field label="Assinatura eletrónica (chave privada AGT)">
                  <input type="password" value={form.electronicSignatureKey} onChange={(e) => updateField('electronicSignatureKey', e.target.value)} className={inputClass} />
                </Field>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4" id="usesInvoicingRow">
                <label className="flex items-center gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                  <input type="checkbox" checked={form.usesInvoicing} onChange={(e) => handleUsesInvoicingChange(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                  <span className="text-sm text-text-primary">Usa Facturação</span>
                </label>
                {form.usesInvoicing && (
                  <>
                    <label className="flex items-center gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                      <input type="checkbox" checked={form.autoSeriesYear} disabled={form.issuanceMode === 'ELETRONICA'} onChange={(e) => updateField('autoSeriesYear', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer disabled:opacity-50" />
                      <span className="text-sm text-text-primary">Série automática por ano</span>
                    </label>
                    <label className="flex items-center gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                      <input type="checkbox" checked={form.allowsFutureSaleDate} onChange={(e) => updateField('allowsFutureSaleDate', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                      <span className="text-sm text-text-primary">Permite venda com data futura</span>
                    </label>
                    <label className="flex items-center gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                      <input type="checkbox" checked={form.suggestsLastDocumentDate} onChange={(e) => updateField('suggestsLastDocumentDate', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                      <span className="text-sm text-text-primary">Sugere data do último documento</span>
                    </label>
                  </>
                )}
              </div>

            </div>
          )}

          {activeTab === 'gestor' && !editingId && (
            <div className="flex flex-col gap-4 min-h-[420px]">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Nome completo *">
                  <input value={form.gestorName} onChange={(e) => updateField('gestorName', e.target.value)} required className={inputClass} />
                </Field>
                <Field label="Número de telefone *">
                  <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
                    <span className="px-3 py-2.5 text-text-muted border-r border-border font-mono text-sm">+244</span>
                    <input value={form.gestorPhone} onChange={(e) => updateField('gestorPhone', e.target.value)} placeholder="923 456 789" required className="flex-1 bg-transparent border-none px-3 py-2.5 text-sm text-text-primary font-mono outline-none" />
                  </div>
                </Field>
              </div>
              <Field label="Palavra-passe *" hint="Mínimo 8 caracteres">
                <input type="password" value={form.gestorPassword} onChange={(e) => updateField('gestorPassword', e.target.value)} required minLength={8} className={inputClass} />
              </Field>
            </div>
          )}

          {activeTab === 'iva' && (
            <div className="flex flex-col gap-4 min-h-[420px]">
              <div className="flex items-center justify-between">
                <p className="text-[12px] text-text-muted">Alterar ou desativar uma taxa nao afeta faturas ou produtos ja associados a ela.</p>
                <button type="button" onClick={openVatCreateForm} className="flex items-center gap-1.5 text-accent hover:text-accent-hover text-[13px] font-medium transition-colors cursor-pointer">
                  <Plus size={14} /> Nova taxa
                </button>
              </div>

              {vatFormOpen && (
                <div className="border border-border rounded-md p-3.5 flex flex-col gap-3 bg-bg-inset/40">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <Field label="Nome *"><input value={vatName} onChange={(e) => setVatName(e.target.value)} required className={inputClass} /></Field>
                    <Field label="Taxa (%) *"><input type="number" step="0.01" min="0" value={vatRate} onChange={(e) => setVatRate(e.target.value)} required className={inputClass} /></Field>
                    <Field label="Categoria *">
                      <Select value={vatCategory} onChange={setVatCategory} options={[{ value: 'NOR', label: 'NOR (normal)' }, { value: 'RED', label: 'RED (reduzida)' }, { value: 'ISE', label: 'ISE (isenta)' }, { value: 'INT', label: 'INT' }, { value: 'OUT', label: 'OUT' }]} />
                    </Field>
                  </div>
                  {vatFormError && (
                    <div className="bg-danger/10 border-l-2 border-danger text-danger px-3 py-2 text-[12px] rounded-r">{vatFormError}</div>
                  )}
                  <div className="flex justify-end gap-2">
                    <button type="button" onClick={() => setVatFormOpen(false)} className="text-[12px] text-text-muted hover:text-text-primary px-3 py-1.5 transition-colors cursor-pointer">Cancelar</button>
                    <button type="button" onClick={handleVatSubmit} disabled={vatSaving || !vatName || !vatRate} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-[12px] font-medium rounded-md px-4 py-1.5 flex items-center gap-1.5 transition-colors cursor-pointer">
                      {vatSaving && <Loader2 size={12} className="animate-spin" />}
                      {vatEditingId ? 'Guardar' : 'Criar'}
                    </button>
                  </div>
                </div>
              )}

              {vatLoading ? (
                <div className="flex justify-center py-8"><Loader2 size={20} className="animate-spin text-accent" /></div>
              ) : companyVatRates.length === 0 ? (
                <p className="text-[13px] text-text-muted text-center py-8">Nenhuma taxa de IVA configurada</p>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {companyVatRates.map((vat) => (
                    <div key={vat.id} className={'flex items-center justify-between border border-border rounded-md px-3.5 py-2.5 ' + (vat.is_active ? '' : 'opacity-50')}>
                      <div className="flex items-center gap-3">
                        <span className="font-mono text-sm text-text-primary font-medium">{vat.rate.toFixed(2)}%</span>
                        <span className="text-sm text-text-primary">{vat.name}</span>
                        <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted bg-bg-inset px-1.5 py-0.5 rounded">{vat.tax_category}</span>
                        {!vat.is_active && <span className="text-[10px] font-semibold uppercase tracking-wide text-danger">Inativa</span>}
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button type="button" onClick={() => openVatEditForm(vat)} className="text-text-muted hover:text-accent transition-colors cursor-pointer" title="Editar">
                          <Pencil size={14} />
                        </button>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={vat.is_active}
                          onClick={() => handleVatToggle(vat.id)}
                          disabled={vatTogglingId === vat.id}
                          title={vat.is_active ? 'Desativar' : 'Ativar'}
                          className={'relative inline-flex items-center h-5 w-9 rounded-full transition-colors cursor-pointer disabled:opacity-50 ' + (vat.is_active ? 'bg-accent' : 'bg-bg-inset border border-border')}
                        >
                          <span className={'inline-block w-3.5 h-3.5 rounded-full bg-white shadow transform transition-transform ' + (vat.is_active ? 'translate-x-[18px]' : 'translate-x-[3px]')} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {activeTab === 'modulos' && (
            <div className="min-h-[420px]">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-2 block">Módulos ativos</label>
              <div className="grid grid-cols-2 gap-2">
                {modules.map((m) => {
                  const info = sectorInfo[m.id];
                  const selected = form.moduleIds.includes(m.id);
                  const blocked = !!info && !info.is_ready && !selected;
                  return (
                    <label
                      key={m.id}
                      title={blocked ? (info.ready_note || 'Em desenvolvimento') : undefined}
                      className={'flex items-center gap-2.5 select-none border border-border rounded-md px-3 py-2.5 transition-colors ' + (blocked ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:border-accent')}
                    >
                      <input type="checkbox" checked={selected} disabled={blocked} onChange={() => toggleModuleSelection(m.id)} className="w-4 h-4 accent-accent cursor-pointer" />
                      <span className="text-sm text-text-primary">{m.name}</span>
                      {info && !info.is_ready && <span className="text-[10px] text-accent">(em desenvolvimento)</span>}
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {activeTab === 'bancarias' && (
            <div className="flex flex-col gap-4 min-h-[420px]">
              <p className="text-[12px] text-text-muted">Opcional - se preencher uma linha, todos os campos dessa linha tornam-se obrigatórios</p>

              {editingId && existingBankAccounts.map((acc) => {
                const bank = banks.find((b) => b.id === acc.bank_id);
                const currency = currencies.find((c) => c.id === acc.currency_id);
                return (
                  <div key={acc.id} className="flex items-center justify-between gap-2 border border-border rounded-md px-3.5 py-2.5">
                    <div className="text-[13px] text-text-primary">
                      <span className="font-medium">{bank ? bank.acronym : '...'}</span>
                      <span className="text-text-muted font-mono ml-2">{acc.account_number} · {acc.iban.replace(/^(AO\d{2})(?!\.)/, '$1.')} · {currency?.code}</span>
                    </div>
                    <ToggleSwitch checked={acc.is_active} disabled={bankRowSaving === acc.id} onChange={() => handleToggleExistingBankAccount(acc.id)} />
                  </div>
                );
              })}

              {bankRows.map((row, idx) => (
                <div key={idx} className="flex flex-col gap-2 border border-border rounded-md p-3">
                  <Select value={row.bankId} onChange={(v) => updateBankRow(idx, 'bankId', v)} options={banks.map((b) => ({ value: b.id, label: b.acronym + ' - ' + b.full_name }))} placeholder="Banco" />
                  <div className="flex items-end gap-1.5 w-full">
                    <input value={row.accountNumber} onChange={(e) => updateBankRow(idx, 'accountNumber', e.target.value)} placeholder="Nº conta" className="w-40 shrink-0 bg-bg-inset border border-border rounded-md px-2 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors" />
                    <div className="flex-1 min-w-0 flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
                      <span className="px-2 py-2.5 text-text-muted border-r border-border font-mono text-[13px] shrink-0">AO06</span>
                      <input
                        value={row.iban}
                        onChange={(e) => updateBankRow(idx, 'iban', formatIbanRest(e.target.value))}
                        placeholder="1234.5678..."
                        className="flex-1 min-w-0 bg-transparent border-none px-2 py-2.5 text-sm text-text-primary font-mono outline-none"
                      />
                    </div>
                    <div className="w-16 shrink-0">
                      <Select value={row.currencyId} onChange={(v) => updateBankRow(idx, 'currencyId', v)} options={currencies.map((c) => ({ value: c.id, label: c.code }))} placeholder="Moeda" />
                    </div>
                    <button
                      type="button"
                      onClick={() => editingId ? handleAddExistingBankAccount(row) : removeBankRow(idx)}
                      disabled={editingId ? (!row.bankId || !row.accountNumber || !row.iban || !row.currencyId || bankRowSaving === 'new') : false}
                      className="flex items-center justify-center w-9 h-9 rounded-md border border-border text-text-muted hover:text-danger hover:border-danger transition-colors cursor-pointer shrink-0 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-text-muted disabled:hover:border-border"
                    >
                      {editingId ? (bankRowSaving === 'new' ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />) : <X size={14} />}
                    </button>
                  </div>
                </div>
              ))}

              <button
                type="button"
                onClick={addBankRow}
                className="flex items-center justify-center gap-2 border border-dashed border-border hover:border-accent text-text-muted hover:text-accent text-sm font-medium rounded-md py-2.5 transition-colors cursor-pointer"
              >
                <Landmark size={15} />
                Adicionar conta bancária
              </button>
            </div>
          )}

          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>
          )}

          <button
            type="submit"
            disabled={saving || !isFormValid}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {saving ? 'A guardar...' : editingId ? 'Guardar alterações' : 'Criar empresa'}
          </button>

          {editingId && (
            <button
              type="button"
              onClick={openResetModal}
              className="flex items-center justify-center gap-2 border border-border hover:border-accent text-text-primary text-sm font-medium rounded-md py-2.5 transition-colors cursor-pointer"
            >
              <KeyRound size={15} />
              Redefinir palavra-passe do Gestor
            </button>
          )}
        </form>
      </Modal>

      <Modal open={resetModalOpen} onClose={() => setResetModalOpen(false)} title="Redefinir palavra-passe do Gestor">
        {resetSuccess ? (
          <div className="flex flex-col gap-4">
            <div className="bg-success/10 border-l-2 border-success text-success px-3.5 py-2.5 text-[13px] rounded-r">
              Palavra-passe redefinida com sucesso.
            </div>
            <button type="button" onClick={() => setResetModalOpen(false)} className="bg-accent hover:bg-accent-hover text-white font-semibold text-sm rounded-md py-3 transition-colors cursor-pointer">
              Fechar
            </button>
          </div>
        ) : (
          <form onSubmit={handleResetPassword} className="flex flex-col gap-4">
            <Field label="Nova palavra-passe *" hint="Mínimo 8 caracteres">
              <input type="password" value={resetPassword} onChange={(e) => setResetPassword(e.target.value)} required minLength={8} className={inputClass} />
            </Field>
            {resetError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{resetError}</div>
            )}
            <button
              type="submit"
              disabled={resetSaving || resetPassword.length < 8}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
            >
              {resetSaving ? <Loader2 size={17} className="animate-spin" /> : <KeyRound size={17} />}
              {resetSaving ? 'A guardar...' : 'Redefinir palavra-passe'}
            </button>
          </form>
        )}
      </Modal>
    </main>
  );
}

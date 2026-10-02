import { useState, useEffect, useMemo } from 'react';
import { Users, Plus, Loader2, Search, Mail, Phone, Pencil, X } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import {
  listCustomers, createCustomer, updateCustomer, toggleCustomerStatus,
  suggestCustomerCode, listCustomerBankLinks, addCustomerBankLink, removeCustomerBankLink,
} from '../api/customers';
import { getMyCompanyBankAccounts } from '../api/company';
import { listInvoices } from '../api/invoices';
import { extractErrorMessage } from '../utils/errors';
import { countriesApi, provincesApi, currenciesApi, paymentTermsApi, paymentMethodsApi, withholdingTaxesApi, banksApi } from '../api/catalogs';

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
const readOnlyClass = inputClass + " opacity-60 cursor-not-allowed";
const TAB_CONTENT_CLASS = "flex flex-col gap-4 min-h-[420px] max-h-[420px] overflow-y-auto scrollbar-thin pr-1";

const STATUS_OPTIONS = [
  { value: 'ACTIVO', label: 'Activo' },
  { value: 'APROVADO', label: 'Aprovado' },
  { value: 'BLOQUEADO', label: 'Bloqueado' },
  { value: 'ELIMINADO', label: 'Eliminado' },
  { value: 'INACTIVO', label: 'Inactivo' },
  { value: 'NAO_APROVADO', label: 'Não aprovado' },
  { value: 'POR_ACTIVAR', label: 'Por Activar' },
  { value: 'POR_AVALIAR', label: 'Por Avaliar' },
  { value: 'SUSPENSO', label: 'Suspenso' },
];

const STATUS_COLOR = {
  ACTIVO: 'text-success', APROVADO: 'text-success',
  BLOQUEADO: 'text-danger', ELIMINADO: 'text-danger', SUSPENSO: 'text-danger', NAO_APROVADO: 'text-danger',
  INACTIVO: 'text-text-muted', POR_ACTIVAR: 'text-accent', POR_AVALIAR: 'text-accent',
};

const emptyForm = {
  customerCode: '', legalPersonType: '', name: '', nif: '', isFinalConsumer: false,
  email: '', phone: '', description: '', registrationDate: new Date().toISOString().slice(0, 10),
  fiscalName: '', currencyId: '', countryId: '', provinceId: '', city: '', address: '',
  paymentTermId: '', paymentMethodId: '', withholdingTaxId: '', status: 'ACTIVO',
};

export default function Customers() {
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [togglingId, setTogglingId] = useState(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('identificacao');
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [createdMessage, setCreatedMessage] = useState('');
  const [nifLookupLoading, setNifLookupLoading] = useState(false);
  const [nifLookupMessage, setNifLookupMessage] = useState('');

  const [countries, setCountries] = useState([]);
  const [provinces, setProvinces] = useState([]);
  const [currencies, setCurrencies] = useState([]);
  const [paymentTerms, setPaymentTerms] = useState([]);
  const [paymentMethods, setPaymentMethods] = useState([]);
  const [withholdingTaxes, setWithholdingTaxes] = useState([]);
  const [companyBankAccounts, setCompanyBankAccounts] = useState([]);
  const [banks, setBanks] = useState([]);

  // Existing (persisted) links when editing, or locally-staged ones when creating.
  const [customerBankLinks, setCustomerBankLinks] = useState([]);
  const [pendingBankAccountIds, setPendingBankAccountIds] = useState([]);
  const [selectedBankAccountId, setSelectedBankAccountId] = useState('');
  const [bankLinkSaving, setBankLinkSaving] = useState(false);

  const [customerInvoices, setCustomerInvoices] = useState([]);
  const [invoicesLoading, setInvoicesLoading] = useState(false);

  useEffect(() => {
    countriesApi.list().then((data) => setCountries(data.filter((c) => c.is_active))).catch(() => {});
    provincesApi.list().then((data) => setProvinces(data.filter((p) => p.is_active))).catch(() => {});
    currenciesApi.list().then((data) => setCurrencies(data.filter((c) => c.is_active))).catch(() => {});
    paymentTermsApi.list().then((data) => setPaymentTerms(data.filter((t) => t.is_active))).catch(() => {});
    paymentMethodsApi.list().then((data) => setPaymentMethods(data.filter((m) => m.is_active))).catch(() => {});
    withholdingTaxesApi.list().then((data) => setWithholdingTaxes(data.filter((w) => w.is_active))).catch(() => {});
    getMyCompanyBankAccounts().then((data) => setCompanyBankAccounts(data.filter((a) => a.is_active))).catch(() => {});
    banksApi.list().then((data) => setBanks(data)).catch(() => {});
  }, []);

  async function loadCustomers() {
    setLoading(true);
    setError('');
    try {
      const data = await listCustomers();
      setCustomers(data);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar clientes'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCustomers();
  }, []);

  const filteredCustomers = useMemo(() => {
    if (!search.trim()) return customers;
    const q = search.toLowerCase();
    return customers.filter((c) => c.name.toLowerCase().includes(q) || c.nif.includes(q) || (c.customer_code || '').toLowerCase().includes(q));
  }, [customers, search]);

  async function openCreateModal() {
    setCreatedMessage('');
    setEditingId(null);
    setForm(emptyForm);
    setActiveTab('identificacao');
    setFormError('');
    setNifLookupMessage('');
    setCustomerBankLinks([]);
    setPendingBankAccountIds([]);
    setSelectedBankAccountId('');
    setModalOpen(true);
    try {
      const { suggested_code } = await suggestCustomerCode();
      setForm((prev) => ({ ...prev, customerCode: suggested_code }));
    } catch {
      // suggestion is optional
    }
  }

  function openEditModal(customer) {
    setEditingId(customer.id);
    setActiveTab('identificacao');
    setForm({
      customerCode: customer.customer_code || '',
      legalPersonType: customer.legal_person_type,
      name: customer.name,
      nif: customer.is_final_consumer ? '' : customer.nif,
      isFinalConsumer: customer.is_final_consumer,
      email: customer.email || '',
      phone: (customer.phone_number || '').replace('+244', ''),
      description: customer.description || '',
      registrationDate: customer.registration_date,
      fiscalName: customer.fiscal_name || '',
      currencyId: customer.currency_id || '',
      countryId: customer.country_id || '',
      provinceId: customer.province_id || '',
      city: customer.city || '',
      address: customer.address || '',
      paymentTermId: customer.payment_term_id || '',
      paymentMethodId: customer.payment_method_id || '',
      withholdingTaxId: customer.withholding_tax_id || '',
      status: customer.status,
    });
    setFormError('');
    setNifLookupMessage('');
    setPendingBankAccountIds([]);
    setSelectedBankAccountId('');
    setModalOpen(true);
    listCustomerBankLinks(customer.id).then(setCustomerBankLinks).catch(() => setCustomerBankLinks([]));
  }

  function closeModal() {
    setModalOpen(false);
    setEditingId(null);
    setForm(emptyForm);
    setFormError('');
    setCustomerBankLinks([]);
    setPendingBankAccountIds([]);
    setCustomerInvoices([]);
    setCreatedMessage('');
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  // No default: the user must choose. Leaving "Pessoa singular" also clears "Consumidor Final" -
  // the checkbox is hidden for a pessoa coletiva, but the flag would still force the generic NIF.
  function handleLegalPersonTypeChange(value) {
    setForm((prev) => ({
      ...prev,
      legalPersonType: value,
      isFinalConsumer: value === 'FISICA' ? prev.isFinalConsumer : false,
    }));
  }

  function handleFinalConsumerChange(checked) {
    setForm((prev) => ({ ...prev, isFinalConsumer: checked, nif: checked ? '' : prev.nif }));
  }

  function handleCountryChange(countryId) {
    const country = countries.find((c) => c.id === countryId);
    setForm((prev) => ({ ...prev, countryId, provinceId: '', currencyId: country?.default_currency_id || '' }));
  }

  async function handleNifLookup() {
    setNifLookupMessage('');
    setNifLookupLoading(true);
    try {
      await new Promise((resolve) => setTimeout(resolve, 500));
      setNifLookupMessage('Funcionalidade dependente da API da AGT - ainda não disponível.');
    } finally {
      setNifLookupLoading(false);
    }
  }

  async function handleAddBankLink() {
    if (!selectedBankAccountId) return;
    if (!editingId) {
      // Creation flow - stage locally, no customer id to attach to yet.
      setPendingBankAccountIds((prev) => (prev.includes(selectedBankAccountId) ? prev : [...prev, selectedBankAccountId]));
      setSelectedBankAccountId('');
      return;
    }
    setBankLinkSaving(true);
    try {
      await addCustomerBankLink(editingId, selectedBankAccountId);
      const data = await listCustomerBankLinks(editingId);
      setCustomerBankLinks(data);
      setSelectedBankAccountId('');
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao associar conta bancária'));
    } finally {
      setBankLinkSaving(false);
    }
  }

  function handleRemovePendingBankLink(accountId) {
    setPendingBankAccountIds((prev) => prev.filter((id) => id !== accountId));
  }

  async function handleRemoveBankLink(linkId) {
    try {
      await removeCustomerBankLink(editingId, linkId);
      const data = await listCustomerBankLinks(editingId);
      setCustomerBankLinks(data);
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao remover conta bancária'));
    }
  }

  async function openInvoicingTab() {
    setActiveTab('faturacao');
    if (!editingId) return;
    setInvoicesLoading(true);
    try {
      const data = await listInvoices({ limit: 100 });
      setCustomerInvoices(data.filter((inv) => inv.customer_id === editingId));
    } catch {
      setCustomerInvoices([]);
    } finally {
      setInvoicesLoading(false);
    }
  }

  function buildPayload() {
    const fullPhone = form.phone.startsWith('+') ? form.phone : '+244' + form.phone.replace(/\s/g, '');
    return {
      customer_code: form.customerCode || null,
      legal_person_type: form.legalPersonType,
      name: form.name,
      nif: form.nif,
      is_final_consumer: form.isFinalConsumer,
      email: form.email || null,
      phone_number: fullPhone,
      description: form.description || null,
      registration_date: form.registrationDate || null,
      fiscal_name: form.fiscalName || null,
      currency_id: form.currencyId || null,
      country_id: form.countryId || null,
      province_id: form.provinceId || null,
      city: form.city || null,
      address: form.address || null,
      payment_term_id: form.paymentTermId || null,
      payment_method_id: form.paymentMethodId || null,
      withholding_tax_id: form.legalPersonType === 'JURIDICA' ? (form.withholdingTaxId || null) : null,
      status: form.status,
    };
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setCreatedMessage('');
    setSaving(true);
    try {
      if (editingId) {
        await updateCustomer(editingId, buildPayload());
        closeModal();
      } else {
        const created = await createCustomer(buildPayload());
        for (const accountId of pendingBankAccountIds) {
          await addCustomerBankLink(created.id, accountId);
        }
        // Stay open, reset to a fresh form so another customer can be created right away.
        setCreatedMessage('Cliente "' + created.name + '" criado com sucesso');
        setForm(emptyForm);
        setActiveTab('identificacao');
        setPendingBankAccountIds([]);
        setSelectedBankAccountId('');
        try {
          const { suggested_code } = await suggestCustomerCode();
          setForm((prev) => ({ ...prev, customerCode: suggested_code }));
        } catch {
          // suggestion is optional
        }
      }
      await loadCustomers();
    } catch (err) {
      setFormError(extractErrorMessage(err, editingId ? 'Erro ao atualizar cliente' : 'Erro ao criar cliente'));
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(customerId) {
    setTogglingId(customerId);
    try {
      await toggleCustomerStatus(customerId);
      await loadCustomers();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado do cliente'));
    } finally {
      setTogglingId(null);
    }
  }

  function bankAccountLabel(account) {
    const bank = banks.find((b) => b.id === account.bank_id);
    return (bank ? bank.acronym : '?') + ' - ' + account.account_number + ' · ' + account.iban;
  }

  const isFormValid = form.legalPersonType && form.name && (form.isFinalConsumer || form.nif) && (form.isFinalConsumer || form.phone);

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Users size={22} className="text-accent" />
        Clientes
      </h2>
      <p className="text-text-muted text-sm mb-6">Gerir os clientes da empresa</p>

      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="relative max-w-sm w-full sm:w-auto sm:min-w-[260px]">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Pesquisar por código, nome ou NIF..."
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
          Novo cliente
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
        {!loading && !error && filteredCustomers.length === 0 && (
          <div className="text-center py-16 text-text-muted text-sm">
            <span className="flex flex-col items-center gap-3">
              {search ? 'Nenhum cliente encontrado' : 'Nenhum cliente registado ainda'}
              <Search size={22} className="text-text-muted/40 mt-1" />
            </span>
          </div>
        )}
        {!loading && !error && filteredCustomers.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[720px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Código</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Nome</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">NIF</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Contacto</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Estado</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredCustomers.map((c) => (
                  <tr key={c.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                    <td className="px-6 py-4 font-mono text-text-muted">{c.customer_code || '-'}</td>
                    <td className="px-6 py-4 font-display font-medium text-text-primary">{c.name}</td>
                    <td className="px-6 py-4 font-mono text-text-muted">{c.is_final_consumer ? 'CONSUMIDOR FINAL' : c.nif}</td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col gap-1 text-[13px] font-mono text-text-muted">
                        {c.email && <span className="flex items-center gap-1.5"><Mail size={12} className="text-accent shrink-0" />{c.email}</span>}
                        {c.phone_number && <span className="flex items-center gap-1.5"><Phone size={12} className="text-accent shrink-0" />{c.phone_number}</span>}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={'text-[12px] font-medium ' + (STATUS_COLOR[c.status] || 'text-text-muted')}>
                        {STATUS_OPTIONS.find((s) => s.value === c.status)?.label || c.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => openEditModal(c)}
                        aria-label="Editar cliente"
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

      <Modal open={modalOpen} onClose={closeModal} title={editingId ? 'Editar cliente' : 'Novo cliente'} maxWidthClass="max-w-3xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {createdMessage && (
            <div className="bg-success/10 border-l-2 border-success text-success px-3.5 py-2.5 text-[13px] rounded-r">{createdMessage}</div>
          )}
          <div className="flex items-center bg-bg-inset border border-border rounded-md p-0.5 self-start flex-wrap">
            {[
              ['identificacao', 'Identificação'],
              ['fiscal', 'Dados Fiscais'],
              ['bancarias', 'Contas Bancárias'],
              ...(editingId ? [['faturacao', 'Faturação']] : []),
            ].map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => key === 'faturacao' ? openInvoicingTab() : setActiveTab(key)}
                className={'px-3.5 py-2 rounded text-[12px] font-medium transition-colors cursor-pointer ' + (activeTab === key ? 'bg-accent text-white' : 'text-text-muted hover:text-text-primary')}
              >
                {label}
              </button>
            ))}
          </div>

          {activeTab === 'identificacao' && (
            <div className={TAB_CONTENT_CLASS}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Código do cliente">
                  <input value={form.customerCode} disabled className={readOnlyClass} />
                </Field>
                <Field label="Personalidade jurídica *">
                  <Select value={form.legalPersonType} onChange={handleLegalPersonTypeChange} options={[{ value: 'JURIDICA', label: 'Pessoa coletiva' }, { value: 'FISICA', label: 'Pessoa singular' }]} placeholder="Selecionar" />
                </Field>
              </div>

              {form.legalPersonType === 'FISICA' && (
                <label className="flex items-center gap-2.5 cursor-pointer select-none border border-border rounded-md px-3.5 py-3 hover:border-accent transition-colors">
                  <input type="checkbox" checked={form.isFinalConsumer} onChange={(e) => handleFinalConsumerChange(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                  <span className="text-sm text-text-primary">Consumidor Final</span>
                </label>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Nome *">
                  <input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} />
                </Field>
                <Field label={form.isFinalConsumer ? 'NIF' : 'NIF *'}>
                  <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
                    <input
                      value={form.isFinalConsumer ? 'CONSUMIDOR FINAL' : form.nif}
                      onChange={(e) => updateField('nif', e.target.value)}
                      disabled={form.isFinalConsumer}
                      required={!form.isFinalConsumer}
                      className="flex-1 bg-transparent border-none px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none disabled:opacity-60"
                    />
                    <button
                      type="button"
                      onClick={handleNifLookup}
                      disabled={form.isFinalConsumer || !form.nif || nifLookupLoading}
                      aria-label="Consultar NIF na AGT"
                      className="flex items-center justify-center w-11 h-11 text-text-muted hover:text-accent border-l border-border transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                    >
                      {nifLookupLoading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                    </button>
                  </div>
                  {nifLookupMessage && <p className="text-[11px] text-text-muted mt-1">{nifLookupMessage}</p>}
                </Field>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Email">
                  <input type="email" value={form.email} onChange={(e) => updateField('email', e.target.value)} className={inputClass} />
                </Field>
                <Field label={form.isFinalConsumer ? 'Telefone' : 'Telefone *'}>
                  <div className="flex items-center bg-bg-inset border border-border rounded-md overflow-hidden focus-within:border-accent transition-colors">
                    <span className="px-3 py-2.5 text-text-muted border-r border-border font-mono text-sm">+244</span>
                    <input value={form.phone} onChange={(e) => updateField('phone', e.target.value)} placeholder="923 456 789" required={!form.isFinalConsumer} className="flex-1 bg-transparent border-none px-3 py-2.5 text-sm text-text-primary font-mono outline-none" />
                  </div>
                </Field>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Data de registo">
                  <input type="date" value={form.registrationDate} onChange={(e) => updateField('registrationDate', e.target.value)} className={inputClass} />
                </Field>
                {editingId && (
                  <Field label="Estado">
                    <Select value={form.status} onChange={(v) => updateField('status', v)} options={STATUS_OPTIONS} />
                  </Field>
                )}
              </div>

              <Field label="Descrição / Observação">
                <textarea value={form.description} onChange={(e) => updateField('description', e.target.value)} rows={2} className={inputClass} />
              </Field>
            </div>
          )}

          {activeTab === 'fiscal' && (
            <div className={TAB_CONTENT_CLASS}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="País">
                  <Select value={form.countryId} onChange={handleCountryChange} options={countries.map((c) => ({ value: c.id, label: c.name }))} placeholder="Selecionar" />
                </Field>
                <Field label="Província">
                  <Select
                    value={form.provinceId}
                    onChange={(v) => updateField('provinceId', v)}
                    options={provinces.filter((p) => p.country_id === form.countryId).map((p) => ({ value: p.id, label: p.name }))}
                    placeholder={form.countryId ? 'Selecionar' : 'Selecione um país primeiro'}
                  />
                </Field>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Cidade">
                  <input value={form.city} onChange={(e) => updateField('city', e.target.value)} className={inputClass} />
                </Field>
                <Field label="Moeda">
                  <input value={currencies.find((c) => c.id === form.currencyId)?.code || ''} disabled className={readOnlyClass} />
                </Field>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Denominação fiscal">
                  <input value={form.fiscalName} onChange={(e) => updateField('fiscalName', e.target.value)} className={inputClass} />
                </Field>
                {form.legalPersonType === 'JURIDICA' && (
                  <Field label="Retenção">
                    <Select value={form.withholdingTaxId} onChange={(v) => updateField('withholdingTaxId', v)} options={withholdingTaxes.map((w) => ({ value: w.id, label: w.name }))} placeholder="Sem retenção" />
                  </Field>
                )}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <Field label="Condição de pagamento">
                  <Select value={form.paymentTermId} onChange={(v) => updateField('paymentTermId', v)} options={paymentTerms.map((t) => ({ value: t.id, label: t.name }))} placeholder="Selecionar" />
                </Field>
                <Field label="Método de pagamento">
                  <Select value={form.paymentMethodId} onChange={(v) => updateField('paymentMethodId', v)} options={paymentMethods.filter((m) => m.allows_receipt !== false).map((m) => ({ value: m.id, label: m.name }))} placeholder="Selecionar" />
                </Field>
              </div>
              <Field label="Morada">
                <input value={form.address} onChange={(e) => updateField('address', e.target.value)} className={inputClass} />
              </Field>
            </div>
          )}

          {activeTab === 'bancarias' && (
            <div className={TAB_CONTENT_CLASS}>
              <p className="text-[12px] text-text-muted">Contas bancárias da empresa a apresentar nos documentos de venda deste cliente</p>

              {editingId ? (
                customerBankLinks.map((link) => {
                  const acc = companyBankAccounts.find((a) => a.id === link.company_bank_account_id);
                  return (
                    <div key={link.id} className="flex items-center justify-between gap-2 border border-border rounded-md px-3.5 py-2.5">
                      <span className="text-[13px] text-text-primary font-mono">{acc ? bankAccountLabel(acc) : link.company_bank_account_id}</span>
                      <button type="button" onClick={() => handleRemoveBankLink(link.id)} className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger hover:border-danger transition-colors cursor-pointer">
                        <X size={13} />
                      </button>
                    </div>
                  );
                })
              ) : (
                pendingBankAccountIds.map((accountId) => {
                  const acc = companyBankAccounts.find((a) => a.id === accountId);
                  return (
                    <div key={accountId} className="flex items-center justify-between gap-2 border border-border rounded-md px-3.5 py-2.5">
                      <span className="text-[13px] text-text-primary font-mono">{acc ? bankAccountLabel(acc) : accountId}</span>
                      <button type="button" onClick={() => handleRemovePendingBankLink(accountId)} className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-danger hover:border-danger transition-colors cursor-pointer">
                        <X size={13} />
                      </button>
                    </div>
                  );
                })
              )}

              <div className="flex items-center gap-2">
                <div className="flex-1">
                  <Select
                    value={selectedBankAccountId}
                    onChange={setSelectedBankAccountId}
                    options={companyBankAccounts
                      .filter((a) => !(editingId ? customerBankLinks.map((l) => l.company_bank_account_id) : pendingBankAccountIds).includes(a.id))
                      .map((a) => ({ value: a.id, label: bankAccountLabel(a) }))}
                    placeholder="Selecionar conta da empresa"
                  />
                </div>
                <button type="button" onClick={handleAddBankLink} disabled={!selectedBankAccountId || bankLinkSaving} className="flex items-center justify-center w-10 h-10 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer disabled:opacity-50 shrink-0">
                  {bankLinkSaving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={16} />}
                </button>
              </div>
            </div>
          )}

          {activeTab === 'faturacao' && editingId && (
            <div className={TAB_CONTENT_CLASS}>
              {invoicesLoading ? (
                <div className="flex items-center justify-center py-8 text-text-muted text-sm">
                  <Loader2 size={16} className="animate-spin mr-2" />
                  A carregar...
                </div>
              ) : customerInvoices.length === 0 ? (
                <p className="text-text-muted text-[13px] text-center py-8">Nenhuma fatura para este cliente</p>
              ) : (
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left text-text-muted font-medium px-2 py-2">Documento</th>
                      <th className="text-left text-text-muted font-medium px-2 py-2">Data</th>
                      <th className="text-right text-text-muted font-medium px-2 py-2">Total</th>
                      <th className="text-left text-text-muted font-medium px-2 py-2">Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customerInvoices.map((inv) => (
                      <tr key={inv.id} className="border-b border-border last:border-0">
                        <td className="px-2 py-2 font-mono text-text-primary">{inv.series}/{inv.number}</td>
                        <td className="px-2 py-2 font-mono text-text-muted">{inv.business_date}</td>
                        <td className="px-2 py-2 font-mono text-text-primary text-right">{Number(inv.total).toFixed(2)}</td>
                        <td className="px-2 py-2 text-text-muted">{inv.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>
          )}

          {activeTab !== 'faturacao' && (
            <button
              type="submit"
              disabled={saving || !isFormValid}
              className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
            >
              {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
              {saving ? 'A guardar...' : editingId ? 'Guardar alterações' : 'Criar cliente'}
            </button>
          )}
        </form>
      </Modal>
    </main>
  );
}

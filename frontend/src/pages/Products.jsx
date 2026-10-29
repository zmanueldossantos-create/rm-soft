import { formatKz } from '../utils/format';
import { API_ORIGIN } from '../api/config';
import { useCan } from '../utils/permissions';
import VatReclassify from '../components/VatReclassify';
import ExemptionMotiveField from '../components/ExemptionMotiveField';
import { getPharmacyContext, createPharmaceuticalForm, DISPENSING_REGIMES, medicineSearchText, medicineSummary } from '../api/pharmacy';
import { useState, useEffect, useMemo, useRef } from 'react';
import { Package, Plus, Loader2, Search, Pencil, Barcode, Scale, Upload, X, Pill, Snowflake, BookOpen } from 'lucide-react';
import Modal from '../components/Modal';
import CostHistory from '../components/CostHistory';

import ProductSaleUnits from '../components/ProductSaleUnits';
import Select from '../components/Select';
import { listProducts, createProduct, updateProduct, toggleProductStatus, uploadProductImage, deleteProductImage } from '../api/products';
import { listVatRates, getArticleVatRule } from '../api/vat';
import { listProductCategories, createProductCategory } from '../api/productCategories';
import { unitsApi, withholdingTaxesApi, vatCodesApi } from '../api/catalogs';
import { extractErrorMessage } from '../utils/errors';
import { useToastState } from '../components/Toaster';
import { toast } from '../store/toastStore';
import ReferencePickerModal from '../components/ReferencePickerModal';
import { lookupReferenceBarcode, takeReferenceProducts } from '../api/products';

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

const STATUS_OPTIONS = [
  { value: 'ACTIVO', label: 'Activo' },
  { value: 'INACTIVO', label: 'Inactivo' },
];

const STATUS_COLOR = {
  ACTIVO: 'text-success', INACTIVO: 'text-text-muted',
};

const emptyForm = {
  code: '', name: '', barcode: '', vat_id: '', price: '', price2: '', price3: '', purchasePrice: '',
  minStockThreshold: '0',
  unitOfMeasureId: '', categoryId: '', brand: '',
  managedByBatch: false, managedByStock: true, managedByExpiry: false,
  notAvailablePos: false, preparedInKitchen: false, internalUseOnly: false, status: 'ACTIVO',
  exemptionReasonId: '',
  // Farmácia (only with the Farmácia sector)
  isMedicine: false, activeSubstance: '', pharmaceuticalFormId: '', dosage: '', dispensingRegime: 'LIVRE', coldStorage: false,
};

export default function Products() {
  const can = useCan();
  const [products, setProducts] = useState([]);
  const [vatRates, setVatRates] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]); // grouped actions (VAT reclassification)
  // What the company's regime imposes on an exempt article (M00, M04...): shown locked instead of asked.
  const [articleVatRule, setArticleVatRule] = useState({ regime: null, exemption: null });
  useEffect(() => {
    getArticleVatRule().then(setArticleVatRule).catch(() => setArticleVatRule({ regime: null, exemption: null }));
  }, []);
  // The Farmácia: is it on, its pharmaceutical forms and the motive proposed for a medicine (M11).
  const [pharmacy, setPharmacy] = useState({ enabled: false, medicine_exemption: null, forms: [] });
  useEffect(() => {
    getPharmacyContext().then(setPharmacy).catch(() => setPharmacy({ enabled: false, medicine_exemption: null, forms: [] }));
  }, []);
  const [formModalOpen, setFormModalOpen] = useState(false);
  const [newFormName, setNewFormName] = useState('');
  const [formSaving, setFormSaving] = useState(false);
  const [newFormError, setNewFormError] = useToastState('error');
  const [categories, setCategories] = useState([]);
  const [units, setUnits] = useState([]);
  const [vatCodes, setVatCodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [togglingId, setTogglingId] = useState(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editingProduct, setEditingProduct] = useState(null);
  const [productTab, setProductTab] = useState('geral'); // product sheet tabs: 'geral' | 'unidades' | 'custo'
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useToastState('error');
  const fileInputRef = useRef(null);
  const [imageUploading, setImageUploading] = useState(false);

  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [categoryName, setCategoryName] = useState('');
  const [categorySaving, setCategorySaving] = useState(false);
  const [categoryFormError, setCategoryFormError] = useToastState('error');

  async function loadData() {
    let loaded = [];
    setLoading(true);
    setError('');
    try {
      const [productsData, vatData, categoriesData, unitsData, vatCodesData] = await Promise.all([
        listProducts(), listVatRates(), listProductCategories(), unitsApi.list(), vatCodesApi.list(),
      ]);
      setProducts(productsData.filter((p) => !p.is_raw_material));
      loaded = productsData;
      setVatRates(vatData);
      setCategories(categoriesData.filter((c) => c.is_active));
      setUnits(unitsData.filter((u) => u.is_active));
      setVatCodes(vatCodesData.filter((v) => v.is_active));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar produtos'));
    } finally {
      setLoading(false);
    }
    return loaded;
  }

  // Catálogo de referência: «Importar do catálogo», and a new product's barcode the catalog knows
  const [pickerOpen, setPickerOpen] = useState(false);
  const [referenceHit, setReferenceHit] = useState(null);
  const [takingHit, setTakingHit] = useState(false);
  async function checkReferenceBarcode() {
    const code = (form.barcode || '').trim();
    if (editingId || !code) { setReferenceHit(null); return; }
    try { setReferenceHit(await lookupReferenceBarcode(code)); } catch { setReferenceHit(null); }
  }
  async function useReferenceHit() {
    setTakingHit(true);
    try {
      const result = await takeReferenceProducts([referenceHit.id]);
      const fresh = await loadData();
      const created = fresh.find((p) => p.id === result.product_ids[0]);
      toast.success('«' + referenceHit.name + '» criado a partir do catálogo' + (result.sem_preco ? ' - defina o preço' : ''));
      setReferenceHit(null);
      if (created) openEditModal(created); else closeModal();  // straight to its sheet: the price, the details
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Não foi possível usar o catálogo'));
    } finally {
      setTakingHit(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const vatById = useMemo(() => {
    const map = {};
    vatRates.forEach((v) => { map[v.id] = v; });
    return map;
  }, [vatRates]);

  // «Sem preço»: the articles taken from the reference catalog without a price - off the Caixa until priced
  const [onlyWithoutPrice, setOnlyWithoutPrice] = useState(false);
  const withoutPrice = products.filter((p) => p.awaiting_price).length;
  const filteredProducts = useMemo(() => {
    const base = onlyWithoutPrice ? products.filter((p) => p.awaiting_price) : products;
    if (!search.trim()) return base;
    const q = search.toLowerCase();
    return base.filter(
      (p) => p.code.toLowerCase().includes(q) || p.name.toLowerCase().includes(q) || (p.barcode && p.barcode.includes(q))
        || medicineSearchText(p).includes(q)
    );
  }, [products, search, onlyWithoutPrice]);

  function openCreateModal() {
    setEditingId(null);
    setEditingProduct(null);
    setProductTab('geral');
    setForm({ ...emptyForm });
    setFormError('');
    setReferenceHit(null);
    setModalOpen(true);
  }

  function openEditModal(product) {
    setEditingId(product.id);
    setEditingProduct(product);
    setProductTab('geral');
    setForm({
      code: product.code,
      name: product.name,
      barcode: product.barcode || '',
      vat_id: product.vat_id,
      price: String(product.price),
      price2: product.price_2 != null ? String(product.price_2) : '',  // Preço 2 / Preço 3: empty = not offered
      price3: product.price_3 != null ? String(product.price_3) : '',
      purchasePrice: product.purchase_price != null ? String(product.purchase_price) : '', averageCost: product.average_cost ?? null, // CMP, read only
      minStockThreshold: String(product.min_stock_threshold),
      unitOfMeasureId: product.unit_of_measure_id || '',
      categoryId: product.category_id || '',
      brand: product.brand || '',
      managedByBatch: product.managed_by_batch,
      managedByStock: product.managed_by_stock,
      managedByExpiry: product.managed_by_expiry,
      notAvailablePos: product.not_available_pos,
      preparedInKitchen: !!product.prepared_in_kitchen,
      internalUseOnly: product.internal_use_only,
      status: product.status,
      exemptionReasonId: product.exemption_reason_id || '',
      isMedicine: !!product.is_medicine,
      activeSubstance: product.active_substance || '',
      pharmaceuticalFormId: product.pharmaceutical_form_id || '',
      dosage: product.dosage || '',
      dispensingRegime: product.dispensing_regime || 'LIVRE',
      coldStorage: !!product.cold_storage,
    });
    setFormError('');
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditingId(null);
    setEditingProduct(null);
    setProductTab('geral');
    setForm(emptyForm);
    setFormError('');
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  // Ticking "Medicamento": followed by stock, lot and expiry (forced), and the VAT of a medicine proposed - exempt,
  // motive M11 (CIVA art. 12.º nº1 b) - when the regime lets the article choose it. Everything stays editable.
  function setMedicine(checked) {
    setForm((prev) => {
      const next = { ...prev, isMedicine: checked };
      if (!checked) return next;
      next.managedByStock = true;
      next.managedByBatch = true;
      next.managedByExpiry = true;
      const exempt = vatRates.find((v) => v.tax_category === 'ISE' && v.is_active !== false);
      const motive = pharmacy.medicine_exemption;
      if (exempt) {
        next.vat_id = exempt.id;
        const imposed = articleVatRule.exemption;
        const kept = (articleVatRule.kept || []).map((k) => k.id);
        if (motive && (!imposed || kept.includes(motive.id))) next.exemptionReasonId = motive.id;
      }
      return next;
    });
  }

  async function handleCreateForm(e) {
    e.preventDefault();
    setNewFormError('');
    setFormSaving(true);
    try {
      const created = await createPharmaceuticalForm(newFormName);
      setPharmacy((prev) => ({ ...prev, forms: [...prev.forms, created] }));
      updateField('pharmaceuticalFormId', created.id);
      setFormModalOpen(false);
      setNewFormName('');
    } catch (err) {
      setNewFormError(extractErrorMessage(err, 'Erro ao criar a forma farmacêutica'));
    } finally {
      setFormSaving(false);
    }
  }

  async function handleImageSelect(e) {
    const file = e.target.files?.[0];
    if (!file || !editingId) return;
    setImageUploading(true);
    try {
      const updated = await uploadProductImage(editingId, file);
      setEditingProduct(updated);
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao enviar imagem'));
    } finally {
      setImageUploading(false);
    }
  }

  async function handleImageRemove() {
    if (!editingId) return;
    setImageUploading(true);
    try {
      const updated = await deleteProductImage(editingId);
      setEditingProduct(updated);
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao remover imagem'));
    } finally {
      setImageUploading(false);
    }
  }

  async function handleCreateCategory(e) {
    e.preventDefault();
    setCategoryFormError('');
    setCategorySaving(true);
    try {
      const created = await createProductCategory({ name: categoryName, not_available_purchases: false, not_available_pos: false, not_available_sales: false });
      setCategories((prev) => [...prev, created]);
      updateField('categoryId', created.id);
      setCategoryModalOpen(false);
      setCategoryName('');
    } catch (err) {
      setCategoryFormError(extractErrorMessage(err, 'Erro ao criar categoria'));
    } finally {
      setCategorySaving(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);

    const medicineOn = pharmacy.enabled && form.isMedicine;
    const payload = {
      code: form.code,
      name: form.name,
      barcode: form.barcode || null,
      vat_id: form.vat_id,
      price: parseFloat(form.price),
      price_2: form.price2 !== '' ? parseFloat(form.price2) : null,
      price_3: form.price3 !== '' ? parseFloat(form.price3) : null,
      purchase_price: form.purchasePrice !== '' ? parseFloat(form.purchasePrice) : null,
      min_stock_threshold: parseFloat(form.minStockThreshold || '0'),
      product_type: 'BEM',
      unit_of_measure_id: form.unitOfMeasureId || null,
      category_id: form.categoryId || null,
      brand: form.brand || null,
      managed_by_batch: form.managedByBatch && form.managedByStock,
      managed_by_stock: form.managedByStock,
      managed_by_expiry: form.managedByExpiry && form.managedByStock,
      not_available_pos: form.notAvailablePos,
      prepared_in_kitchen: form.preparedInKitchen,
      internal_use_only: form.internalUseOnly,
      status: form.status,
      exemption_reason_id: form.exemptionReasonId || null,
      is_medicine: medicineOn,
      active_substance: medicineOn ? form.activeSubstance : null,
      pharmaceutical_form_id: medicineOn ? form.pharmaceuticalFormId || null : null,
      dosage: medicineOn ? form.dosage : null,
      dispensing_regime: medicineOn ? form.dispensingRegime : null,
      cold_storage: medicineOn && form.coldStorage,
    };

    try {
      if (editingId) {
        await updateProduct(editingId, payload);
        // a new price: the packs priced «unit price × what they hold» followed it (the server did it) - say so
        const followed = editingProduct && Number(editingProduct.price) !== Number(payload.price);
        toast.success('Produto «' + form.name + '» guardado' + (followed ? ' - as embalagens ao preço proporcional seguem o novo preço' : ''));
      } else {
        await createProduct(payload);
        toast.success('Produto «' + form.name + '» criado');
      }
      closeModal();
      await loadData();
    } catch (err) {
      setFormError(extractErrorMessage(err, editingId ? 'Erro ao atualizar produto' : 'Erro ao criar produto'));
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(productId) {
    setTogglingId(productId);
    try {
      await toggleProductStatus(productId);
      await loadData();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado do produto'));
    } finally {
      setTogglingId(null);
    }
  }

  const selectedVat = vatRates.find((v) => v.id === form.vat_id);
  const isExemptVat = selectedVat && selectedVat.tax_category === 'ISE';
  const imposedExemption = isExemptVat ? articleVatRule.exemption : null;

  const medicineOn = pharmacy.enabled && form.isMedicine;
  const isFormValid = form.code && form.name && form.unitOfMeasureId && form.vat_id && form.price !== '' && (!isExemptVat || imposedExemption || form.exemptionReasonId)
    && (!medicineOn || (form.activeSubstance.trim() && form.dispensingRegime));
  const medicineVatHint = medicineOn && pharmacy.medicine_exemption && form.exemptionReasonId === pharmacy.medicine_exemption.id
    ? 'IVA proposto para um medicamento: isento, ' + pharmacy.medicine_exemption.code + ' (art. 12.º nº1 b) do CIVA). Pode alterar.' : '';
  const formOptions = pharmacy.forms.filter((f) => f.is_active || f.id === form.pharmaceuticalFormId).map((f) => ({ value: f.id, label: f.name }));

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Package size={22} className="text-accent" />
        Produtos
      </h2>
      <p className="text-text-muted text-sm mb-6">Gerir a ficha de produtos da sua empresa</p>

      {vatRates.length === 0 && !loading && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-4 py-3 text-sm rounded-r mb-5">
          Nenhuma taxa de IVA disponível - contacte o administrador da plataforma.
        </div>
      )}

      <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
        <div className="relative max-w-md w-full sm:w-auto sm:min-w-[380px]">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
                        placeholder={pharmacy.enabled ? 'Pesquisar por código, nome, substância ativa ou código de barras...' : 'Pesquisar por código, nome ou código de barras...'}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
          />
        </div>
        {(withoutPrice > 0 || onlyWithoutPrice) && (
          <button type="button" onClick={() => setOnlyWithoutPrice((v) => !v)}
            className={'flex items-center gap-2 text-sm font-medium px-3.5 py-2.5 rounded-md border transition-colors cursor-pointer ' + (onlyWithoutPrice ? 'bg-amber-500 border-amber-500 text-amber-950' : 'border-amber-500/60 text-amber-500 [.light_&]:text-amber-700 hover:border-amber-500')}>
            Sem preço ({withoutPrice})
          </button>
        )}
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setPickerOpen(true)}
          className="flex items-center gap-2 border border-border hover:border-accent text-text-primary font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer"
        >
          <BookOpen size={16} />
          Importar do catálogo
        </button>
        <button
          onClick={openCreateModal}
          disabled={vatRates.length === 0}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer"
        >
          <Plus size={17} />
          Novo produto
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
        {!loading && !error && filteredProducts.length === 0 && (
          <div className="text-center py-16 text-text-muted text-sm">
            <span className="flex flex-col items-center gap-3">{search ? 'Nenhum produto encontrado' : 'Nenhum produto registado ainda'}<Search size={22} className="text-text-muted/40 mt-1" /></span>
          </div>
        )}
        <VatReclassify kind="products" selectedIds={selectedIds} setSelectedIds={setSelectedIds} vatRates={vatRates} vatCodes={vatCodes} articleVatRule={articleVatRule} onDone={loadData} />
        {!loading && !error && filteredProducts.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[820px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-3 py-3 w-8"><input type="checkbox" checked={filteredProducts.length > 0 && filteredProducts.every((x) => selectedIds.includes(x.id))} onChange={(e) => setSelectedIds(e.target.checked ? filteredProducts.map((x) => x.id) : [])} /></th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Imagem</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Código</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Nome</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Preço</th>
                <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Preço compra</th>
                <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Custo médio</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">IVA</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Estado</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredProducts.map((p) => (
                  <tr key={p.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                    <td className="px-3 py-4"><input type="checkbox" checked={selectedIds.includes(p.id)} onChange={(e) => setSelectedIds((prev) => (e.target.checked ? [...prev, p.id] : prev.filter((x) => x !== p.id)))} /></td>
                    <td className="px-6 py-4">
                      {p.image_path ? (
                        <img src={API_ORIGIN + p.image_path} alt={p.name} className="w-9 h-9 rounded object-cover border border-border" />
                      ) : (
                        <div className="w-9 h-9 rounded bg-bg-inset border border-border flex items-center justify-center text-text-muted/40"><Package size={14} /></div>
                      )}
                    </td>
                    <td className="px-6 py-4 font-mono text-text-muted">{p.code}</td>
                    <td className="px-6 py-4 font-display font-medium text-text-primary">
                      <div className="flex items-center gap-2">
                        {p.name}
                        {p.barcode && <Barcode size={13} className="text-text-muted" />}
                        {p.awaiting_price && (
                          <span title="Vindo do catálogo de referência sem preço: fora da Caixa até definir o preço"
                            className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 [.light_&]:text-amber-700">
                            Sem preço
                          </span>
                        )}
                        {p.unit_is_fractional && <Scale size={13} className="text-text-muted" />}
                        {p.is_medicine && p.dispensing_regime !== 'LIVRE' && (
                          <span title={DISPENSING_REGIMES.find((r) => r.value === p.dispensing_regime)?.label} className={'text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ' + (p.dispensing_regime === 'RECEITA_ESPECIAL' ? 'bg-danger/10 text-danger' : 'bg-amber-500/10 text-amber-500 [.light_&]:text-amber-700')}>
                            {p.dispensing_regime === 'RECEITA_ESPECIAL' ? 'Receita especial' : 'Receita'}
                          </span>
                        )}
                        {p.is_medicine && p.cold_storage && <span title="Conservar no frio"><Snowflake size={13} className="text-sky-400" /></span>}
                      </div>
                      {p.is_medicine && <p className="text-[12px] font-normal text-text-muted mt-0.5">{medicineSummary(p)}</p>}
                    </td>
                    <td className="px-6 py-4 font-mono text-text-primary whitespace-nowrap">
                      {formatKz(p.price)} Kz
                      {(p.price_2 != null || p.price_3 != null) && (
                        <p className="text-[11px] text-text-muted mt-0.5">
                          {[p.price_2 != null && 'P2 ' + formatKz(p.price_2), p.price_3 != null && 'P3 ' + formatKz(p.price_3)].filter(Boolean).join(' · ')}
                        </p>
                      )}
                    </td>
                    <td className="px-6 py-4 font-mono text-text-primary">{p.purchase_price != null ? formatKz(p.purchase_price) : '-'}</td>
                    <td className="px-6 py-4 font-mono text-text-primary">{p.average_cost != null ? formatKz(p.average_cost) : '-'}</td>
                    <td className="px-6 py-4 font-mono text-text-muted">{vatById[p.vat_id] ? vatById[p.vat_id].rate + '%' : '-'}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2.5">
                        <ToggleSwitch checked={p.is_active} disabled={togglingId === p.id} onChange={() => handleToggle(p.id)} />
                        <span className={'text-[12px] font-medium ' + (STATUS_COLOR[p.status] || (p.is_active ? 'text-success' : 'text-text-muted'))}>
                          {STATUS_OPTIONS.find((s) => s.value === p.status)?.label || (p.is_active ? 'Ativo' : 'Inativo')}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => openEditModal(p)}
                        aria-label="Editar produto"
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

      <Modal open={modalOpen} onClose={closeModal} title={editingId ? 'Editar produto' : 'Novo produto'} maxWidthClass="max-w-5xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 h-[70vh] overflow-y-auto scrollbar-thin pr-1">

          <div className="flex gap-1 border-b border-border -mt-1">
            {[['geral', 'Geral'], ['unidades', 'Unidades e embalagens'], ['custo', 'Histórico do custo']].map(([key, label]) => (
              <button key={key} type="button" disabled={key !== 'geral' && !editingId} title={key !== 'geral' && !editingId ? 'Guarde o produto primeiro' : undefined} onClick={() => setProductTab(key)} className={'px-3.5 py-2 text-[13px] font-medium border-b-2 -mb-px transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ' + (productTab === key ? 'border-accent text-text-primary' : 'border-transparent text-text-muted hover:text-text-primary')}>
                {label}
              </button>
            ))}
          </div>
          <div className={productTab === 'geral' ? 'flex flex-col gap-4' : 'hidden'}>
          {editingId && (
            <div className="flex items-center gap-3">
              {editingProduct?.image_path ? (
                <img src={API_ORIGIN + editingProduct.image_path} alt="" className="w-16 h-16 rounded-md object-cover border border-border" />
              ) : (
                <div className="w-16 h-16 rounded-md bg-bg-inset border border-border flex items-center justify-center text-text-muted/40"><Package size={22} /></div>
              )}
              <button type="button" onClick={() => fileInputRef.current?.click()} disabled={imageUploading} className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[13px] font-medium rounded-md px-3 py-2 transition-colors cursor-pointer disabled:opacity-50">
                {imageUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                Alterar imagem
              </button>
              {editingProduct?.image_path && (
                <button type="button" onClick={handleImageRemove} disabled={imageUploading} className="flex items-center gap-1.5 border border-border hover:border-danger hover:text-danger text-text-muted text-[13px] font-medium rounded-md px-3 py-2 transition-colors cursor-pointer disabled:opacity-50">
                  <X size={14} />
                  Remover
                </button>
              )}
              <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={handleImageSelect} />
            </div>
          )}

          {/* the sheet's fields, four per line */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-start">
            <Field label="Código *">
              <input value={form.code} onChange={(e) => updateField('code', e.target.value)} required className={inputClass} />
            </Field>
            <Field label="Nome *">
              <input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} />
            </Field>
            <Field label="Marca">
              <input value={form.brand} onChange={(e) => updateField('brand', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Categoria">
              <div className="flex items-center gap-1.5">
                <div className="flex-1">
                  <Select value={form.categoryId} onChange={(v) => updateField('categoryId', v)} options={categories.map((c) => ({ value: c.id, label: c.name }))} placeholder="Selecionar" />
                </div>
                <button type="button" onClick={() => setCategoryModalOpen(true)} className="flex items-center justify-center w-10 h-10 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer shrink-0">
                  <Plus size={15} />
                </button>
              </div>
            </Field>
            <Field label="Código de barras">
              <input value={form.barcode} onChange={(e) => { updateField('barcode', e.target.value); setReferenceHit(null); }}
                onBlur={checkReferenceBarcode}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); checkReferenceBarcode(); } }}
                className={inputClass} />
              {referenceHit && (
                referenceHit.owned ? (
                  <p className="text-[12px] text-amber-500 [.light_&]:text-amber-700 mt-1.5">Já tem «{referenceHit.name}» com este código de barras.</p>
                ) : (
                  <div className="mt-1.5 flex flex-col gap-1.5 border border-accent/50 bg-accent/5 rounded-md px-3 py-2">
                    <span className="text-[12px] text-text-primary flex items-start gap-1.5">
                      <BookOpen size={13} className="text-accent shrink-0 mt-0.5" />
                      <span>No catálogo: <b>{referenceHit.name}</b>{referenceHit.units.length ? ' · ' + referenceHit.units.length + (referenceHit.units.length === 1 ? ' embalagem' : ' embalagens') : ''}{referenceHit.price == null ? ' · sem preço' : ''}</span>
                    </span>
                    <button type="button" onClick={useReferenceHit} disabled={takingHit}
                      className="self-start text-[12px] font-semibold text-accent hover:underline cursor-pointer disabled:opacity-50">
                      {takingHit ? 'A criar...' : 'Usar o catálogo (com as embalagens) →'}
                    </button>
                  </div>
                )
              )}
            </Field>
            <Field label="Unidade base *">
              <Select value={form.unitOfMeasureId} onChange={(v) => updateField('unitOfMeasureId', v)} options={units.map((u) => ({ value: u.id, label: u.code + ' - ' + u.name }))} placeholder="Selecionar" />
            </Field>
            <Field label="Preço 1 (Kz) *">
              <input type="number" step="0.01" min="0" value={form.price} onChange={(e) => updateField('price', e.target.value)} required className={inputClass} />
            </Field>
            <Field label="Preço 2 (Kz)">
              <input type="number" step="0.01" min="0" value={form.price2} onChange={(e) => updateField('price2', e.target.value)} placeholder="Opcional" className={inputClass} />
            </Field>
            <Field label="Preço 3 (Kz)">
              <input type="number" step="0.01" min="0" value={form.price3} onChange={(e) => updateField('price3', e.target.value)} placeholder="Opcional" className={inputClass} />
            </Field>
            <Field label="Preço de compra (Kz)">
              <input type="number" step="0.01" min="0" value={form.purchasePrice} onChange={(e) => updateField('purchasePrice', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Custo médio (calculado)">
              <div className="w-full bg-bg-inset/40 border border-border rounded-md px-3.5 py-2.5 text-sm font-mono text-text-muted cursor-not-allowed" title="Calculado pelo sistema a partir das entradas de stock com preço de compra (custo médio ponderado)">
                {form.averageCost != null ? formatKz(form.averageCost) + ' Kz' : 'Sem custo conhecido'}
              </div>
            </Field>
            <Field label="IVA *">
              <Select value={form.vat_id} onChange={(v) => updateField('vat_id', v)} options={vatRates.filter((v) => v.is_active !== false || v.id === form.vat_id).map((v) => ({ value: v.id, label: v.name + ' (' + v.rate + '%)' }))} placeholder="Selecionar IVA" />
            </Field>
            <Field label="Limite mínimo stock">
              <input type="number" step="0.001" min="0" value={form.minStockThreshold} onChange={(e) => updateField('minStockThreshold', e.target.value)} className={inputClass} />
            </Field>
            {isExemptVat && (
              <Field label="Motivo de isenção *">
                <ExemptionMotiveField rule={articleVatRule} value={form.exemptionReasonId} onChange={(v) => updateField('exemptionReasonId', v)} vatCodes={vatCodes} lockedClass={inputClass} />
              </Field>
            )}
            {editingId && (
              <Field label="Estado">
                <Select value={form.status} onChange={(v) => updateField('status', v)} options={STATUS_OPTIONS} />
              </Field>
            )}
          </div>

          {medicineVatHint && <p className="text-[12px] text-text-muted -mt-2">{medicineVatHint}</p>}

          {pharmacy.enabled && (
            <div className="flex flex-col gap-3 pt-3 border-t border-border">
              <label className="flex items-center gap-2.5 cursor-pointer select-none self-start">
                <input type="checkbox" checked={form.isMedicine} onChange={(e) => setMedicine(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                <Pill size={15} className="text-accent" />
                <span className="text-sm font-medium text-text-primary">Medicamento</span>
                <span className="text-[12px] text-text-muted">- gerido por lote e validade; vendido primeiro o lote que expira primeiro</span>
              </label>
              {form.isMedicine && (
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                  <Field label="Substância ativa (DCI) *" hint="Permite encontrar todas as marcas no POS">
                    <input value={form.activeSubstance} onChange={(e) => updateField('activeSubstance', e.target.value)} placeholder="Ex.: Paracetamol" className={inputClass} />
                  </Field>
                  <Field label="Forma farmacêutica">
                    <div className="flex items-center gap-1.5">
                      <div className="flex-1 min-w-0">
                        <Select value={form.pharmaceuticalFormId} onChange={(v) => updateField('pharmaceuticalFormId', v)} options={formOptions} placeholder="Selecionar" />
                      </div>
                      {can('pharmaceutical_forms:manage') && (
                        <button type="button" onClick={() => setFormModalOpen(true)} title="Nova forma farmacêutica" className="flex items-center justify-center w-10 h-10 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer shrink-0">
                          <Plus size={15} />
                        </button>
                      )}
                    </div>
                  </Field>
                  <Field label="Dosagem">
                    <input value={form.dosage} onChange={(e) => updateField('dosage', e.target.value)} placeholder="Ex.: 500 mg" className={inputClass} />
                  </Field>
                  <Field label="Regime de dispensa *">
                    <Select value={form.dispensingRegime} onChange={(v) => updateField('dispensingRegime', v)} options={DISPENSING_REGIMES} />
                  </Field>
                  <label className="flex items-center gap-2.5 cursor-pointer select-none sm:col-span-4">
                    <input type="checkbox" checked={form.coldStorage} onChange={(e) => updateField('coldStorage', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
                    <Snowflake size={14} className="text-sky-400" />
                    <span className="text-sm text-text-primary">Conservar no frio</span>
                  </label>
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-3 gap-2 pt-2 border-t border-border">
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" disabled={medicineOn} checked={form.managedByStock} onChange={(e) => updateField('managedByStock', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer disabled:cursor-not-allowed" />
              <span className="text-sm text-text-primary">Gerido por stocks</span>
            </label>
            {/* followed by lot / expiry: the lot is entered on every entry, exits take the first to expire (FEFO) */}
            <label className={'flex items-center gap-2.5 select-none ' + (form.managedByStock ? 'cursor-pointer' : 'opacity-50 cursor-not-allowed')} title="Número de lote obrigatório em cada entrada de stock. Só pode ser alterado com o stock a zero.">
              <input type="checkbox" disabled={!form.managedByStock || medicineOn} checked={form.managedByBatch && form.managedByStock} onChange={(e) => updateField('managedByBatch', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer disabled:cursor-not-allowed" />
              <span className="text-sm text-text-primary">Gerido por lotes</span>
            </label>
            <label className={'flex items-center gap-2.5 select-none ' + (form.managedByStock ? 'cursor-pointer' : 'opacity-50 cursor-not-allowed')} title="Data de validade obrigatória em cada entrada de stock; um lote expirado nunca é vendido. Só pode ser alterado com o stock a zero.">
              <input type="checkbox" disabled={!form.managedByStock || medicineOn} checked={form.managedByExpiry && form.managedByStock} onChange={(e) => updateField('managedByExpiry', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer disabled:cursor-not-allowed" />
              <span className="text-sm text-text-primary">Gerido por validade</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.notAvailablePos} onChange={(e) => updateField('notAvailablePos', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Não disponível POS</span>
            </label>
            {can('kitchen:view') && (
<label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.preparedInKitchen} onChange={(e) => updateField('preparedInKitchen', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Preparado na cozinha</span>
            </label>
)}
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.internalUseOnly} onChange={(e) => updateField('internalUseOnly', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Uso interno apenas</span>
            </label>
          </div>

          </div>
          {editingId && productTab === 'unidades' && <ProductSaleUnits productId={editingId} baseUnitId={form.unitOfMeasureId} units={units} />}
          {editingId && productTab === 'custo' && <CostHistory productId={editingId} />}


          <button
            type="submit"
            disabled={saving || !isFormValid}
            className={(productTab === 'geral' ? '' : 'hidden ') + 'mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors'}
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {saving ? 'A guardar...' : editingId ? 'Guardar alterações' : 'Criar produto'}
          </button>
        </form>
      </Modal>

      <Modal open={formModalOpen} onClose={() => { setFormModalOpen(false); setNewFormError(''); }} title="Nova forma farmacêutica">
        <form onSubmit={handleCreateForm} className="flex flex-col gap-4">
          <Field label="Nome *">
            <input value={newFormName} onChange={(e) => setNewFormName(e.target.value)} placeholder="Ex.: Comprimido" required className={inputClass} />
          </Field>
          <button type="submit" disabled={formSaving || !newFormName.trim()} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
            {formSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            Criar forma farmacêutica
          </button>
        </form>
      </Modal>

      <Modal open={categoryModalOpen} onClose={() => { setCategoryModalOpen(false); setCategoryFormError(''); }} title="Nova categoria">
        <form onSubmit={handleCreateCategory} className="flex flex-col gap-4">
          <Field label="Nome *">
            <input value={categoryName} onChange={(e) => setCategoryName(e.target.value)} required className={inputClass} />
          </Field>
          <button
            type="submit"
            disabled={categorySaving || !categoryName}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {categorySaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            Criar categoria
          </button>
        </form>
      </Modal>
      <ReferencePickerModal open={pickerOpen} onClose={() => setPickerOpen(false)} units={units} onTaken={() => loadData()} />
    </main>
  );
}

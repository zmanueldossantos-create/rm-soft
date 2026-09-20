import { useState, useEffect, useMemo, useRef } from 'react';
import { Package, Plus, Loader2, Search, Pencil, Barcode, Scale, Upload, X } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { listProducts, createProduct, updateProduct, toggleProductStatus, uploadProductImage, deleteProductImage } from '../api/products';
import { listVatRates } from '../api/vat';
import { listProductCategories, createProductCategory } from '../api/productCategories';
import { unitsApi, withholdingTaxesApi, vatCodesApi } from '../api/catalogs';
import { extractErrorMessage } from '../utils/errors';

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
  code: '', name: '', barcode: '', vat_id: '', price: '', purchasePrice: '',
  minStockThreshold: '0', expiryDate: '', isSoldByWeight: false,
  unitOfMeasureId: '', categoryId: '', brand: '',
  managedByBatch: false, managedByStock: true, managedByExpiry: false,
  notAvailablePos: false, internalUseOnly: false, subjectToReturn: false, status: 'ACTIVO',
  exemptionReasonId: '',
};

export default function Products() {
  const [products, setProducts] = useState([]);
  const [vatRates, setVatRates] = useState([]);
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
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const fileInputRef = useRef(null);
  const [imageUploading, setImageUploading] = useState(false);

  const [categoryModalOpen, setCategoryModalOpen] = useState(false);
  const [categoryName, setCategoryName] = useState('');
  const [categorySaving, setCategorySaving] = useState(false);
  const [categoryFormError, setCategoryFormError] = useState('');

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      const [productsData, vatData, categoriesData, unitsData, vatCodesData] = await Promise.all([
        listProducts(), listVatRates(), listProductCategories(), unitsApi.list(), vatCodesApi.list(),
      ]);
      setProducts(productsData.filter((p) => !p.is_raw_material));
      setVatRates(vatData);
      setCategories(categoriesData.filter((c) => c.is_active));
      setUnits(unitsData.filter((u) => u.is_active));
      setVatCodes(vatCodesData.filter((v) => v.is_active));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar produtos'));
    } finally {
      setLoading(false);
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

  const filteredProducts = useMemo(() => {
    if (!search.trim()) return products;
    const q = search.toLowerCase();
    return products.filter(
      (p) => p.code.toLowerCase().includes(q) || p.name.toLowerCase().includes(q) || (p.barcode && p.barcode.includes(q))
    );
  }, [products, search]);

  function openCreateModal() {
    setEditingId(null);
    setEditingProduct(null);
    setForm({ ...emptyForm });
    setFormError('');
    setModalOpen(true);
  }

  function openEditModal(product) {
    setEditingId(product.id);
    setEditingProduct(product);
    setForm({
      code: product.code,
      name: product.name,
      barcode: product.barcode || '',
      vat_id: product.vat_id,
      price: String(product.price),
      purchasePrice: product.purchase_price != null ? String(product.purchase_price) : '',
      minStockThreshold: String(product.min_stock_threshold),
      expiryDate: product.expiry_date || '',
      isSoldByWeight: product.is_sold_by_weight,
      unitOfMeasureId: product.unit_of_measure_id || '',
      categoryId: product.category_id || '',
      brand: product.brand || '',
      managedByBatch: product.managed_by_batch,
      managedByStock: product.managed_by_stock,
      managedByExpiry: product.managed_by_expiry,
      notAvailablePos: product.not_available_pos,
      internalUseOnly: product.internal_use_only,
      subjectToReturn: product.subject_to_return,
      status: product.status,
      exemptionReasonId: product.exemption_reason_id || '',
    });
    setFormError('');
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditingId(null);
    setEditingProduct(null);
    setForm(emptyForm);
    setFormError('');
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
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

    const payload = {
      code: form.code,
      name: form.name,
      barcode: form.barcode || null,
      vat_id: form.vat_id,
      price: parseFloat(form.price),
      purchase_price: form.purchasePrice !== '' ? parseFloat(form.purchasePrice) : null,
      min_stock_threshold: parseFloat(form.minStockThreshold || '0'),
      expiry_date: form.expiryDate || null,
      is_sold_by_weight: form.isSoldByWeight,
      product_type: 'BEM',
      unit_of_measure_id: form.unitOfMeasureId || null,
      category_id: form.categoryId || null,
      brand: form.brand || null,
      managed_by_batch: form.managedByBatch,
      managed_by_stock: form.managedByStock,
      managed_by_expiry: form.managedByExpiry,
      not_available_pos: form.notAvailablePos,
      internal_use_only: form.internalUseOnly,
      subject_to_return: form.subjectToReturn,
      status: form.status,
      exemption_reason_id: form.exemptionReasonId || null,
    };

    try {
      if (editingId) {
        await updateProduct(editingId, payload);
      } else {
        await createProduct(payload);
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
  const isExemptVat = selectedVat && Number(selectedVat.rate) === 0;

  const isFormValid = form.code && form.name && form.vat_id && form.price !== '' && (!isExemptVat || form.exemptionReasonId);

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
        <div className="relative max-w-sm w-full sm:w-auto sm:min-w-[260px]">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Pesquisar por código, nome ou código de barras..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
          />
        </div>
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
        {!loading && !error && filteredProducts.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[820px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Imagem</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Código</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Nome</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Preço</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">IVA</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Estado</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredProducts.map((p) => (
                  <tr key={p.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                    <td className="px-6 py-4">
                      {p.image_path ? (
                        <img src={'http://127.0.0.1:8001' + p.image_path} alt={p.name} className="w-9 h-9 rounded object-cover border border-border" />
                      ) : (
                        <div className="w-9 h-9 rounded bg-bg-inset border border-border flex items-center justify-center text-text-muted/40"><Package size={14} /></div>
                      )}
                    </td>
                    <td className="px-6 py-4 font-mono text-text-muted">{p.code}</td>
                    <td className="px-6 py-4 font-display font-medium text-text-primary">
                      <div className="flex items-center gap-2">
                        {p.name}
                        {p.barcode && <Barcode size={13} className="text-text-muted" />}
                        {p.is_sold_by_weight && <Scale size={13} className="text-text-muted" />}
                      </div>
                    </td>
                    <td className="px-6 py-4 font-mono text-text-primary">{p.price.toFixed(2)} Kz</td>
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

      <Modal open={modalOpen} onClose={closeModal} title={editingId ? 'Editar produto' : 'Novo produto'} maxWidthClass="max-w-4xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 max-h-[70vh] overflow-y-auto scrollbar-thin pr-1">
          {editingId && (
            <div className="flex items-center gap-3">
              {editingProduct?.image_path ? (
                <img src={'http://127.0.0.1:8001' + editingProduct.image_path} alt="" className="w-16 h-16 rounded-md object-cover border border-border" />
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

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="Código *">
              <input value={form.code} onChange={(e) => updateField('code', e.target.value)} required className={inputClass} />
            </Field>
            <Field label="Nome *">
              <input value={form.name} onChange={(e) => updateField('name', e.target.value)} required className={inputClass} />
            </Field>
            <Field label="Marca">
              <input value={form.brand} onChange={(e) => updateField('brand', e.target.value)} className={inputClass} />
            </Field>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
              <input value={form.barcode} onChange={(e) => updateField('barcode', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Unidade de medida">
              <Select value={form.unitOfMeasureId} onChange={(v) => updateField('unitOfMeasureId', v)} options={units.map((u) => ({ value: u.id, label: u.code + ' - ' + u.name }))} placeholder="Selecionar" />
            </Field>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="Preço de venda (Kz) *">
              <input type="number" step="0.01" min="0" value={form.price} onChange={(e) => updateField('price', e.target.value)} required className={inputClass} />
            </Field>
            <Field label="Preço de compra (Kz)">
              <input type="number" step="0.01" min="0" value={form.purchasePrice} onChange={(e) => updateField('purchasePrice', e.target.value)} className={inputClass} />
            </Field>
            <Field label="IVA *">
              <Select value={form.vat_id} onChange={(v) => updateField('vat_id', v)} options={vatRates.map((v) => ({ value: v.id, label: v.name + ' (' + v.rate + '%)' }))} placeholder="Selecionar IVA" />
            </Field>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Field label="Limite mínimo stock">
              <input type="number" step="0.001" min="0" value={form.minStockThreshold} onChange={(e) => updateField('minStockThreshold', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Data limite de consumo">
              <input type="date" value={form.expiryDate} onChange={(e) => updateField('expiryDate', e.target.value)} className={inputClass} />
            </Field>
            {isExemptVat && (
              <Field label="Motivo de isenção *">
                <Select value={form.exemptionReasonId} onChange={(v) => updateField('exemptionReasonId', v)} options={vatCodes.filter((c) => Number(c.rate) === 0).map((c) => ({ value: c.id, label: c.code + ' - ' + c.name }))} placeholder="Selecionar motivo" />
              </Field>
            )}
            {editingId && (
              <Field label="Estado">
                <Select value={form.status} onChange={(v) => updateField('status', v)} options={STATUS_OPTIONS} />
              </Field>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border">
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.managedByStock} onChange={(e) => updateField('managedByStock', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Gerido por stocks</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.managedByBatch} onChange={(e) => updateField('managedByBatch', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Gerido por lotes</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.managedByExpiry} onChange={(e) => updateField('managedByExpiry', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Gerido por validade</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.isSoldByWeight} onChange={(e) => updateField('isSoldByWeight', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Vendido ao peso</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.notAvailablePos} onChange={(e) => updateField('notAvailablePos', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Não disponível POS</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.internalUseOnly} onChange={(e) => updateField('internalUseOnly', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Uso interno apenas (nunca vendavel)</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={form.subjectToReturn} onChange={(e) => updateField('subjectToReturn', e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Sujeito a devolução</span>
            </label>
          </div>

          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>
          )}

          <button
            type="submit"
            disabled={saving || !isFormValid}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {saving ? 'A guardar...' : editingId ? 'Guardar alterações' : 'Criar produto'}
          </button>
        </form>
      </Modal>

      <Modal open={categoryModalOpen} onClose={() => { setCategoryModalOpen(false); setCategoryFormError(''); }} title="Nova categoria">
        <form onSubmit={handleCreateCategory} className="flex flex-col gap-4">
          <Field label="Nome *">
            <input value={categoryName} onChange={(e) => setCategoryName(e.target.value)} required className={inputClass} />
          </Field>
          {categoryFormError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{categoryFormError}</div>
          )}
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
    </main>
  );
}

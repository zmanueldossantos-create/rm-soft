import ProductSaleUnits from '../components/ProductSaleUnits';
import { useState, useEffect } from 'react';
import { Wheat, Plus, Loader2, Search, Pencil } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { listProducts, createProduct, updateProduct, toggleProductStatus } from '../api/products';
import { unitsApi } from '../api/catalogs';
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

const emptyForm = {
  code: '',
  name: '',
  unit_of_measure_id: '',
  min_stock_threshold: '0',
};

export default function MateriaPrima() {
  const [materials, setMaterials] = useState([]);
  const [units, setUnits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [togglingId, setTogglingId] = useState(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [sheetTab, setSheetTab] = useState('geral'); // 'geral' | 'embalagens'
  const [editingMaterial, setEditingMaterial] = useState(null); // its last purchase price and average cost

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      const [productsData, unitsData] = await Promise.all([listProducts(), unitsApi.list()]);
      setMaterials(productsData.filter((p) => p.is_raw_material));
      setUnits(unitsData);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar materias-primas'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const filteredMaterials = materials.filter((m) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return m.code.toLowerCase().includes(q) || m.name.toLowerCase().includes(q);
  });

  function openCreateModal() {
    setEditingId(null);
    setEditingMaterial(null);
    setSheetTab('geral');
    setForm(emptyForm);
    setFormError('');
    setModalOpen(true);
  }

  function openEditModal(material) {
    setEditingId(material.id);
    setEditingMaterial(material);
    setSheetTab('geral');
    setForm({
      code: material.code,
      name: material.name,
      unit_of_measure_id: material.unit_of_measure_id || '',
      min_stock_threshold: String(material.min_stock_threshold),
    });
    setFormError('');
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditingId(null);
    setForm(emptyForm);
    setFormError('');
  }

  function updateField(field, value) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);

    const payload = {
      code: form.code,
      name: form.name,
      barcode: null,
      // A raw material is never sold, so it carries no VAT rate (the server accepts a missing one only
      // for is_raw_material) and no exemption reason.
      vat_id: null,
      price: 0,
      // Kept as it is: only receptions set the last purchase price (an edit must never erase it).
      purchase_price: editingMaterial ? editingMaterial.purchase_price ?? null : null,
      min_stock_threshold: parseFloat(form.min_stock_threshold || '0'),
      expiry_date: null,
      product_type: 'BEM',
      unit_of_measure_id: form.unit_of_measure_id || null,
      is_raw_material: true,
      not_available_pos: true,
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
      setFormError(extractErrorMessage(err, editingId ? 'Erro ao atualizar materia-prima' : 'Erro ao criar materia-prima'));
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(materialId) {
    setTogglingId(materialId);
    try {
      await toggleProductStatus(materialId);
      await loadData();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado'));
    } finally {
      setTogglingId(null);
    }
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Wheat size={22} className="text-accent" />
        Matéria-prima
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Ingredientes e insumos de produção - nunca aparecem no catálogo de venda nem em faturas
      </p>

      <div className="flex items-end justify-between mb-5 flex-wrap gap-3">
        <div className="relative max-w-sm w-full sm:w-auto sm:min-w-[260px]">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text"
            placeholder="Pesquisar por código ou nome..."
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
          Nova matéria-prima
        </button>
      </div>

      <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
        {loading && (
          <div className="flex items-center justify-center py-16 text-text-muted text-sm">
            <Loader2 size={18} className="animate-spin mr-2" />
            A carregar...
          </div>
        )}

        {error && (
          <div className="px-6 py-4 text-danger text-sm bg-danger/10">{error}</div>
        )}

        {!loading && !error && filteredMaterials.length === 0 && (
          <div className="text-center py-16 text-text-muted text-sm">
            <span className="flex flex-col items-center gap-3">
              {search ? 'Nenhuma materia-prima encontrada' : 'Nenhuma materia-prima registada ainda'}
              <Search size={22} className="text-text-muted/40 mt-1" />
            </span>
          </div>
        )}

        {!loading && !error && filteredMaterials.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[560px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Código</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Nome</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Unidade</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Limite mínimo</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Estado</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredMaterials.map((m) => (
                  <tr key={m.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                    <td className="px-6 py-4 font-mono text-text-muted">{m.code}</td>
                    <td className="px-6 py-4 font-display font-medium text-text-primary">{m.name}</td>
                    <td className="px-6 py-4 font-mono text-text-muted">{units.find((u) => u.id === m.unit_of_measure_id)?.code || '-'}</td>
                    <td className="px-6 py-4 font-mono text-text-muted text-right">{m.min_stock_threshold}</td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2.5">
                        <ToggleSwitch checked={m.is_active} disabled={togglingId === m.id} onChange={() => handleToggle(m.id)} />
                        <span className={'text-[12px] font-medium ' + (m.is_active ? 'text-success' : 'text-text-muted')}>
                          {m.is_active ? 'Ativo' : 'Inativo'}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => openEditModal(m)}
                        aria-label="Editar materia-prima"
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

      <Modal open={modalOpen} onClose={closeModal} title={editingId ? 'Editar matéria-prima' : 'Nova matéria-prima'} maxWidthClass="max-w-3xl">
        <div className="flex gap-1 mb-4 border-b border-border">
          {[['geral', 'Geral'], ['embalagens', 'Embalagens']].map(([key, label]) => (
            <button key={key} type="button" disabled={key === 'embalagens' && !editingId}
              title={key === 'embalagens' && !editingId ? 'Crie primeiro a mat\u00e9ria-prima' : undefined}
              onClick={() => setSheetTab(key)}
              className={'px-3 py-2 text-[13px] -mb-px border-b-2 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ' + (sheetTab === key ? 'border-accent text-text-primary font-medium' : 'border-transparent text-text-muted hover:text-text-primary')}>
              {label}
            </button>
          ))}
        </div>
        {/* Same height for both tabs, the content scrolls inside. */}
        <div className="h-[60vh] overflow-y-auto scrollbar-thin pr-1">
        <form onSubmit={handleSubmit} className={(sheetTab === 'geral' ? '' : 'hidden ') + 'grid grid-cols-1 sm:grid-cols-2 gap-4'}>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Código *</label>
            <input
              value={form.code}
              onChange={(e) => updateField('code', e.target.value)}
              required
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome *</label>
            <input
              value={form.name}
              onChange={(e) => updateField('name', e.target.value)}
              placeholder="Ex: Farinha de trigo"
              required
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Unidade base *</label>
            <Select
              value={form.unit_of_measure_id}
              onChange={(v) => updateField('unit_of_measure_id', v)}
              options={units.map((u) => ({ value: u.id, label: u.code + ' - ' + u.name }))}
              placeholder="Selecionar unidade"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Limite mínimo stock</label>
            <input
              type="number"
              step="0.001"
              min="0"
              value={form.min_stock_threshold}
              onChange={(e) => updateField('min_stock_threshold', e.target.value)}
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>

          {editingMaterial && (() => {
            const base = units.find((u) => u.id === form.unit_of_measure_id)?.code || '';
            const kz = (v) => (v == null ? '\u2013' : Number(v).toLocaleString('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Kz' + (base ? ' / ' + base : ''));
            return (
              <div className="sm:col-span-2 grid grid-cols-2 gap-3 rounded-md border border-border bg-bg-inset/40 px-3.5 py-2.5 text-[12px]">
                <div><p className="text-text-muted">{'\u00daltimo pre\u00e7o de compra'}</p><p className="font-mono text-text-primary">{kz(editingMaterial.purchase_price)}</p></div>
                <div><p className="text-text-muted">{'Custo m\u00e9dio'}</p><p className="font-mono text-text-primary">{kz(editingMaterial.average_cost)}</p></div>
                <p className="col-span-2 text-[11px] text-text-muted">{'Atualizados pelas rece\u00e7\u00f5es de stock.'}</p>
              </div>
            );
          })()}
          {formError && (
            <div className="sm:col-span-2 bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
              {formError}
            </div>
          )}

          <button
            type="submit"
            disabled={saving || !form.code || !form.name || !form.unit_of_measure_id}
            className="sm:col-span-2 mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {saving ? 'A guardar...' : editingId ? 'Guardar alterações' : 'Criar matéria-prima'}
          </button>
        </form>
              {editingId && sheetTab === 'embalagens' && (
          <ProductSaleUnits productId={editingId} baseUnitId={form.unit_of_measure_id} units={units} noPrice />
        )}
        </div>
      </Modal>
    </main>
  );
}

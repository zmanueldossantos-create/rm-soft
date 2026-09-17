import { useState, useEffect } from 'react';
import { Factory, Plus, Loader2, Search, Pencil, ChefHat } from 'lucide-react';
import Modal from '../components/Modal';
import Select from '../components/Select';
import { listProducts } from '../api/products';
import { getRecipe, setRecipe } from '../api/recipe';
import { listWarehouses, getProductionEstimate, produceStock } from '../api/stock';
import apiClient from '../api/client';
import { unitsApi } from '../api/catalogs';
import { extractErrorMessage } from '../utils/errors';

async function getProductsWithRecipe() {
  const res = await apiClient.get('/products/with-recipe');
  return res.data;
}

const emptyRecipeForm = { productId: '', batchYield: '1', rows: [] };
const emptyProduceForm = { productId: '', warehouseId: '', quantity: '', reason: '' };

export default function Producao() {
  const [allProducts, setAllProducts] = useState([]);
  const [units, setUnits] = useState([]);
  const [configuredProducts, setConfiguredProducts] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  const [recipeModalOpen, setRecipeModalOpen] = useState(false);
  const [recipeIsEditing, setRecipeIsEditing] = useState(false);
  const [recipeForm, setRecipeForm] = useState(emptyRecipeForm);
  const [recipeLoading, setRecipeLoading] = useState(false);
  const [recipeSaving, setRecipeSaving] = useState(false);
  const [recipeError, setRecipeError] = useState('');

  const [produceModalOpen, setProduceModalOpen] = useState(false);
  const [produceForm, setProduceForm] = useState(emptyProduceForm);
  const [produceEstimate, setProduceEstimate] = useState(null);
  const [produceEstimateLoading, setProduceEstimateLoading] = useState(false);
  const [produceEstimateError, setProduceEstimateError] = useState('');
  const [produceSaving, setProduceSaving] = useState(false);
  const [produceError, setProduceError] = useState('');

  async function loadData() {
    setLoading(true);
    setError('');
    try {
      const [productsData, configuredData, warehousesData, unitsData] = await Promise.all([
        listProducts(),
        getProductsWithRecipe(),
        listWarehouses(),
        unitsApi.list(),
      ]);
      setAllProducts(productsData.filter((p) => p.is_active));
      setConfiguredProducts(configuredData);
      setWarehouses(warehousesData);
      setUnits(unitsData);
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar produção'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  const filteredConfigured = configuredProducts.filter((p) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return p.code.toLowerCase().includes(q) || p.name.toLowerCase().includes(q);
  });

  // Products that can be picked to configure a NEW recipe for - any active,
  // non-raw-material product (raw materials are never "produced" themselves).
  const producibleCandidates = allProducts.filter((p) => !p.is_raw_material && p.product_type === 'BEM');

  // Ingredients can be raw materials OR other finished products (multi-level
  // recipes, e.g. a sandwich using bread as an ingredient) - just not itself.
  function ingredientOptions(excludeProductId) {
    return allProducts.filter((p) => p.id !== excludeProductId && p.product_type === 'BEM');
  }

  function openNewRecipeModal() {
    setRecipeForm({ productId: '', batchYield: '1', batchYieldUnitId: '', rows: [] });
    setRecipeError('');
    setRecipeIsEditing(false);
    setRecipeModalOpen(true);
  }

  async function openEditRecipeModal(product) {
    setRecipeForm({ productId: product.id, batchYield: String(product.batch_yield), batchYieldUnitId: product.unit_of_measure_id || '', rows: [] });
    setRecipeError('');
    setRecipeIsEditing(true);
    setRecipeModalOpen(true);
    setRecipeLoading(true);
    try {
      const data = await getRecipe(product.id);
      setRecipeForm((prev) => ({
        ...prev,
        rows: data.map((r) => ({ ingredientProductId: r.ingredient_product_id, quantityPerBatch: String(r.quantity_per_batch) })),
      }));
    } catch (err) {
      setRecipeError(extractErrorMessage(err, 'Erro ao carregar receita'));
    } finally {
      setRecipeLoading(false);
    }
  }

  async function handleRecipeProductChange(productId) {
    const chosen = producibleCandidates.find((p) => p.id === productId);
    setRecipeForm((prev) => ({ ...prev, productId, batchYieldUnitId: chosen?.unit_of_measure_id || '', rows: [] }));
    const existing = configuredProducts.find((p) => p.id === productId);
    if (existing) {
      setRecipeLoading(true);
      try {
        const data = await getRecipe(productId);
        setRecipeForm((prev) => ({
          ...prev,
          batchYield: String(existing.batch_yield),
          rows: data.map((r) => ({ ingredientProductId: r.ingredient_product_id, quantityPerBatch: String(r.quantity_per_batch) })),
        }));
      } catch (err) {
        setRecipeError(extractErrorMessage(err, 'Erro ao carregar receita'));
      } finally {
        setRecipeLoading(false);
      }
    }
  }

  function closeRecipeModal() {
    setRecipeModalOpen(false);
    setRecipeForm(emptyRecipeForm);
    setRecipeError('');
  }

  function addRecipeRow() {
    setRecipeForm((prev) => ({ ...prev, rows: [...prev.rows, { ingredientProductId: '', quantityPerBatch: '' }] }));
  }

  function updateRecipeRow(index, field, value) {
    setRecipeForm((prev) => ({
      ...prev,
      rows: prev.rows.map((r, i) => (i === index ? { ...r, [field]: value } : r)),
    }));
  }

  function removeRecipeRow(index) {
    setRecipeForm((prev) => ({ ...prev, rows: prev.rows.filter((_, i) => i !== index) }));
  }

  async function handleSaveRecipe() {
    setRecipeError('');
    setRecipeSaving(true);
    try {
      const validRows = recipeForm.rows.filter((r) => r.ingredientProductId && r.quantityPerBatch);
      await setRecipe(recipeForm.productId, parseFloat(recipeForm.batchYield || '1'), validRows.map((r) => ({
        ingredientProductId: r.ingredientProductId,
        quantityPerBatch: parseFloat(r.quantityPerBatch),
      })));
      closeRecipeModal();
      await loadData();
    } catch (err) {
      setRecipeError(extractErrorMessage(err, 'Erro ao guardar receita'));
    } finally {
      setRecipeSaving(false);
    }
  }

  function fractionHint(value) {
    const num = parseFloat(value);
    if (!num || num <= 0) return null;
    const commonFractions = [
      [0.25, '1/4'], [0.5, '1/2'], [0.75, '3/4'],
      [0.333, '1/3'], [0.667, '2/3'],
      [0.2, '1/5'], [0.4, '2/5'], [0.6, '3/5'], [0.8, '4/5'],
    ];
    const whole = Math.floor(num);
    const frac = num - whole;
    if (frac < 0.001) return null; // already a whole number, no hint needed
    const match = commonFractions.find(([f]) => Math.abs(frac - f) < 0.01);
    if (!match) return null;
    return (whole > 0 ? whole + ' + ' : '') + match[1];
  }

  function openProduceModal(product) {
    setProduceForm({ productId: product.id, warehouseId: warehouses[0]?.id || '', quantity: '', numBatches: '', batchYield: product.batch_yield, reason: '' });
    setProduceEstimate(null);
    setProduceEstimateError('');
    setProduceError('');
    setProduceModalOpen(true);
    if (warehouses[0]) {
      loadEstimate(product.id, warehouses[0].id);
    }
  }

  async function loadEstimate(productId, warehouseId) {
    if (!productId || !warehouseId) return;
    setProduceEstimateLoading(true);
    setProduceEstimateError('');
    try {
      const estimate = await getProductionEstimate(warehouseId, productId);
      setProduceEstimate(estimate);
    } catch (err) {
      setProduceEstimateError(extractErrorMessage(err, 'Erro ao estimar produção'));
    } finally {
      setProduceEstimateLoading(false);
    }
  }

  function handleQuantityChange(value) {
    const yieldPerBatch = produceForm.batchYield || 1;
    const numBatches = value ? String(parseFloat(value) / yieldPerBatch) : '';
    setProduceForm((prev) => ({ ...prev, quantity: value, numBatches }));
  }

  function handleBatchesChange(value) {
    const yieldPerBatch = produceForm.batchYield || 1;
    const quantity = value ? String(parseFloat(value) * yieldPerBatch) : '';
    setProduceForm((prev) => ({ ...prev, numBatches: value, quantity }));
  }

  function handleProduceWarehouseChange(warehouseId) {
    setProduceForm((prev) => ({ ...prev, warehouseId }));
    setProduceEstimate(null);
    loadEstimate(produceForm.productId, warehouseId);
  }

  function closeProduceModal() {
    setProduceModalOpen(false);
    setProduceForm(emptyProduceForm);
    setProduceEstimate(null);
  }

  const produceExceedsCapacity = produceEstimate && produceForm.quantity && parseFloat(produceForm.quantity) > produceEstimate.max_units;

  async function handleProduceSubmit(e) {
    e.preventDefault();
    setProduceError('');
    setProduceSaving(true);
    try {
      await produceStock(produceForm.warehouseId, produceForm.productId, parseFloat(produceForm.quantity), produceForm.reason || null);
      closeProduceModal();
    } catch (err) {
      setProduceError(extractErrorMessage(err, 'Erro ao produzir'));
    } finally {
      setProduceSaving(false);
    }
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Factory size={22} className="text-accent" />
        Produção
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Receitas por lote e produção de produtos - transforma matéria-prima e outros produtos em stock vendável
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
          onClick={openNewRecipeModal}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer"
        >
          <ChefHat size={17} />
          Configurar nova receita
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

        {!loading && !error && filteredConfigured.length === 0 && (
          <div className="text-center py-16 text-text-muted text-sm">
            <span className="flex flex-col items-center gap-3">
              {search ? 'Nenhum produto encontrado' : 'Nenhuma receita configurada ainda - clique em "Configurar nova receita"'}
              <Search size={22} className="text-text-muted/40 mt-1" />
            </span>
          </div>
        )}

        {!loading && !error && filteredConfigured.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[600px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Código</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Produto</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Rendimento do lote</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredConfigured.map((p) => (
                  <tr key={p.id} className="border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors">
                    <td className="px-6 py-4 font-mono text-text-muted">{p.code}</td>
                    <td className="px-6 py-4 font-display font-medium text-text-primary">{p.name}</td>
                    <td className="px-6 py-4 font-mono text-text-muted text-right">{p.batch_yield} {units.find((u) => u.id === p.unit_of_measure_id)?.code || 'UN'}</td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => openProduceModal(p)}
                          className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white font-medium text-[12px] px-3 py-2 rounded-md transition-colors cursor-pointer"
                        >
                          <Factory size={13} />
                          Produzir
                        </button>
                        <button
                          onClick={() => openEditRecipeModal(p)}
                          aria-label="Editar receita"
                          className="inline-flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer"
                        >
                          <Pencil size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      
      <Modal open={recipeModalOpen} onClose={closeRecipeModal} title="Configurar receita" maxWidthClass="max-w-2xl">
        <div className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Produto a configurar *</label>
            <Select
              value={recipeForm.productId}
              onChange={handleRecipeProductChange}
              options={producibleCandidates.map((p) => ({ value: p.id, label: p.code + ' - ' + p.name }))}
              placeholder="Selecionar produto"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Rendimento do lote *</label>
            <div className="flex items-center gap-2">
              <input
                type="number"
                step="1"
                min="1"
                value={recipeForm.batchYield}
                onChange={(e) => setRecipeForm((prev) => ({ ...prev, batchYield: e.target.value }))}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
              />
              <div className="w-32 shrink-0">
                <Select
                  value={recipeForm.batchYieldUnitId}
                  onChange={(v) => setRecipeForm((prev) => ({ ...prev, batchYieldUnitId: v }))}
                  options={units.map((u) => ({ value: u.id, label: u.code }))}
                  placeholder="Unidade"
                />
              </div>
            </div>
            <p className="text-[11px] text-text-muted mt-1">Quantas unidades 1 lote completo desta receita produz</p>
          </div>


              {recipeLoading ? (
                <div className="flex items-center justify-center py-6 text-text-muted text-sm">
                  <Loader2 size={16} className="animate-spin mr-2" />
                  A carregar receita...
                </div>
              ) : (
                <>
                  <div className="flex flex-col gap-2.5">
                    <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">Ingredientes por lote</p>
                    {recipeForm.rows.map((row, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <div className="flex-1">
                          <Select
                            value={row.ingredientProductId}
                            onChange={(v) => updateRecipeRow(idx, 'ingredientProductId', v)}
                            options={ingredientOptions(recipeForm.productId).map((p) => ({ value: p.id, label: p.code + ' - ' + p.name + (p.is_raw_material ? ' (matéria-prima)' : '') }))}
                            placeholder="Ingrediente"
                          />
                        </div>
                        <div className="w-36 shrink-0 flex items-center gap-1.5">
                          <input
                            type="number"
                            step="0.0001"
                            min="0.0001"
                            value={row.quantityPerBatch}
                            onChange={(e) => updateRecipeRow(idx, 'quantityPerBatch', e.target.value)}
                            placeholder="Qtd./lote"
                            className="w-full bg-bg-inset border border-border rounded-md px-2.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
                          />
                          {(() => {
                            const ingredientProduct = allProducts.find((p) => p.id === row.ingredientProductId);
                            const unitCode = units.find((u) => u.id === ingredientProduct?.unit_of_measure_id)?.code;
                            return unitCode ? <span className="text-[12px] text-text-muted font-mono shrink-0">{unitCode}</span> : null;
                          })()}
                        </div>
                        <button
                          type="button"
                          onClick={() => removeRecipeRow(idx)}
                          aria-label="Remover ingrediente"
                          className="flex items-center justify-center w-9 h-9 rounded-md border border-border text-text-muted hover:text-danger hover:border-danger transition-colors cursor-pointer shrink-0"
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>

                  <button
                    type="button"
                    onClick={addRecipeRow}
                    className="flex items-center justify-center gap-2 border border-dashed border-border hover:border-accent text-text-muted hover:text-accent text-sm font-medium rounded-md py-2.5 transition-colors cursor-pointer"
                  >
                    <Plus size={15} />
                    Adicionar ingrediente
                  </button>

                  {recipeIsEditing && recipeForm.rows.some((r) => r.ingredientProductId && r.quantityPerBatch) && (
                    <div className="bg-bg-inset border border-border rounded-md p-3">
                      <p className="text-[11px] text-text-muted leading-snug">
                        {recipeForm.rows.filter((r) => r.ingredientProductId && r.quantityPerBatch).map((r, i) => {
                          const ing = allProducts.find((p) => p.id === r.ingredientProductId);
                          const unitCode = units.find((u) => u.id === ing?.unit_of_measure_id)?.code || '';
                          const hint = fractionHint(r.quantityPerBatch);
                          return (i > 0 ? ' + ' : '') + (hint || r.quantityPerBatch) + ' ' + unitCode + ' ' + (ing?.name || '?');
                        })}
                        {' \u2192 '}
                        {recipeForm.batchYield || '?'} {units.find((u) => u.id === recipeForm.batchYieldUnitId)?.code || ''} {producibleCandidates.find((p) => p.id === recipeForm.productId)?.name || 'produto'}
                      </p>
                    </div>
                  )}
                </>
              )}

              {recipeError && (
                <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
                  {recipeError}
                </div>
              )}

              <button
                type="button"
                onClick={handleSaveRecipe}
                disabled={recipeSaving || recipeForm.rows.length === 0 || !recipeForm.batchYieldUnitId}
                className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
              >
                {recipeSaving ? <Loader2 size={17} className="animate-spin" /> : <ChefHat size={17} />}
                {recipeSaving ? 'A guardar...' : 'Guardar receita'}
              </button>
        </div>
      </Modal>

      <Modal open={produceModalOpen} onClose={closeProduceModal} title="Produzir">
        <form onSubmit={handleProduceSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Armazém *</label>
            <Select
              value={produceForm.warehouseId}
              onChange={handleProduceWarehouseChange}
              options={warehouses.map((w) => ({ value: w.id, label: w.name }))}
              placeholder="Selecionar armazém"
            />
          </div>

          {produceEstimateLoading && (
            <div className="flex items-center gap-2 text-text-muted text-[12px]">
              <Loader2 size={13} className="animate-spin" />
              A calcular capacidade...
            </div>
          )}

          {produceEstimateError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
              {produceEstimateError}
            </div>
          )}

          {produceEstimate && !produceEstimateLoading && (
            <div className="bg-accent/10 border-l-2 border-accent text-accent px-3.5 py-2.5 text-[13px] rounded-r">
              Com o stock atual de ingredientes neste armazém, pode produzir até <strong>{produceEstimate.max_units}</strong> unidades
            </div>
          )}

          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Número de lotes</label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={produceForm.numBatches}
              onChange={(e) => handleBatchesChange(e.target.value)}
              placeholder={'Ex: 2 (1 lote = ' + (produceForm.batchYield || 1) + ' unidades)'}
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>

          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Quantidade a produzir (unidades) *</label>
            <input
              type="number"
              step="1"
              min="1"
              value={produceForm.quantity}
              onChange={(e) => handleQuantityChange(e.target.value)}
              required
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
            {produceExceedsCapacity && (
              <p className="text-[11px] text-danger mt-1">Excede a capacidade estimada com o stock atual de ingredientes</p>
            )}
          </div>

          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Motivo (opcional)</label>
            <input
              value={produceForm.reason}
              onChange={(e) => setProduceForm((prev) => ({ ...prev, reason: e.target.value }))}
              placeholder="Ex: Produção diária"
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>

          {produceError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
              {produceError}
            </div>
          )}

          <button
            type="submit"
            disabled={produceSaving || !produceForm.quantity || !produceForm.warehouseId || produceExceedsCapacity}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {produceSaving ? <Loader2 size={17} className="animate-spin" /> : <Factory size={17} />}
            {produceSaving ? 'A produzir...' : 'Produzir'}
          </button>
        </form>
      </Modal>
    </main>
  );
}

import { useState, useEffect } from 'react';
import { Package2, Plus, Loader2, Search, AlertTriangle, ArrowDownToLine, SlidersHorizontal, Warehouse, Pencil, Check, X, ArrowRightLeft, Trash2, Power } from 'lucide-react';
import Modal from '../components/Modal';
import MovementForm from '../components/MovementForm';
import Select from '../components/Select';
import { listStockLevels, receiveStock, adjustStock, transferStock, recordStockLoss, listWarehouses, createWarehouse, updateWarehouseFull, toggleWarehouseStatus } from '../api/stock';
import { provincesApi, municipalitiesApi } from '../api/catalogs';
import { listProducts } from '../api/products';
import { extractErrorMessage } from '../utils/errors';
import { useCan } from '../utils/permissions';

const LOSS_CATEGORIES = [
  { value: 'EXPIRACAO', label: 'Expiração' },
  { value: 'QUEBRA', label: 'Quebra' },
  { value: 'ROUBO', label: 'Roubo' },
  { value: 'OUTRO', label: 'Outro' },
];

function formatQty(value) {
  return value % 1 === 0 ? String(value) : String(value).replace('.', ',');
}

function WarehouseCard({ warehouse, isCentral, onEditClick, onToggleStatus, togglingId }) {
  const can = useCan();

  return (
    <div className="bg-bg-elevated border border-border rounded-lg px-5 py-4 flex items-center justify-between gap-4 flex-wrap">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-md bg-accent/10 flex items-center justify-center shrink-0">
          <Warehouse size={17} className="text-accent" />
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-text-muted">Armazem selecionado</p>
          <div className="flex items-center gap-2">
            <p className="font-display font-medium text-text-primary">{warehouse.name}</p>
            {!warehouse.is_active && (
              <span className="text-[10px] font-semibold uppercase tracking-wide text-danger bg-danger/10 px-1.5 py-0.5 rounded">Inativo</span>
            )}
          </div>
          {warehouse.code && <p className="text-[12px] text-text-muted font-mono">{warehouse.code}</p>}
        </div>
      </div>

      {can('warehouses:manage') && !isCentral && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => onEditClick(warehouse)}
            aria-label="Editar armazem"
            className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer"
          >
            <Pencil size={14} />
          </button>
          <button
            onClick={() => onToggleStatus(warehouse.id)}
            disabled={togglingId === warehouse.id}
            aria-label={warehouse.is_active ? 'Desativar armazem' : 'Ativar armazem'}
            title={warehouse.is_active ? 'Desativar' : 'Ativar'}
            className={'flex items-center justify-center w-8 h-8 rounded-md border border-border transition-colors cursor-pointer disabled:opacity-50 ' + (warehouse.is_active ? 'text-danger hover:bg-danger/10' : 'text-success hover:bg-success/10')}
          >
            {togglingId === warehouse.id ? <Loader2 size={14} className="animate-spin" /> : <Power size={14} />}
          </button>
        </div>
      )}
    </div>
  );
}

export default function Stock() {
  const can = useCan();
  const [warehouses, setWarehouses] = useState([]);
  const [selectedWarehouseId, setSelectedWarehouseId] = useState('');
  const [levels, setLevels] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');

  const [newWarehouseModalOpen, setNewWarehouseModalOpen] = useState(false);
  const [editingWarehouseId, setEditingWarehouseId] = useState(null);
  const [newWarehouseName, setNewWarehouseName] = useState('');
  const [newWarehouseCode, setNewWarehouseCode] = useState('');
  const [newWarehouseProvinceId, setNewWarehouseProvinceId] = useState('');
  const [newWarehouseMunicipalityId, setNewWarehouseMunicipalityId] = useState('');
  const [newWarehouseAddress, setNewWarehouseAddress] = useState('');
  const [newWarehouseAllowNegative, setNewWarehouseAllowNegative] = useState(false);
  const [newWarehouseEntradasBloqueadas, setNewWarehouseEntradasBloqueadas] = useState(false);
  const [newWarehouseSaidasBloqueadas, setNewWarehouseSaidasBloqueadas] = useState(false);
  const [newWarehouseGeridoPorFamilia, setNewWarehouseGeridoPorFamilia] = useState(false);
  const [provinces, setProvinces] = useState([]);
  const [municipalities, setMunicipalities] = useState([]);
  const [creatingWarehouse, setCreatingWarehouse] = useState(false);
  const [togglingWarehouseId, setTogglingWarehouseId] = useState(null);
  const [newWarehouseError, setNewWarehouseError] = useState('');

  const [receiveModalOpen, setReceiveModalOpen] = useState(false);
  const [transferModalOpen, setTransferModalOpen] = useState(false);
  const [lossModalOpen, setLossModalOpen] = useState(false);
  const [adjustModalOpen, setAdjustModalOpen] = useState(false);
  const [selectedProductId, setSelectedProductId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [reason, setReason] = useState('');
  const [transferFromWarehouseId, setTransferFromWarehouseId] = useState('');
  const [transferToWarehouseId, setTransferToWarehouseId] = useState('');
  const [lossCategory, setLossCategory] = useState('EXPIRACAO');
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [formSuccess, setFormSuccess] = useState('');

  async function loadWarehouses() {
    try {
      const data = await listWarehouses();
      setWarehouses(data);
      if (data.length > 0 && !selectedWarehouseId) {
        setSelectedWarehouseId(data[0].id);
      }
      return data;
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar armazéns'));
      return [];
    }
  }

  async function loadLevels(warehouseId) {
    if (!warehouseId) return;
    setLoading(true);
    setError('');
    try {
      const [levelsData, productsData] = await Promise.all([listStockLevels(warehouseId), listProducts()]);
      setLevels(levelsData);
      setProducts(productsData.filter((p) => p.is_active && p.product_type === 'BEM'));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar stock'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWarehouses();
    provincesApi.list().then(setProvinces).catch(() => setProvinces([]));
    municipalitiesApi.list().then(setMunicipalities).catch(() => setMunicipalities([]));
  }, []);

  useEffect(() => {
    if (selectedWarehouseId) loadLevels(selectedWarehouseId);
  }, [selectedWarehouseId]);

  const selectedWarehouse = warehouses.find((w) => w.id === selectedWarehouseId);
  const centralWarehouse = warehouses[0]; // first created = central (see stock_service.get_default_warehouse ordering)
  const isCentralSelected = selectedWarehouseId === centralWarehouse?.id;

  const filteredLevels = levels.filter((l) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return l.product_code.toLowerCase().includes(q) || l.product_name.toLowerCase().includes(q);
  });

  function openReceiveModal() {
    setSelectedProductId('');
    setQuantity('');
    setReason('');
    setFormError('');
    setFormSuccess('');
    setReceiveModalOpen(true);
  }

  function openTransferModal() {
    setSelectedProductId('');
    setQuantity('');
    setReason('');
    setTransferFromWarehouseId(selectedWarehouseId || centralWarehouse?.id || '');
    setTransferToWarehouseId('');
    setFormError('');
    setFormSuccess('');
    setTransferModalOpen(true);
  }

  async function handleToggleWarehouseStatus(warehouseId) {
    setTogglingWarehouseId(warehouseId);
    try {
      await toggleWarehouseStatus(warehouseId);
      await loadWarehouses();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado do armazem'));
    } finally {
      setTogglingWarehouseId(null);
    }
  }

  function resetWarehouseForm() {
    setNewWarehouseName('');
    setNewWarehouseCode('');
    setNewWarehouseProvinceId('');
    setNewWarehouseMunicipalityId('');
    setNewWarehouseAddress('');
    setNewWarehouseAllowNegative(false);
    setNewWarehouseEntradasBloqueadas(false);
    setNewWarehouseSaidasBloqueadas(false);
    setNewWarehouseGeridoPorFamilia(false);
    setNewWarehouseError('');
  }

  function openNewWarehouseModal() {
    setEditingWarehouseId(null);
    resetWarehouseForm();
    setNewWarehouseModalOpen(true);
  }

  function openEditWarehouseModal(warehouse) {
    setEditingWarehouseId(warehouse.id);
    setNewWarehouseName(warehouse.name);
    setNewWarehouseCode(warehouse.code || '');
    setNewWarehouseProvinceId(warehouse.province_id || '');
    setNewWarehouseMunicipalityId(warehouse.municipality_id || '');
    setNewWarehouseAddress(warehouse.address || '');
    setNewWarehouseAllowNegative(!!warehouse.allow_negative_stock);
    setNewWarehouseEntradasBloqueadas(!!warehouse.entradas_bloqueadas);
    setNewWarehouseSaidasBloqueadas(!!warehouse.saidas_bloqueadas);
    setNewWarehouseGeridoPorFamilia(!!warehouse.gerido_por_familia_tipo);
    setNewWarehouseError('');
    setNewWarehouseModalOpen(true);
  }

  async function handleCreateWarehouse(e) {
    e.preventDefault();
    setNewWarehouseError('');
    setCreatingWarehouse(true);
    const payload = {
      name: newWarehouseName,
      code: newWarehouseCode || null,
      province_id: newWarehouseProvinceId || null,
      municipality_id: newWarehouseMunicipalityId || null,
      address: newWarehouseAddress || null,
      allow_negative_stock: newWarehouseAllowNegative,
      entradas_bloqueadas: newWarehouseEntradasBloqueadas,
      saidas_bloqueadas: newWarehouseSaidasBloqueadas,
      gerido_por_familia_tipo: newWarehouseGeridoPorFamilia,
    };
    try {
      if (editingWarehouseId) {
        const updated = await updateWarehouseFull(editingWarehouseId, payload);
        setNewWarehouseModalOpen(false);
        await loadWarehouses();
        setSelectedWarehouseId(updated.id);
      } else {
        const created = await createWarehouse(payload);
        setNewWarehouseModalOpen(false);
        await loadWarehouses();
        setSelectedWarehouseId(created.id);
      }
    } catch (err) {
      setNewWarehouseError(extractErrorMessage(err, 'Erro ao guardar armazem'));
    } finally {
      setCreatingWarehouse(false);
    }
  }

  function openLossModal() {
    setSelectedProductId('');
    setQuantity('');
    setReason('');
    setLossCategory('EXPIRACAO');
    setFormError('');
    setFormSuccess('');
    setLossModalOpen(true);
  }

  function openAdjustModal() {
    setSelectedProductId('');
    setQuantity('');
    setReason('');
    setFormError('');
    setFormSuccess('');
    setAdjustModalOpen(true);
  }

  async function handleReceiveSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      await receiveStock(selectedProductId, parseFloat(quantity), reason || null);
      setSelectedProductId('');
      setQuantity('');
      setReason('');
      setFormSuccess('Receção registada com sucesso.');
      await loadLevels(selectedWarehouseId);
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao registar receção'));
    } finally {
      setSaving(false);
    }
  }

  async function handleTransferSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      await transferStock(transferFromWarehouseId, transferToWarehouseId, selectedProductId, parseFloat(quantity), reason || null);
      setSelectedProductId('');
      setQuantity('');
      setReason('');
      setFormSuccess('Transferência registada com sucesso.');
      await loadLevels(selectedWarehouseId);
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao transferir stock'));
    } finally {
      setSaving(false);
    }
  }

  async function handleLossSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      await recordStockLoss(selectedWarehouseId, selectedProductId, parseFloat(quantity), lossCategory, reason || null);
      setSelectedProductId('');
      setQuantity('');
      setReason('');
      setFormSuccess('Perda registada com sucesso.');
      await loadLevels(selectedWarehouseId);
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao registar perda'));
    } finally {
      setSaving(false);
    }
  }

  async function handleAdjustSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      await adjustStock(selectedWarehouseId, selectedProductId, parseFloat(quantity), reason);
      setSelectedProductId('');
      setQuantity('');
      setReason('');
      setFormSuccess('Stock ajustado com sucesso.');
      await loadLevels(selectedWarehouseId);
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao ajustar stock'));
    } finally {
      setSaving(false);
    }
  }

  function handleWarehouseRenamed(updated) {
    setWarehouses((prev) => prev.map((w) => (w.id === updated.id ? updated : w)));
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <Package2 size={22} className="text-accent" />
        Stock
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Níveis de stock por armazém - a receção entra no armazém central é distribuída por transferência interna
      </p>

      <div className="flex items-end justify-between mb-4 flex-wrap gap-3">
        {warehouses.length > 1 ? (
          <div className="max-w-sm w-full sm:w-auto sm:min-w-[260px]">
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Armazém</label>
            <Select
              value={selectedWarehouseId}
              onChange={setSelectedWarehouseId}
              options={warehouses.map((w) => ({ value: w.id, label: w.name }))}
              placeholder="Selecionar armazém"
            />
          </div>
        ) : <div />}

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={openNewWarehouseModal}
            disabled={!can('warehouses:create')}
            className="flex items-center gap-2 border border-border hover:border-accent text-text-primary font-medium text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Plus size={16} />
            Novo Armazem
          </button>
          {warehouses.length > 1 && (
            <button
              onClick={openTransferModal}
              disabled={!can('stock:transfer')}
              className="flex items-center gap-2 border border-border hover:border-accent text-text-primary font-medium text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ArrowRightLeft size={16} />
              Transferir
            </button>
          )}
          <button
            onClick={openLossModal}
            disabled={!can('stock:loss')}
            className="flex items-center gap-2 border border-border hover:border-danger hover:text-danger text-text-primary font-medium text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Trash2 size={16} />
            Registar perda
          </button>
          <button
            onClick={openAdjustModal}
            disabled={!can('stock:adjust')}
            className="flex items-center gap-2 border border-border hover:border-accent text-text-primary font-medium text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <SlidersHorizontal size={16} />
            Ajustar
          </button>
          {isCentralSelected && (
            <button
              onClick={openReceiveModal}
              disabled={!can('stock:receive')}
              className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white font-semibold text-sm px-4 py-2.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ArrowDownToLine size={17} />
              Receção
            </button>
          )}
        </div>
      </div>

      {selectedWarehouse && <div className="mb-5"><WarehouseCard key={selectedWarehouse.id} warehouse={selectedWarehouse} isCentral={selectedWarehouse.id === centralWarehouse?.id} onEditClick={openEditWarehouseModal} onToggleStatus={handleToggleWarehouseStatus} togglingId={togglingWarehouseId} /></div>}

      <div className="relative max-w-sm mb-5">
        <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          type="text"
          placeholder="Pesquisar por código ou nome..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-bg-elevated border border-border rounded-md pl-10 pr-4 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
        />
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

        {!loading && !error && filteredLevels.length === 0 && (
          <div className="text-center py-16 text-text-muted text-sm">
            <span className="flex flex-col items-center gap-3">{search ? 'Nenhum produto encontrado' : 'Nenhum produto com stock registado'}<Search size={22} className="text-text-muted/40 mt-1" /></span>
          </div>
        )}

        {!loading && !error && filteredLevels.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[680px]">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Código</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Produto</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Quantidade</th>
                  <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Limite mínimo</th>
                  <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-6 py-3">Estado</th>
                </tr>
              </thead>
              <tbody>
                {filteredLevels.map((l) => (
                  <tr key={l.product_id} className={'border-b border-border last:border-0 hover:bg-bg-inset/40 transition-colors ' + (l.is_low ? 'bg-danger/5' : '')}>
                    <td className="px-6 py-4 font-mono text-text-muted">{l.product_code}</td>
                    <td className="px-6 py-4 font-display font-medium text-text-primary">{l.product_name}</td>
                    <td className="px-6 py-4 font-mono text-text-primary text-right">{formatQty(l.quantity)}</td>
                    <td className="px-6 py-4 font-mono text-text-muted text-right">{formatQty(l.min_stock_threshold)}</td>
                    <td className="px-6 py-4">
                      {l.is_low ? (
                        <span className="inline-flex items-center gap-1 bg-danger/10 text-danger text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded">
                          <AlertTriangle size={11} />
                          Stock baixo
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 bg-success/10 text-success text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded">
                          OK
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal open={receiveModalOpen} onClose={() => setReceiveModalOpen(false)} title="Registar Receção de Stock" maxWidthClass="max-w-6xl">
        <MovementForm
          filterDirection="ENTRADA"
          defaultWarehouseId={centralWarehouse?.id}
          onSuccess={() => { setReceiveModalOpen(false); loadWarehouses(); if (selectedWarehouseId) loadLevels(selectedWarehouseId); }}
          onCancel={() => setReceiveModalOpen(false)}
        />
      </Modal>

      <Modal open={transferModalOpen} onClose={() => setTransferModalOpen(false)} title="Transferir stock" maxWidthClass="max-w-2xl">
        <form onSubmit={handleTransferSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">De *</label>
              <Select
                value={transferFromWarehouseId}
                onChange={setTransferFromWarehouseId}
                options={warehouses.filter((w) => w.is_active).map((w) => ({ value: w.id, label: w.name }))}
                placeholder="Selecionar origem"
              />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Para *</label>
              <Select
                value={transferToWarehouseId}
                onChange={setTransferToWarehouseId}
                options={warehouses.filter((w) => w.is_active && w.id !== transferFromWarehouseId).map((w) => ({ value: w.id, label: w.name }))}
                placeholder="Selecionar destino"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Produto *</label>
              <Select
                value={selectedProductId}
                onChange={setSelectedProductId}
                options={products.map((p) => ({ value: p.id, label: p.code + ' - ' + p.name }))}
                placeholder="Selecionar produto"
              />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Quantidade *</label>
              <input
                type="number"
                step="0.001"
                min="0.001"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                required
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
              />
            </div>
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Motivo (opcional)</label>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Ex: Reposicao semanal"
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          {formSuccess && (
            <div className="bg-success/10 border-l-2 border-success text-success px-3.5 py-2.5 text-[13px] rounded-r">
              {formSuccess}
            </div>
          )}
          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
              {formError}
            </div>
          )}
          <button
            type="submit"
            disabled={saving || !selectedProductId || !quantity || !transferToWarehouseId || !transferFromWarehouseId}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <ArrowRightLeft size={17} />}
            {saving ? 'A transferir...' : 'Transferir stock'}
          </button>
        </form>
      </Modal>

      <Modal open={lossModalOpen} onClose={() => setLossModalOpen(false)} title={'Registar perda' + (selectedWarehouse ? ' - ' + selectedWarehouse.name : '')}>
        <form onSubmit={handleLossSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Produto *</label>
            <Select
              value={selectedProductId}
              onChange={setSelectedProductId}
              options={products.map((p) => ({ value: p.id, label: p.code + ' - ' + p.name }))}
              placeholder="Selecionar produto"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Categoria *</label>
            <div className="grid grid-cols-2 gap-2">
              {LOSS_CATEGORIES.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => setLossCategory(c.value)}
                  className={
                    'px-3 py-2.5 rounded-md border text-sm font-medium transition-colors cursor-pointer ' +
                    (lossCategory === c.value
                      ? 'bg-danger/10 border-danger text-danger'
                      : 'border-border text-text-muted hover:text-text-primary')
                  }
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Quantidade *</label>
            <input
              type="number"
              step="0.001"
              min="0.001"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Detalhe (opcional)</label>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Ex: Lote 4521, validade 20/08"
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          {formSuccess && (
            <div className="bg-success/10 border-l-2 border-success text-success px-3.5 py-2.5 text-[13px] rounded-r">
              {formSuccess}
            </div>
          )}
          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
              {formError}
            </div>
          )}
          <button
            type="submit"
            disabled={saving || !selectedProductId || !quantity}
            className="mt-1 bg-danger hover:bg-danger/90 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Trash2 size={17} />}
            {saving ? 'A guardar...' : 'Registar perda'}
          </button>
        </form>
      </Modal>

      <Modal open={adjustModalOpen} onClose={() => setAdjustModalOpen(false)} title={'Ajustar stock' + (selectedWarehouse ? ' - ' + selectedWarehouse.name : '')}>
        <form onSubmit={handleAdjustSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Produto *</label>
            <Select
              value={selectedProductId}
              onChange={setSelectedProductId}
              options={products.map((p) => ({ value: p.id, label: p.code + ' - ' + p.name }))}
              placeholder="Selecionar produto"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nova quantidade exata *</label>
            <input
              type="number"
              step="0.001"
              min="0"
              value={quantity}
              onChange={(e) => setQuantity(e.target.value)}
              required
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Motivo *</label>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Ex: Contagem física..."
              required
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
            />
          </div>
          {formSuccess && (
            <div className="bg-success/10 border-l-2 border-success text-success px-3.5 py-2.5 text-[13px] rounded-r">
              {formSuccess}
            </div>
          )}
          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
              {formError}
            </div>
          )}
          <button
            type="submit"
            disabled={saving || !selectedProductId || quantity === '' || reason.trim().length < 5}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <SlidersHorizontal size={17} />}
            {saving ? 'A guardar...' : 'Ajustar stock'}
          </button>
        </form>
      </Modal>

      <Modal open={newWarehouseModalOpen} onClose={() => setNewWarehouseModalOpen(false)} title={editingWarehouseId ? 'Editar Armazem' : 'Novo Armazem'} maxWidthClass="max-w-2xl">
        <form onSubmit={handleCreateWarehouse} className="flex flex-col gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome do armazem *</label>
              <input
                value={newWarehouseName}
                onChange={(e) => setNewWarehouseName(e.target.value)}
                required
                autoFocus
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
              />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Codigo</label>
              <input
                value={newWarehouseCode}
                onChange={(e) => setNewWarehouseCode(e.target.value)}
                className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Provincia</label>
              <Select value={newWarehouseProvinceId} onChange={setNewWarehouseProvinceId} options={provinces.map((p) => ({ value: p.id, label: p.name }))} placeholder="Selecionar" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Municipio</label>
              <Select value={newWarehouseMunicipalityId} onChange={setNewWarehouseMunicipalityId} options={municipalities.filter((m) => !newWarehouseProvinceId || m.province_id === newWarehouseProvinceId).map((m) => ({ value: m.id, label: m.name }))} placeholder="Selecionar" />
            </div>
          </div>

          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Morada</label>
            <input
              value={newWarehouseAddress}
              onChange={(e) => setNewWarehouseAddress(e.target.value)}
              className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={newWarehouseAllowNegative} onChange={(e) => setNewWarehouseAllowNegative(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Permitir quantidades negativas</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={newWarehouseGeridoPorFamilia} onChange={(e) => setNewWarehouseGeridoPorFamilia(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Gerido por Familia/Tipo</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={newWarehouseEntradasBloqueadas} onChange={(e) => setNewWarehouseEntradasBloqueadas(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Entradas bloqueadas</span>
            </label>
            <label className="flex items-center gap-2.5 cursor-pointer select-none">
              <input type="checkbox" checked={newWarehouseSaidasBloqueadas} onChange={(e) => setNewWarehouseSaidasBloqueadas(e.target.checked)} className="w-4 h-4 accent-accent cursor-pointer" />
              <span className="text-sm text-text-primary">Saidas bloqueadas</span>
            </label>
          </div>

          {newWarehouseError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-sm rounded-r">{newWarehouseError}</div>
          )}
          <button
            type="submit"
            disabled={creatingWarehouse || !newWarehouseName.trim()}
            className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
          >
            {creatingWarehouse ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {creatingWarehouse ? 'A guardar...' : (editingWarehouseId ? 'Guardar alteracoes' : 'Criar armazem')}
          </button>
        </form>
      </Modal>
    </main>
  );
}

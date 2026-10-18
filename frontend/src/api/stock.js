// API calls for stock, scoped to the caller's company.
// Multi-warehouse: goods are received into the CENTRAL warehouse, then
// internally transferred between any of the company's warehouses.
import apiClient from './client';

export async function listWarehouses() {
  const res = await apiClient.get('/stock/warehouses');
  return res.data;
}

export async function createWarehouse(payload) {
  const res = await apiClient.post('/stock/warehouses', payload);
  return res.data;
}

export async function updateWarehouseFull(warehouseId, payload) {
  const res = await apiClient.patch('/stock/warehouses/' + warehouseId, payload);
  return res.data;
}

export async function toggleWarehouseStatus(warehouseId) {
  const res = await apiClient.patch('/stock/warehouses/' + warehouseId + '/toggle-status');
  return res.data;
}

export async function listStockLevels(warehouseId) {
  const res = await apiClient.get('/stock/levels', { params: { warehouse_id: warehouseId } });
  return res.data;
}

// Stock > Validades: lots expired or expiring within the company's alert days (every warehouse unless one is given).
export async function listExpiringLots(warehouseId = null) {
  const res = await apiClient.get('/stock/expiring', { params: warehouseId ? { warehouse_id: warehouseId } : {} });
  return res.data;
}

// The lots of a product followed by lot / expiry still holding stock (every warehouse unless one is given).
export async function listProductLots(productId, warehouseId = null) {
  const res = await apiClient.get('/stock/lots', { params: { product_id: productId, ...(warehouseId ? { warehouse_id: warehouseId } : {}) } });
  return res.data;
}

export async function listStockMovements(filters = {}) {
  const params = {};
  if (filters.warehouseId) params.warehouse_id = filters.warehouseId;
  if (filters.year) params.year = filters.year;
  if (filters.month) params.month = filters.month;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  params.limit = filters.limit || 50;
  params.offset = filters.offset || 0;
  const res = await apiClient.get('/stock/movements', { params });
  return res.data;
}

export async function getMovementPeriods() {
  const res = await apiClient.get('/stock/movements/available-periods');
  return res.data;
}

export async function transferStock(fromWarehouseId, toWarehouseId, productId, quantity, reason, fiscalPeriodId = null, saleUnitId = null, lotId = null) {
  const res = await apiClient.post('/stock/transfer', {
    lot_id: lotId || null,  // a product followed by lot: the lot moved (empty = FEFO)
    sale_unit_id: saleUnitId || null,
    fiscal_period_id: fiscalPeriodId || null,
    from_warehouse_id: fromWarehouseId,
    to_warehouse_id: toWarehouseId,
    product_id: productId,
    quantity,
    reason: reason || null,
  });
  return res.data;
}

export async function recordStockLoss(warehouseId, productId, quantity, lossCategory, reason, fiscalPeriodId = null, saleUnitId = null, lotId = null) {
  const res = await apiClient.post('/stock/loss', {
    lot_id: lotId || null,  // a product followed by lot: the lot lost (empty = FEFO, the expired first)
    sale_unit_id: saleUnitId || null,
    fiscal_period_id: fiscalPeriodId || null,
    warehouse_id: warehouseId,
    product_id: productId,
    quantity,
    loss_category: lossCategory,
    reason: reason || null,
  });
  return res.data;
}

export async function adjustStock(warehouseId, productId, newQuantity, reason, fiscalPeriodId = null, saleUnitId = null, lot = {}) {
  const res = await apiClient.post('/stock/adjust', {
    // a product followed by lot: a decrease takes lot_id (empty = FEFO), an increase fills lot_number / expiry_date
    lot_id: lot.lotId || null, lot_number: lot.lotNumber || null, expiry_date: lot.expiryDate || null,
    sale_unit_id: saleUnitId || null,
    fiscal_period_id: fiscalPeriodId || null,
    warehouse_id: warehouseId,
    product_id: productId,
    new_quantity: newQuantity,
    reason,
  });
  return res.data;
}

export async function renameWarehouse(warehouseId, name) {
  const res = await apiClient.patch('/stock/warehouses/' + warehouseId, { name });
  return res.data;
}


export async function getProductionEstimate(warehouseId, productId) {
  const res = await apiClient.get('/stock/production-estimate', { params: { warehouse_id: warehouseId, product_id: productId } });
  return res.data;
}

export async function produceStock(warehouseId, finishedProductId, quantityToProduce, reason, fiscalPeriodId = null, saleUnitId = null, lot = {}) {
  const res = await apiClient.post('/stock/produce', {
    fiscal_period_id: fiscalPeriodId || null,
    warehouse_id: warehouseId,
    finished_product_id: finishedProductId,
    quantity_to_produce: quantityToProduce, sale_unit_id: saleUnitId,
    reason: reason || null,
    lot_number: lot.lotNumber || null, expiry_date: lot.expiryDate || null,  // a product followed by lot / expiry
  });
  return res.data;
}

export async function getProductionHistory(filters = {}) {
  const params = {};
  if (filters.year) params.year = filters.year;
  if (filters.month) params.month = filters.month;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  const res = await apiClient.get('/stock/production-history', { params });
  return res.data;
}

// ---------- Inventário (count a warehouse, validate the differences into adjustments) ----------

export async function listInventories(warehouseId) {
  const res = await apiClient.get('/stock/inventories', { params: warehouseId ? { warehouse_id: warehouseId } : {} });
  return res.data;
}

export async function createInventory(warehouseId, fiscalPeriodId = null, description = null) {
  const res = await apiClient.post('/stock/inventories', { warehouse_id: warehouseId, fiscal_period_id: fiscalPeriodId || null, description });
  return res.data;
}

export async function getInventory(inventoryId) {
  const res = await apiClient.get('/stock/inventories/' + inventoryId);
  return res.data;
}

// counts: [{ product_id, counted_quantity (base unit, null = not counted), count_detail }]
export async function saveInventoryCounts(inventoryId, counts) {
  const res = await apiClient.put('/stock/inventories/' + inventoryId + '/counts', { counts });
  return res.data;
}

export async function validateInventory(inventoryId) {
  const res = await apiClient.post('/stock/inventories/' + inventoryId + '/validate');
  return res.data;
}

export async function fetchInventoryPdfBlob(inventoryId) {
  const res = await apiClient.get('/stock/inventories/' + inventoryId + '/pdf', { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

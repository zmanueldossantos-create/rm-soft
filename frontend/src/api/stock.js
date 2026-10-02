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

export async function transferStock(fromWarehouseId, toWarehouseId, productId, quantity, reason, fiscalPeriodId = null, saleUnitId = null) {
  const res = await apiClient.post('/stock/transfer', {
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

export async function recordStockLoss(warehouseId, productId, quantity, lossCategory, reason, fiscalPeriodId = null, saleUnitId = null) {
  const res = await apiClient.post('/stock/loss', {
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

export async function adjustStock(warehouseId, productId, newQuantity, reason, fiscalPeriodId = null, saleUnitId = null) {
  const res = await apiClient.post('/stock/adjust', {
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

export async function produceStock(warehouseId, finishedProductId, quantityToProduce, reason, fiscalPeriodId = null) {
  const res = await apiClient.post('/stock/produce', {
    fiscal_period_id: fiscalPeriodId || null,
    warehouse_id: warehouseId,
    finished_product_id: finishedProductId,
    quantity_to_produce: quantityToProduce,
    reason: reason || null,
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

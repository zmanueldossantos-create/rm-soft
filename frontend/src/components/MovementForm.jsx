import { useState, useEffect, useMemo, useRef } from 'react';
import { Plus, Loader2, Trash2, Upload, Download } from 'lucide-react';
import Select from './Select';
import * as XLSX from 'xlsx';
import { createMovementDocument, downloadMovementExcelTemplate } from '../api/movements';
import { listProducts } from '../api/products';
import { listWarehouses } from '../api/stock';
import { movementTypesApi, unitsApi } from '../api/catalogs';
import { listSuppliers } from '../api/suppliers';
import { extractErrorMessage } from '../utils/errors';

const inputClass = "w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors";

function formatMoney(v) {
  return Number(v || 0).toLocaleString('pt-AO', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' Kz';
}

// Reusable stock movement form, always used within a specific contextual action
// ("Registar Recepcao", "Registar Perda", ...) - filterDirection is required and the
// underlying Tipo de Movimento (Manual vs Automatico) is resolved automatically: filling
// the table manually uses the Manual variant, importing an Excel file uses the Automatico
// variant, so the user never has to think about "type" as a separate concept.
// The warehouse is always chosen explicitly: a reception in the wrong one would silently distort the stock.
export default function MovementForm({ onSuccess, onCancel, filterDirection }) {
  const [loaded, setLoaded] = useState(false);
  const [products, setProducts] = useState([]);
  const [movementTypes, setMovementTypes] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [units, setUnits] = useState([]);

  const [warehouseId, setWarehouseId] = useState('');
  const [movementDate, setMovementDate] = useState(new Date().toISOString().slice(0, 10));
  const [description, setDescription] = useState('');
  const [suppliers, setSuppliers] = useState([]);
  const [supplierId, setSupplierId] = useState('');
  const [lines, setLines] = useState([{ product_id: '', sale_unit_id: '', quantity: '1', purchase_price: '0', sale_price: '0' }]);
  const [scanCode, setScanCode] = useState('');
  const [scanError, setScanError] = useState('');
  const [usedExcelImport, setUsedExcelImport] = useState(false);
  const [excelFileName, setExcelFileName] = useState('');
  const [excelError, setExcelError] = useState('');
  const excelInputRef = useRef(null);

  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    async function loadData() {
      try {
        const [productsData, typesData, warehousesData, unitsData, suppliersData] = await Promise.all([
          listProducts(),
          movementTypesApi.list(),
          listWarehouses(),
          unitsApi.list(),
          filterDirection === 'ENTRADA' ? listSuppliers() : Promise.resolve([]),
        ]);
        setProducts(productsData.filter((p) => p.is_active));
        setMovementTypes(typesData.filter((t) => t.is_active && t.direction === filterDirection));
        setWarehouses(warehousesData.filter((w) => w.is_active));
        setUnits(unitsData);
        setSuppliers(suppliersData.filter((s) => s.is_active));
      } catch (err) {
        setFormError(extractErrorMessage(err, 'Erro ao carregar dados'));
      } finally {
        setLoaded(true);
      }
    }
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const productById = useMemo(() => {
    const map = {};
    products.forEach((p) => { map[p.id] = p; });
    return map;
  }, [products]);

  // Resolved automatically: Excel import -> the "Automatico" variant, manual table -> "Manual".
  const resolvedMovementType = movementTypes.find((t) => t.is_auto === usedExcelImport);
  const isEntrada = filterDirection === 'ENTRADA';

  const totals = useMemo(() => {
    let totalQuantity = 0;
    let totalValue = 0;
    for (const line of lines) {
      const qty = parseFloat(line.quantity) || 0;
      const price = isEntrada ? (parseFloat(line.purchase_price) || 0) : (parseFloat(line.sale_price) || 0);
      totalQuantity += qty;
      totalValue += qty * price;
    }
    return { totalQuantity, totalValue };
  }, [lines, isEntrada]);

  function updateLine(index, field, value) {
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, [field]: value } : l)));
  }

  // THE article lookup of this form (scan and Excel import alike): a product's barcode or internal code (base unit),
  // or the barcode of one of its sale units - then factor base units (a box of 30 eggs = 30).
  function lookupArticle(code) {
    const c = String(code || '').trim().toLowerCase();
    if (!c) return null;
    for (const p of products) {
      if ((p.barcode || '').toLowerCase() === c || (p.code || '').toLowerCase() === c) return { product: p, saleUnit: null, factor: 1 };
      const saleUnit = (p.sale_units || []).find((u) => (u.barcode || '').toLowerCase() === c);
      if (saleUnit) return { product: p, saleUnit, factor: Number(saleUnit.factor) };
    }
    return null;
  }

  // Barcode scan (field + Enter): adds the article in the unit scanned (a bag's barcode = a line in SC), or raises by 1 the
  // quantity of its existing line in that unit. Enter never submits.
  function handleScan() {
    const found = lookupArticle(scanCode);
    if (!found) {
      setScanError('Codigo nao encontrado: ' + scanCode);
      return;
    }
    const { product, saleUnit } = found;
    const unitId = saleUnit ? saleUnit.id : '';
    setLines((prev) => {
      const index = prev.findIndex((l) => l.product_id === product.id && (l.sale_unit_id || '') === unitId);
      if (index >= 0) {
        return prev.map((l, i) => (i === index ? { ...l, quantity: String((parseFloat(l.quantity) || 0) + 1) } : l));
      }
      const fresh = { product_id: product.id, sale_unit_id: unitId, quantity: '1', ...unitPrices(product, saleUnit) };
      const emptyIndex = prev.findIndex((l) => !l.product_id);
      return emptyIndex >= 0 ? prev.map((l, i) => (i === emptyIndex ? fresh : l)) : [...prev, fresh];
    });
    setScanCode('');
    setScanError('');
  }

  // Default prices of a line in a unit: the product's purchase price x factor, and the unit's own sale price.
  function unitPrices(product, saleUnit) {
    const factor = saleUnit ? Number(saleUnit.factor) : 1;
    return {
      purchase_price: String(Math.round(Number(product.purchase_price || 0) * factor * 100) / 100),
      sale_price: String(saleUnit ? saleUnit.price : (product.price ?? 0)),
    };
  }

  function changeLineUnit(index, value) {
    setLines((prev) => prev.map((l, i) => {
      if (i !== index) return l;
      const product = productById[l.product_id];
      const saleUnit = (product?.sale_units || []).find((u) => u.id === value) || null;
      return { ...l, sale_unit_id: saleUnit ? saleUnit.id : '', ...(product ? unitPrices(product, saleUnit) : {}) };
    }));
  }

  function addLine() {
    setLines((prev) => [...prev, { product_id: '', sale_unit_id: '', quantity: '1', purchase_price: '0', sale_price: '0' }]);
  }

  function removeLine(index) {
    setLines((prev) => prev.filter((_, i) => i !== index));
  }

  const isFormValid = warehouseId && resolvedMovementType && lines.length > 0 &&
    lines.every((l) => l.product_id && parseFloat(l.quantity) > 0);

  function handleExcelFileChange(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setExcelFileName(file.name);
    setExcelError('');
    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const wb = XLSX.read(evt.target.result, { type: 'array' });
        const ws = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: null });
        const parsedLines = [];
        const notFound = [];
        for (const row of rows.slice(1)) {
          if (!row || row.every((v) => v === null || v === '')) continue;
          const code = String(row[0] ?? '').trim();
          if (!code) continue;
          const found = lookupArticle(code);
          const product = found?.product;
          if (!product) {
            notFound.push(code);
            continue;
          }
          const unitCode = String(row[4] ?? '').trim().toUpperCase();
          const isBase = !unitCode || unitCode === (product.unit_of_measure_code || '').toUpperCase();
          const unitByCode = isBase ? null : (product.sale_units || []).find((u) => (u.unit_of_measure_code || '').toUpperCase() === unitCode);
          if (!isBase && !unitByCode) {
            notFound.push(code + ' (unidade ' + unitCode + ')');
            continue;
          }
          const lineUnit = unitByCode || (isBase && unitCode ? null : found.saleUnit);
          parsedLines.push({
            product_id: product.id,
            sale_unit_id: lineUnit ? lineUnit.id : '',
            quantity: String(row[1] ?? '1'),
            purchase_price: String(row[2] ?? '0'),
            sale_price: String(row[3] ?? '0'),
          });
        }
        if (parsedLines.length === 0) {
          setExcelError(
            notFound.length > 0
              ? 'Nenhum codigo encontrado: ' + notFound.join(', ') + '. Verifique se os codigos existem nos seus produtos.'
              : 'Nenhuma linha valida encontrada no ficheiro.'
          );
          return;
        }
        setLines(parsedLines);
        setUsedExcelImport(true);
        if (notFound.length > 0) {
          setExcelError('Codigos nao encontrados (ignorados): ' + notFound.join(', '));
        }
      } catch {
        setExcelError('Nao foi possivel ler o ficheiro Excel.');
      }
    };
    reader.readAsArrayBuffer(file);
  }

  function handleManualLineEdit(index, field, value) {
    if (field === 'product_id') setLines((prev) => prev.map((l, i) => (i === index ? { ...l, sale_unit_id: '' } : l)));
    setUsedExcelImport(false);
    updateLine(index, field, value);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    if (!resolvedMovementType) {
      setFormError('Nenhum tipo de movimento configurado para esta operacao - contacte o administrador.');
      return;
    }
    setSaving(true);
    try {
      await createMovementDocument({
        movement_type_id: resolvedMovementType.id,
        warehouse_id: warehouseId,
        movement_date: movementDate,
        description: description || null,
        supplier_id: filterDirection === 'ENTRADA' ? (supplierId || null) : null,
        lines: lines.map((l) => ({
          product_id: l.product_id,
          sale_unit_id: l.sale_unit_id || null,
          quantity: parseFloat(l.quantity),
          purchase_price: parseFloat(l.purchase_price) || 0,
          sale_price: parseFloat(l.sale_price) || 0,
        })),
      });
      onSuccess?.();
    } catch (err) {
      setFormError(extractErrorMessage(err, 'Erro ao criar movimento'));
    } finally {
      setSaving(false);
    }
  }

  if (!loaded) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 size={24} className="animate-spin text-accent" />
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <div className="grid grid-cols-1 sm:grid-cols-12 gap-4">
        <div className="sm:col-span-5">
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Armazém *</label>
          <Select
            value={warehouseId}
            onChange={setWarehouseId}
            options={warehouses.filter((w) => w.is_active).map((w) => ({ value: w.id, label: w.name }))}
            placeholder="Selecionar"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data do movimento *</label>
          <input type="date" value={movementDate} onChange={(e) => setMovementDate(e.target.value)} required className={inputClass} />
        </div>
        {filterDirection === 'ENTRADA' && (
          <div className="sm:col-span-2">
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Fornecedor (opcional)</label>
            <Select
              value={supplierId}
              onChange={setSupplierId}
              options={suppliers.map((s) => ({ value: s.id, label: s.name }))}
              placeholder="Nenhum"
            />
          </div>
        )}
        <div className={filterDirection === 'ENTRADA' ? 'sm:col-span-3' : 'sm:col-span-5'}>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Descrição</label>
          <input value={description} onChange={(e) => setDescription(e.target.value)} className={inputClass} />
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 bg-bg-inset/40 border border-border rounded-md p-3.5">
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Qtd Total</label>
          <p className="font-mono text-sm text-text-primary">{totals.totalQuantity.toFixed(2)}</p>
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1 block">Valor Total</label>
          <p className="font-mono text-sm text-text-primary">{formatMoney(totals.totalValue)}</p>
        </div>
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <input ref={excelInputRef} type="file" accept=".xlsx,.xls" onChange={handleExcelFileChange} className="hidden" />
        <input value={scanCode} onChange={(e) => { setScanCode(e.target.value); setScanError(''); }} onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleScan(); } }} autoFocus placeholder="Ler codigo de barras" className="flex-1 min-w-[180px] bg-bg-inset border border-border rounded-md px-3 py-2 text-[13px] text-text-primary font-mono outline-none focus:border-accent" />
<button type="button" onClick={() => excelInputRef.current?.click()} title="Importar ficheiro Excel" className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[13px] px-3 py-2 rounded-md transition-colors cursor-pointer">
          <Upload size={15} /> Importar Excel
        </button>
        <button type="button" onClick={downloadMovementExcelTemplate} title="Baixar modelo Excel" className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[13px] px-3 py-2 rounded-md transition-colors cursor-pointer">
          <Download size={15} /> Modelo
        </button>
<button type="button" onClick={() => { setUsedExcelImport(false); addLine(); }} className="flex items-center gap-1.5 border border-dashed border-accent/60 hover:border-accent hover:bg-accent/5 text-accent text-[13px] font-medium rounded-md px-3.5 py-2 transition-colors cursor-pointer"><Plus size={15} /> Linha</button>
        {excelFileName && usedExcelImport && <span className="text-[12px] text-text-muted">{excelFileName}</span>}
        {scanError && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2 text-[12px] rounded-r">{scanError}</div>}
{excelError && <span className="text-[12px] text-danger">{excelError}</span>}
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm table-fixed">
          <thead>
            <tr className="border-b border-border bg-bg-inset/40">
              <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2">Produto</th>
              <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2 w-28">Un.</th>
              <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2 w-28">Qtd</th>
              <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2 w-36">Preço Compra</th>
              <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2 w-36">Preço Venda</th>
              <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2 w-32">Total</th>
              <th className="px-2 py-2 w-10"></th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line, idx) => {
              const product = productById[line.product_id];
              const qty = parseFloat(line.quantity) || 0;
              const price = isEntrada ? (parseFloat(line.purchase_price) || 0) : (parseFloat(line.sale_price) || 0);
              const lineTotal = qty * price;
              return (
                <tr key={idx} className="border-b border-border last:border-0">
                  <td className="px-4 py-2.5">
                    <Select
                      value={line.product_id}
                      onChange={(v) => handleManualLineEdit(idx, 'product_id', v)}
                      options={products.map((p) => ({ value: p.id, label: p.code + ' - ' + p.name }))}
                      placeholder="Selecionar produto"
                    />
                  </td>
                  <td className="px-4 py-2.5 w-28 text-right font-mono text-text-muted text-[13px]">
                    {(product?.sale_units || []).length > 0 ? (
  <Select compact value={line.sale_unit_id || 'base'} onChange={(v) => changeLineUnit(idx, v === 'base' ? '' : v)} options={[{ value: 'base', label: product.unit_of_measure_code || 'Base' }, ...product.sale_units.map((u) => ({ value: u.id, label: u.unit_of_measure_code }))]} />
) : (units.find((u) => u.id === product?.unit_of_measure_id)?.code || '-')}
                  </td>
                  <td className="px-4 py-2.5 w-28">
                    <input type="number" step={((product?.sale_units || []).find((u) => u.id === line.sale_unit_id)?.is_fractional ?? (!line.sale_unit_id && product?.unit_is_fractional)) ? '0.001' : '1'} min="0" value={line.quantity} onChange={(e) => handleManualLineEdit(idx, 'quantity', e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors text-right" />{(() => { const su = (product?.sale_units || []).find((u) => u.id === line.sale_unit_id); return su && qty > 0 ? <p className="text-[10.5px] text-text-muted mt-0.5 text-right">= {Math.round(qty * Number(su.factor) * 1000) / 1000} {product.unit_of_measure_code}</p> : null; })()}
                  </td>
                  <td className="px-4 py-2.5 w-36">
                    <input type="number" step="0.01" min="0" value={line.purchase_price} onChange={(e) => handleManualLineEdit(idx, 'purchase_price', e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors text-right" />
                  </td>
                  <td className="px-4 py-2.5 w-36">
                    <input type="number" step="0.01" min="0" value={line.sale_price} onChange={(e) => handleManualLineEdit(idx, 'sale_price', e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors text-right" />
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-text-primary">{formatMoney(lineTotal)}</td>
                  <td className="px-2 py-2.5 text-center">
                    <button type="button" onClick={() => removeLine(idx)} disabled={lines.length === 1} className="text-text-muted hover:text-danger disabled:opacity-30 disabled:cursor-not-allowed transition-colors cursor-pointer">
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {formError && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-sm rounded-r">{formError}</div>
      )}

      <div className="flex justify-end gap-3">
        <button type="button" onClick={onCancel} className="border border-border hover:border-accent text-text-primary text-sm px-5 py-3 rounded-md transition-colors cursor-pointer">
          Cancelar
        </button>
        <button type="submit" disabled={saving || !isFormValid} className="bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-md px-6 py-3 flex items-center gap-2 transition-colors cursor-pointer">
          {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
          {saving ? 'A criar...' : 'Criar Movimento'}
        </button>
      </div>
    </form>
  );
}

import { useState, useEffect, useMemo, useRef } from 'react';
import { Plus, Loader2, Trash2, Upload, Download } from 'lucide-react';
import Select from './Select';
import * as XLSX from 'xlsx';
import { createMovementDocument, downloadMovementExcelTemplate } from '../api/movements';
import { listProducts } from '../api/products';
import { listWarehouses } from '../api/stock';
import { movementTypesApi, unitsApi } from '../api/catalogs';
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
export default function MovementForm({ onSuccess, onCancel, filterDirection, defaultWarehouseId = null }) {
  const [loaded, setLoaded] = useState(false);
  const [products, setProducts] = useState([]);
  const [movementTypes, setMovementTypes] = useState([]);
  const [warehouses, setWarehouses] = useState([]);
  const [units, setUnits] = useState([]);

  const [warehouseId, setWarehouseId] = useState(defaultWarehouseId || '');
  const [movementDate, setMovementDate] = useState(new Date().toISOString().slice(0, 10));
  const [description, setDescription] = useState('');
  const [lines, setLines] = useState([{ product_id: '', quantity: '1', purchase_price: '0', sale_price: '0' }]);
  const [usedExcelImport, setUsedExcelImport] = useState(false);
  const [excelFileName, setExcelFileName] = useState('');
  const [excelError, setExcelError] = useState('');
  const excelInputRef = useRef(null);

  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  useEffect(() => {
    async function loadData() {
      try {
        const [productsData, typesData, warehousesData, unitsData] = await Promise.all([
          listProducts(),
          movementTypesApi.list(),
          listWarehouses(),
          unitsApi.list(),
        ]);
        setProducts(productsData.filter((p) => p.is_active));
        setMovementTypes(typesData.filter((t) => t.is_active && t.direction === filterDirection));
        setWarehouses(warehousesData.filter((w) => w.is_active));
        setUnits(unitsData);
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

  function addLine() {
    setLines((prev) => [...prev, { product_id: '', quantity: '1', purchase_price: '0', sale_price: '0' }]);
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
          const product = products.find((p) => p.code?.toLowerCase() === code.toLowerCase());
          if (!product) {
            notFound.push(code);
            continue;
          }
          parsedLines.push({
            product_id: product.id,
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
        lines: lines.map((l) => ({
          product_id: l.product_id,
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
        <div className="sm:col-span-5">
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
        <button type="button" onClick={() => excelInputRef.current?.click()} title="Importar ficheiro Excel" className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[13px] px-3 py-2 rounded-md transition-colors cursor-pointer">
          <Upload size={15} /> Importar Excel
        </button>
        <button type="button" onClick={downloadMovementExcelTemplate} title="Baixar modelo Excel" className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[13px] px-3 py-2 rounded-md transition-colors cursor-pointer">
          <Download size={15} /> Modelo
        </button>
        {excelFileName && usedExcelImport && <span className="text-[12px] text-text-muted">{excelFileName}</span>}
        {excelError && <span className="text-[12px] text-danger">{excelError}</span>}
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm table-fixed">
          <thead>
            <tr className="border-b border-border bg-bg-inset/40">
              <th className="text-left text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2">Produto</th>
              <th className="text-right text-[11px] uppercase tracking-wide text-text-muted font-medium px-4 py-2 w-16">Un.</th>
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
                  <td className="px-4 py-2.5 w-16 text-right font-mono text-text-muted text-[13px]">
                    {units.find((u) => u.id === product?.unit_of_measure_id)?.code || '-'}
                  </td>
                  <td className="px-4 py-2.5 w-28">
                    <input type="number" step="0.001" min="0" value={line.quantity} onChange={(e) => handleManualLineEdit(idx, 'quantity', e.target.value)} className="w-full bg-bg-inset border border-border rounded-md px-2.5 py-1.5 text-sm text-text-primary font-mono outline-none focus:border-accent transition-colors text-right" />
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
        <button type="button" onClick={() => { setUsedExcelImport(false); addLine(); }} className="w-full flex items-center justify-center gap-1.5 text-accent hover:text-accent-hover text-sm font-medium py-2.5 border-t border-border transition-colors cursor-pointer">
          <Plus size={15} /> Adicionar linha
        </button>
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

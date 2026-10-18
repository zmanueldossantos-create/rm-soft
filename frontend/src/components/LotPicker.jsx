import { useEffect, useState } from 'react';
import Select from './Select';
import { listProductLots } from '../api/stock';

// A product followed by lot / expiry: is it, and what must an entry give (number and/or date)?
export function lotRuleOf(product) {
  if (!product || product.managed_by_stock === false || !(product.managed_by_batch || product.managed_by_expiry)) return null;
  return { batch: !!product.managed_by_batch, expiry: !!product.managed_by_expiry };
}

const day = (iso) => new Date(iso + 'T00:00:00').toLocaleDateString('pt-PT');
const qty = (v) => Number(v || 0).toLocaleString('pt-PT', { maximumFractionDigits: 3 });

// The lot a manual exit takes (loss, transfer, adjustment down, exit document): empty = automatic, the first to expire
// (FEFO). The lots listed are the product's in that warehouse still holding stock - an expired one may be chosen here
// (to write it off, or to move it aside), never by the automatic choice of a sale.
export default function LotPicker({ productId, warehouseId, value, onChange, unitCode = '', compact = false }) {
  const [lots, setLots] = useState(null); // null while loading: a lot given beforehand (Validades) is kept meanwhile

  useEffect(() => {
    setLots(null);
    if (!productId || !warehouseId) { setLots([]); return; }
    let alive = true;
    listProductLots(productId, warehouseId).then((d) => { if (alive) setLots(d); }).catch(() => { if (alive) setLots([]); });
    return () => { alive = false; };
  }, [productId, warehouseId]);

  // once loaded, a lot chosen that is not listed (another warehouse chosen) falls back to automatic
  useEffect(() => {
    if (lots !== null && value && !lots.some((l) => l.id === value)) onChange('');
  }, [lots]); // eslint-disable-line react-hooks/exhaustive-deps

  const options = [
    { value: '', label: 'Automático (primeiro a expirar)' },
    ...(lots || []).map((l) => ({
      value: l.id,
      label: (l.lot_number || 'Sem número') + (l.expiry_date ? ' · val. ' + day(l.expiry_date) : '') + ' · ' + qty(l.quantity) + (unitCode ? ' ' + unitCode : '') + (l.expired ? ' · EXPIRADO' : ''),
    })),
  ];
  return <Select compact={compact} value={value || ''} onChange={onChange} options={options} />;
}

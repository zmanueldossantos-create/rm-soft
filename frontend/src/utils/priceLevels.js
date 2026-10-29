// Preço 1 / 2 / 3: a product, or one of its sale units, may carry two more prices the seller chooses from
// (permission invoices:price_levels). The server always reads the price itself - the screens only send the level.
import { formatKz } from './format';

export const PRICE_LEVEL_PERMISSION = 'invoices:price_levels';

// The price of a level on a product / sale unit, or null when that level is not set (Preço 1 is always set).
export function priceOf(source, level) {
  if (!source) return null;
  const value = level === 2 ? source.price_2 : level === 3 ? source.price_3 : source.price;
  return value === null || value === undefined || value === '' ? null : Number(value);
}

// The levels this product / unit offers - more than one: there is a choice to make.
export function levelsOf(source) {
  return [1, 2, 3].filter((level) => priceOf(source, level) !== null);
}

// The selector's options: «Preço 2 · 1 350,00» - the seller sees what each price is worth.
export function levelOptions(source) {
  return levelsOf(source).map((level) => ({ value: String(level), label: 'Preço ' + level + ' · ' + formatKz(priceOf(source, level)) }));
}

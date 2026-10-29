// Preço 1 / 2 / 3 and the free price: a product, or one of its sale units, may carry two more prices; a till may let
// its cashier choose them, or type a free price (set by the gestor on the till, like the billetage - the gestor always
// may). The server always reads / checks the price itself - the screens send the level, or the free price.
import { formatKz } from './format';

export const FREE = 'free';  // the selector's value for «Preço livre»

// The price of a level on a product / sale unit, or null when that level is not set (Preço 1 is always set).
export function priceOf(source, level) {
  if (!source) return null;
  const value = level === 2 ? source.price_2 : level === 3 ? source.price_3 : source.price;
  return value === null || value === undefined || value === '' ? null : Number(value);
}

// The levels this product / unit offers.
export function levelsOf(source) {
  return [1, 2, 3].filter((level) => priceOf(source, level) !== null);
}

// The selector's options: «Preço 2 · 1 350,00» - the seller sees what each price is worth; levels: whether Preço 2 / 3
// may be chosen, free: whether «Preço livre» may.
export function levelOptions(source, { levels = true, free = false } = {}) {
  const options = (levels ? levelsOf(source) : [1]).map((level) => ({ value: String(level), label: 'Preço ' + level + ' · ' + formatKz(priceOf(source, level)) }));
  return free ? [...options, { value: FREE, label: 'Preço livre' }] : options;
}

// Whether a line has a price choice to show at all.
export function hasPriceChoice(source, { levels = true, free = false } = {}) {
  return !!source && (free || (levels && levelsOf(source).length > 1));
}

// The cost of one unit sold (the average cost, else the purchase price, times what the unit holds) - a free price
// under it needs the seller's confirmation; null: the cost is not known.
export function unitCost(product, factor = 1) {
  const cost = product?.average_cost ?? product?.purchase_price;
  return cost === null || cost === undefined ? null : Math.round(Number(cost) * Number(factor || 1) * 100) / 100;
}

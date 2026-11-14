// The rates in the order a price list reads: by duration (1 hora, 2 horas, 3 horas), then those with hours of their
// own (Pernoite), then the night at the type's hours (Diária); the same order everywhere a rate is listed.
export const rateOrder = (s) => (s.duration_minutes ? s.duration_minutes : s.stay_start_time ? 100000 : 200000);

export const byRateOrder = (a, b) => rateOrder(a) - rateOrder(b) || a.name.localeCompare(b.name, 'pt');

import { useState, useEffect } from 'react';
import DateInput from '../components/DateInput';
import { CalendarClock, Plus, Loader2, X, CheckCircle2, Pencil, ChevronLeft, ChevronRight, DoorOpen, Banknote } from 'lucide-react';
import { useCan } from '../utils/permissions';
import { listActivities } from '../api/activity';
import { listResources, listBookings, createBooking, updateBookingStatus, rescheduleBooking, chargeBooking } from '../api/booking';
import { listPointsOfSale } from '../api/activity';
import { listResourceTypes } from '../api/booking';
import { listCustomers, createCustomer } from '../api/customers';
import { checkIn, checkOut, extendStay, walkIn } from '../api/hotel';
import { listResourceStatuses } from '../api/booking';
import { listPaymentMethodPreferences } from '../api/tesouraria';
import { listVatRates } from '../api/vat';
import { withholdingTaxesApi } from '../api/catalogs';
import { withholdingOf } from '../utils/withholding';
import { guessLegalPersonType, LEGAL_PERSON_OPTIONS } from '../utils/customerType';
import { formatKz } from '../utils/format';
import { listServices } from '../api/services';
import { extractErrorMessage } from '../utils/errors';
import Modal from '../components/Modal';
import Select from '../components/Select';

const STATUS_LABELS = {
  PENDENTE: 'Pendente',
  CONFIRMADA: 'Confirmada',
  EM_CURSO: 'Em curso',
  CONCLUIDA: 'Concluida',
  CANCELADA: 'Cancelada',
  NO_SHOW: 'Nao compareceu',
};

const STATUS_COLORS = {
  PENDENTE: 'text-accent bg-accent/10',
  CONFIRMADA: 'text-success bg-success/10',
  EM_CURSO: 'text-accent bg-accent/10',
  CONCLUIDA: 'text-text-muted bg-bg-inset',
  CANCELADA: 'text-danger bg-danger/10',
  NO_SHOW: 'text-danger bg-danger/10',
};

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

const HOUR_PX = 48;
const AGENDA_DEFAULT_START = 8;
const AGENDA_DEFAULT_END = 20;
const AGENDA_STATUS_STYLE = {
  PENDENTE: 'bg-accent/15 border-accent text-accent',
  CONFIRMADA: 'bg-success/15 border-success text-success',
  EM_CURSO: 'bg-accent/25 border-accent text-accent',
  CONCLUIDA: 'bg-bg-inset border-border text-text-muted',
};
const WEEKDAYS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sab', 'Dom'];

function pad2(n) {
  return String(n).padStart(2, '0');
}

// Date arithmetic on plain YYYY-MM-DD strings, done in UTC so the browser timezone
// (and daylight-saving rules) can never shift a day.
function addDays(dateStr, n) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d + n));
  return dt.getUTCFullYear() + '-' + pad2(dt.getUTCMonth() + 1) + '-' + pad2(dt.getUTCDate());
}

function weekStart(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dow = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return addDays(dateStr, -((dow + 6) % 7));
}

function agendaDays(dateStr, weekMode) {
  if (!weekMode) return [dateStr];
  const start = weekStart(dateStr);
  return Array.from({ length: 7 }, (_, i) => addDays(start, i));
}

function toMinutes(time) {
  const [h, m] = time.split(':').map(Number);
  return h * 60 + m;
}

function formatDayLabel(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const dow = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return WEEKDAYS[(dow + 6) % 7] + ' ' + pad2(d) + '/' + pad2(m);
}

// How many times a booked service is charged - as the server does (hotel_service._stay_quantity): a timed service
// once per started duration (90 min on a 60 min massage: 2), a service without duration once per night (at least 1).
function bookingQuantity(service, booking) {
  const minutes = (new Date(booking.ends_at) - new Date(booking.starts_at)) / 60000;
  if (service.duration_minutes) return Math.max(Math.ceil(minutes / service.duration_minutes - 1e-9), 1);
  const day = (iso) => new Date(new Date(iso).getTime() + 3600000).toISOString().slice(0, 10);  // Luanda: UTC+1
  const nights = Math.round((Date.parse(day(booking.ends_at)) - Date.parse(day(booking.starts_at))) / 86400000);
  return Math.max(nights, 1);
}

// The reservations - a page for the manager, and a drawer in the till (Caixa) for the reception: same list, same
// forms, same actions. In the till (posId given) the activity is the till's own and a check-in bills the stay through
// that till, so there is never a till to pick.
export default function Reservas() {
  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <ReservasPanel />
    </main>
  );
}

// onPayStay(accountId): in the till, the check-out of a stay with something to pay - the till opens its account for
// the payment (closing it concludes the stay). Without it (the manager's page) that check-out is done at the till.
// onSale(invoiceId): in the till, a passage sold at the entry or a marcação charged - the till shows and prints its document.
export function ReservasPanel({ posId = null, activityId = null, onPayStay = null, onSale = null }) {
  const embedded = !!posId;
  // Cobrar: a marcação (spa, salão, consultório) paid at this till - its service sold, the booking concluded
  // (booking_charge_service). Shares the payment block of the Entrada: one of the two is open at a time.
  const [chargeTarget, setChargeTarget] = useState(null);
  // Entrada: a prepaid passage (hotel_service.walk_in) - a free room, a timed service, paid now at this till.
  const [walkInOpen, setWalkInOpen] = useState(false);
  const [walkInForm, setWalkInForm] = useState({ resourceId: '', serviceId: '', customerId: '', guestName: '', partySize: '' });
  const [walkInRooms, setWalkInRooms] = useState([]);
  const [walkInMethods, setWalkInMethods] = useState([]);
  const [walkInPayments, setWalkInPayments] = useState({});
  const [vatRates, setVatRates] = useState([]);
  const [withholdingTaxes, setWithholdingTaxes] = useState([]);
  const [walkInError, setWalkInError] = useState('');
  const [walkInSaving, setWalkInSaving] = useState(false);
  const [extendBooking, setExtendBooking] = useState(null);
  const [extendForm, setExtendForm] = useState({ date: '', time: '' });
  const [extendError, setExtendError] = useState('');
  const [extendSaving, setExtendSaving] = useState(false);
  const can = useCan();
  const [activities, setActivities] = useState([]);
  const [selectedActivityId, setSelectedActivityId] = useState('');
  // The activity's own workflow (the capabilities of its module): with the hotel stay a booking is billed through
  // its check-in and its account; without it (spa, salão, consultório) a marcação is charged at the till. The words
  // follow: the guest of a room, the client of a marcação. A module without any capability ticked keeps the old rule.
  const activityCapabilities = activities.find((a) => a.id === selectedActivityId)?.capabilities || [];
  const hasStay = activityCapabilities.length ? activityCapabilities.includes('HOTEL_STAY') : can('hotel:checkin');
  const personWord = hasStay ? 'hóspede' : 'cliente';
  const [resources, setResources] = useState([]);
  const [services, setServices] = useState([]);
  const [resourceTypesCatalog, setResourceTypesCatalog] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [customerModalOpen, setCustomerModalOpen] = useState(false);
  const [customerForm, setCustomerForm] = useState({ name: '', phoneNumber: '', nif: '', legalPersonType: 'FISICA', typeTouched: false });
  const [customerFormError, setCustomerFormError] = useState('');
  const [customerSaving, setCustomerSaving] = useState(false);
  const [selectedResourceId, setSelectedResourceId] = useState('');
  const [dateFrom, setDateFrom] = useState(todayIso());
  const [dateTo, setDateTo] = useState(todayIso());
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [statusUpdatingId, setStatusUpdatingId] = useState(null);
  const [checkActionId, setCheckActionId] = useState(null);
  const [posPickerOpen, setPosPickerOpen] = useState(false);
  const [posPickerBookingId, setPosPickerBookingId] = useState(null);
  const [posPickerOptions, setPosPickerOptions] = useState([]);
  const [posPickerSelected, setPosPickerSelected] = useState('');
  const [posPickerError, setPosPickerError] = useState('');
  const [posPickerSaving, setPosPickerSaving] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [form, setForm] = useState({ activityId: '', resourceId: '', serviceId: '', customerId: '', date: todayIso(), endDate: todayIso(), startTime: '14:00', endTime: '12:00', notes: '', guestName: '', partySize: '', endTouched: false });
  const [formResources, setFormResources] = useState([]);
  const [editingBookingId, setEditingBookingId] = useState(null);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  const [viewMode, setViewMode] = useState('list');
  const [agendaDate, setAgendaDate] = useState(todayIso());
  const [agendaBookings, setAgendaBookings] = useState([]);
  const [agendaLoading, setAgendaLoading] = useState(false);
  const [agendaVersion, setAgendaVersion] = useState(0);

  // The agenda (day = one column per resource, week = one column per day for the chosen
  // resource) loads its own bookings. One day either side of the visible range is fetched
  // and filtered by Luanda date on screen, so the naive date-time filters can never hide
  // a booking that crosses midnight. Late responses of an earlier navigation are ignored.
  useEffect(() => {
    if (viewMode !== 'agenda') return undefined;
    let cancelled = false;
    const days = agendaDays(agendaDate, !!selectedResourceId);
    const filters = {
      dateFrom: addDays(days[0], -1) + 'T00:00:00',
      dateTo: addDays(days[days.length - 1], 1) + 'T23:59:59',
    };
    if (selectedResourceId) filters.resourceId = selectedResourceId;
    setAgendaLoading(true);
    listBookings(filters)
      .then((data) => {
        if (cancelled) return;
        const resourceIds = new Set(resources.map((r) => r.id));
        setAgendaBookings(selectedResourceId ? data : data.filter((b) => resourceIds.has(b.resource_id)));
      })
      .catch((err) => {
        if (!cancelled) setError(extractErrorMessage(err, 'Erro ao carregar agenda'));
      })
      .finally(() => {
        if (!cancelled) setAgendaLoading(false);
      });
    return () => { cancelled = true; };
  }, [viewMode, agendaDate, selectedResourceId, resources, agendaVersion]);

  useEffect(() => {
    listActivities().then((data) => {
      const active = data.filter((a) => a.is_active);
      setActivities(active);
      // In the till: the till's own activity. Otherwise one active activity is selected for the user, else the choice stays free.
      if (activityId) setSelectedActivityId(activityId);
      else if (active.length === 1) setSelectedActivityId(active[0].id);
    }).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar atividades')));
    listServices().then((data) => setServices(data.filter((s) => s.is_active))).catch(() => {});
    listResourceTypes().then(setResourceTypesCatalog).catch(() => {});
    listCustomers().then(setCustomers).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedActivityId) return;
    listResources(selectedActivityId).then((data) => {
      const active = data.filter((r) => r.is_active);
      setResources(active);
      setSelectedResourceId('');
    }).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar recursos')));
  }, [selectedActivityId]);

  useEffect(() => {
    loadBookings();
  }, [selectedResourceId, dateFrom, dateTo, resources]);

  // Form's own resource list, scoped to whichever activity is picked INSIDE the
  // modal - independent of the page-level activity tab, so creating a booking
  // never silently targets the wrong activity just because a different tab
  // happened to be selected when the modal was opened (see the "reserva criada
  // no Bar em vez do Hotel" discussion).
  useEffect(() => {
    if (!formOpen || !form.activityId) { setFormResources([]); return; }
    listResources(form.activityId).then((data) => setFormResources(data.filter((r) => r.is_active))).catch(() => setFormResources([]));
  }, [formOpen, form.activityId]);

  async function loadBookings() {
    setLoading(true);
    setError('');
    try {
      const filters = {
        dateFrom: dateFrom ? dateFrom + 'T00:00:00' : undefined,
        dateTo: dateTo ? dateTo + 'T23:59:59' : undefined,
      };
      if (selectedResourceId) filters.resourceId = selectedResourceId;
      const data = await listBookings(filters);
      const resourceIds = new Set(resources.map((r) => r.id));
      setBookings(selectedResourceId ? data : data.filter((b) => resourceIds.has(b.resource_id)));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao carregar reservas'));
    } finally {
      setLoading(false);
    }
  }

  function openCreateForm() {
    const today = todayIso();
    setEditingBookingId(null);
    setForm({ activityId: selectedActivityId, resourceId: '', serviceId: '', customerId: '', date: today, endDate: addDays(today, 1), startTime: '14:00', endTime: '12:00', notes: '', guestName: '', partySize: '', endTouched: false });
    setFormError('');
    setFormOpen(true);
  }

  function openEditForm(b) {
    const startsParts = luandaDateParts(b.starts_at);
    const endsParts = luandaDateParts(b.ends_at);
    const resource = resources.find((r) => r.id === b.resource_id);
    setEditingBookingId(b.id);
    setForm({
      activityId: resource?.activity_id || selectedActivityId,
      resourceId: b.resource_id,
      serviceId: b.service_id || '',
      customerId: b.customer_id || '',
      date: startsParts.date,
      endDate: endsParts.date,
      startTime: startsParts.time,
      endTime: endsParts.time,
      notes: b.notes || '',
      guestName: b.guest_name || '',
      partySize: b.party_size ? String(b.party_size) : '',
    });
    setFormError('');
    setFormOpen(true);
  }

  // A table or a practitioner (a resource type without usual hours) is booked on the same day, unlike a
  // hotel room (check-in 14:00, check-out 12:00 the next day). While the times are still the untouched
  // defaults, picking such a resource switches to a same-day slot: next full hour for today (12:00 for a
  // future date), as long as the chosen service (two hours without one).
  function handleResourceChange(resourceId) {
    setForm((prev) => {
      const next = { ...prev, resourceId };
      if (editingBookingId) return next;
      const resource = formResources.find((r) => r.id === resourceId);
      const type = resourceTypesCatalog.find((rt) => rt.id === resource?.resource_type_id);
      const untouched = !prev.endTouched && prev.startTime === '14:00' && prev.endTime === '12:00';
      if (type?.default_start_time && type?.default_end_time && untouched) {
        // the usual hours of this type (Catálogos): a room 14:00 -> 12:00, the night rule below sets the next day
        next.startTime = type.default_start_time.slice(0, 5);
        next.endTime = type.default_end_time.slice(0, 5);
        next.endDate = next.date;
        return withAutoEnd(next);
      }
      // A type without usual hours (a table, a practitioner): a same-day slot from the next full hour - an hour
      // already past is never proposed. The end follows the chosen service's duration (withAutoEnd), else 2 hours.
      if (type && untouched) {
        next.endDate = next.date;
        const startHour = prev.date === todayIso() ? Math.min(new Date().getHours() + 1, 21) : 12;
        const pad = (n) => String(n).padStart(2, '0');
        next.startTime = pad(startHour) + ':00';
        next.endTime = pad(startHour + 2) + ':00';
        return withAutoEnd(next);
      }
      return next;
    });
  }

  // When the chosen service has a default duration, the end time follows the start
  // (start + duration, possibly on the next day) until the end is edited by hand.
  // Never applied when editing an existing booking. UTC arithmetic on the naive
  // date/time strings, so browser daylight-saving rules cannot shift the result.
  // Without a duration (a night), an exit hour not after the entry hour means the next day: 14:00 -> 12:00 tomorrow.
  function withAutoEnd(next) {
    if (editingBookingId || next.endTouched) return next;
    const service = next.serviceId ? services.find((s) => s.id === next.serviceId) : null;
    if (!service || !service.duration_minutes || !next.date || !next.startTime) {
      if (next.date && next.startTime && next.endTime && next.endTime <= next.startTime && (!next.endDate || next.endDate <= next.date)) {
        return { ...next, endDate: addDays(next.date, 1) };
      }
      return next;
    }
    const [y, mo, d] = next.date.split('-').map(Number);
    const [hh, mm] = next.startTime.split(':').map(Number);
    const end = new Date(Date.UTC(y, mo - 1, d, hh, mm) + service.duration_minutes * 60000);
    const pad = (n) => String(n).padStart(2, '0');
    return {
      ...next,
      endDate: end.getUTCFullYear() + '-' + pad(end.getUTCMonth() + 1) + '-' + pad(end.getUTCDate()),
      endTime: pad(end.getUTCHours()) + ':' + pad(end.getUTCMinutes()),
    };
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    if (!form.resourceId || !form.date || !form.endDate || !form.startTime || !form.endTime) {
      setFormError('Preencha todos os campos obrigatorios');
      return;
    }
    if (form.endDate < form.date) {
      setFormError('A data de fim deve ser posterior ou igual a data de inicio');
      return;
    }
    if (form.endDate === form.date && form.endTime <= form.startTime) {
      setFormError('No mesmo dia, a hora de saida deve ser posterior a hora de entrada');
      return;
    }
    if (form.partySize && !(parseInt(form.partySize, 10) >= 1)) {
      setFormError('O numero de pessoas deve ser pelo menos 1');
      return;
    }
    if (selectedResourceType?.requires_service && !form.serviceId) {
      setFormError(`Este tipo de recurso (${selectedResourceType.name}) exige um servico associado a reserva`);
      return;
    }
    setSaving(true);
    try {
      const startsAt = form.date + 'T' + form.startTime + ':00';
      const endsAt = form.endDate + 'T' + form.endTime + ':00';
      if (editingBookingId) {
        await rescheduleBooking(editingBookingId, startsAt, endsAt, form.serviceId || null, form.notes || null, form.customerId || null, form.guestName.trim() || null, form.partySize ? parseInt(form.partySize, 10) : null);
      } else {
        await createBooking({
          resource_id: form.resourceId,
          service_id: form.serviceId || null,
          customer_id: form.customerId || null,
          starts_at: startsAt,
          ends_at: endsAt,
          notes: form.notes || null,
          guest_name: form.guestName.trim() || null,
          party_size: form.partySize ? parseInt(form.partySize, 10) : null,
        });
      }
      setFormOpen(false);
      setAgendaVersion((v) => v + 1);
      await loadBookings();
    } catch (err) {
      setFormError(extractErrorMessage(err, editingBookingId ? 'Erro ao guardar alteracoes' : 'Erro ao criar reserva'));
    } finally {
      setSaving(false);
    }
  }

  async function handleStatusChange(bookingId, newStatus) {
    setStatusUpdatingId(bookingId);
    try {
      await updateBookingStatus(bookingId, newStatus);
      await loadBookings();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao atualizar estado da reserva'));
    } finally {
      setStatusUpdatingId(null);
    }
  }

  async function handleCheckIn(bookingId) {
    setCheckActionId(bookingId);
    setError('');
    try {
      await checkIn(bookingId, posId);
      await loadBookings();
    } catch (err) {
      if (err.response?.status === 409 && (err.response?.data?.detail || '').includes('mais de uma caixa aberta')) {
        await openPosPicker(bookingId);
      } else {
        setError(extractErrorMessage(err, 'Erro ao fazer check-in'));
      }
    } finally {
      setCheckActionId(null);
    }
  }

  async function openPosPicker(bookingId) {
    const booking = bookings.find((b) => b.id === bookingId);
    const resource = resources.find((r) => r.id === booking?.resource_id);
    setPosPickerBookingId(bookingId);
    setPosPickerSelected('');
    setPosPickerError('');
    setPosPickerOptions([]);
    setPosPickerOpen(true);
    if (resource?.activity_id) {
      try {
        const pos = await listPointsOfSale(resource.activity_id);
        setPosPickerOptions(pos.filter((p) => p.is_active));
      } catch (err) {
        setPosPickerError(extractErrorMessage(err, 'Erro ao carregar pontos de venda'));
      }
    }
  }

  async function handlePosPickerConfirm() {
    if (!posPickerSelected) {
      setPosPickerError('Selecione um ponto de venda');
      return;
    }
    setPosPickerSaving(true);
    setPosPickerError('');
    try {
      await checkIn(posPickerBookingId, posPickerSelected);
      setPosPickerOpen(false);
      await loadBookings();
    } catch (err) {
      setPosPickerError(extractErrorMessage(err, 'Erro ao fazer check-in'));
    } finally {
      setPosPickerSaving(false);
    }
  }

  async function handleCheckOut(bookingId) {
    setCheckActionId(bookingId);
    setError('');
    try {
      await checkOut(bookingId);
      await loadBookings();
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao fazer check-out'));
    } finally {
      setCheckActionId(null);
    }
  }

  // Prolongar: a new end for a stay in progress - the room-rate line of its account follows (hotel_service.extend_stay).
  function openExtendForm(b) {
    const ends = luandaDateParts(b.ends_at);
    setExtendBooking(b);
    setExtendForm({ date: ends.date, time: ends.time });
    setExtendError('');
  }

  async function handleExtendSubmit(e) {
    e.preventDefault();
    if (!extendForm.date || !extendForm.time) {
      setExtendError('Indique a nova data e hora de saída');
      return;
    }
    setExtendSaving(true);
    setExtendError('');
    try {
      await extendStay(extendBooking.id, extendForm.date + 'T' + extendForm.time + ':00');
      setExtendBooking(null);
      await loadBookings();
    } catch (err) {
      setExtendError(extractErrorMessage(err, 'Erro ao prolongar a estadia'));
    } finally {
      setExtendSaving(false);
    }
  }

  // What a payment at this till needs: its methods, the VAT rates (the total) and the withholdings (company customers).
  async function loadPaymentContext() {
    const [methods, rates] = await Promise.all([listPaymentMethodPreferences(), listVatRates()]);
    setWalkInMethods(methods.filter((m) => m.available_at_pos && m.allows_receipt));
    setVatRates(rates);
    withholdingTaxesApi.list().then(setWithholdingTaxes).catch(() => {});
  }

  async function openWalkIn() {
    setChargeTarget(null);
    setWalkInForm({ resourceId: '', serviceId: '', customerId: '', guestName: '', partySize: '' });
    setWalkInPayments({});
    setWalkInError('');
    setWalkInOpen(true);
    try {
      const [statuses] = await Promise.all([listResourceStatuses(selectedActivityId), loadPaymentContext()]);
      setWalkInRooms(statuses.filter((s) => s.status === 'LIVRE'));
    } catch (err) {
      setWalkInError(extractErrorMessage(err, 'Erro ao carregar os quartos livres'));
    }
  }

  // Cobrar: the customer of the invoice starts as the booking's own (Consumidor final when it has none).
  async function openCharge(b) {
    setWalkInOpen(false);
    setWalkInForm({ resourceId: '', serviceId: '', customerId: b.customer_id || '', guestName: '', partySize: '' });
    setWalkInPayments({});
    setWalkInError('');
    setChargeTarget(b);
    try {
      await loadPaymentContext();
    } catch (err) {
      setWalkInError(extractErrorMessage(err, 'Erro ao carregar os métodos de pagamento'));
    }
  }

  async function handleChargeSubmit(e) {
    e.preventDefault();
    if (Math.abs(walkInPaid - walkInDue) > 0.009) {
      setWalkInError('O pagamento (' + formatKz(walkInPaid) + ' Kz) deve ser igual ao valor a pagar (' + formatKz(walkInDue) + ' Kz)');
      return;
    }
    setWalkInSaving(true);
    setWalkInError('');
    try {
      const result = await chargeBooking(chargeTarget.id, {
        pos_id: posId,
        payments: Object.entries(walkInPayments).filter(([, v]) => Number(v) > 0).map(([id, v]) => ({ payment_method_id: id, amount: Number(v) })),
        customer_id: walkInForm.customerId || null,  // none: Consumidor final
      });
      setChargeTarget(null);
      setAgendaVersion((v) => v + 1);
      await loadBookings();
      if (onSale) await onSale(result.invoice_id);
    } catch (err) {
      setWalkInError(extractErrorMessage(err, 'Erro ao cobrar a reserva'));
    } finally {
      setWalkInSaving(false);
    }
  }

  // the timed services of the chosen room's type (a night is a booking, not a passage)
  const walkInRoom = resources.find((r) => r.id === walkInForm.resourceId);
  const walkInServices = services.filter((s) => s.duration_minutes && (!s.resource_type_id || s.resource_type_id === walkInRoom?.resource_type_id));
  const walkInService = services.find((s) => s.id === walkInForm.serviceId);
  // What is sold: the Entrada's service once, or the charged marcação's service as many times as it lasts.
  const chargeService = chargeTarget ? services.find((s) => s.id === chargeTarget.service_id) : null;
  const saleService = chargeTarget ? chargeService : walkInService;
  const saleQuantity = chargeTarget && chargeService ? bookingQuantity(chargeService, chargeTarget) : 1;
  const saleSubtotal = saleService ? Math.round(Number(saleService.price || 0) * saleQuantity * 100) / 100 : 0;
  // the price before VAT, plus its rate - rounded as the invoice does (create_invoice)
  const walkInTotal = (() => {
    if (!saleService) return 0;
    const rate = Number(vatRates.find((v) => v.id === saleService.vat_id)?.rate || 0);
    return Math.round((saleSubtotal + Math.round(saleSubtotal * rate) / 100) * 100) / 100;
  })();
  // a company customer keeps the withholding of the service, if it carries one: the till collects the rest
  const walkInRetention = saleService ? withholdingOf(
    [{ service_id: saleService.id, subtotal: saleSubtotal }],
    { services, withholdingTaxes, customer: customers.find((c) => c.id === walkInForm.customerId) || null },
  ) : 0;
  const walkInDue = Math.round((walkInTotal - walkInRetention) * 100) / 100;
  const walkInPaid = Object.values(walkInPayments).reduce((sum, v) => sum + (Number(v) || 0), 0);
  const walkInRemaining = Math.round((walkInDue - walkInPaid) * 100) / 100;

  // As in the till's Fechar conta: nothing chosen for the reception - ticking a method puts the rest on it.
  function chooseWalkInService(serviceId) {
    setWalkInForm((p) => ({ ...p, serviceId }));
    setWalkInPayments({});
  }

  function toggleWalkInPayment(methodId) {
    setWalkInPayments((prev) => {
      if (methodId in prev) {
        const next = { ...prev };
        delete next[methodId];
        return next;
      }
      const paid = Object.values(prev).reduce((sum, v) => sum + (Number(v) || 0), 0);
      return { ...prev, [methodId]: Math.max(Math.round((walkInDue - paid) * 100) / 100, 0) };
    });
  }

  async function handleWalkInSubmit(e) {
    e.preventDefault();
    if (!walkInForm.resourceId || !walkInForm.serviceId) {
      setWalkInError('Escolha o quarto e o serviço');
      return;
    }
    if (Math.abs(walkInPaid - walkInDue) > 0.009) {
      setWalkInError('O pagamento (' + formatKz(walkInPaid) + ' Kz) deve ser igual ao valor a pagar (' + formatKz(walkInDue) + ' Kz)');
      return;
    }
    setWalkInSaving(true);
    setWalkInError('');
    try {
      const result = await walkIn({
        resource_id: walkInForm.resourceId,
        service_id: walkInForm.serviceId,
        pos_id: posId,
        payments: Object.entries(walkInPayments).filter(([, v]) => Number(v) > 0).map(([id, v]) => ({ payment_method_id: id, amount: Number(v) })),
        customer_id: walkInForm.customerId || null,  // none: Consumidor final
        guest_name: walkInForm.guestName.trim() || null,
        party_size: walkInForm.partySize ? parseInt(walkInForm.partySize, 10) : null,
      });
      setWalkInOpen(false);
      await loadBookings();
      if (onSale) await onSale(result.invoice_id);
    } catch (err) {
      setWalkInError(extractErrorMessage(err, 'Erro ao registar a entrada'));
    } finally {
      setWalkInSaving(false);
    }
  }

  function openCustomerModal() {
    setCustomerForm({ name: '', phoneNumber: '', nif: '', legalPersonType: 'FISICA', typeTouched: false });
    setCustomerFormError('');
    setCustomerModalOpen(true);
  }

  async function handleCustomerSubmit(e) {
    e.preventDefault();
    setCustomerFormError('');
    setCustomerSaving(true);
    try {
      const created = await createCustomer({
        name: customerForm.name,
        phone_number: customerForm.phoneNumber,
        nif: customerForm.nif || '',
        is_final_consumer: !customerForm.nif,
        legal_person_type: customerForm.nif ? customerForm.legalPersonType : 'FISICA',  // a final consumer is a private person
      });
      setCustomers((prev) => [...prev, created]);
      if (walkInOpen || chargeTarget) setWalkInForm((p) => ({ ...p, customerId: created.id }));
      else setForm((p) => ({ ...p, customerId: created.id }));
      setCustomerModalOpen(false);
    } catch (err) {
      setCustomerFormError(extractErrorMessage(err, 'Erro ao criar cliente'));
    } finally {
      setCustomerSaving(false);
    }
  }

  // a booking whose service has a price: it ends with its payment, never concluded by hand
  function isPriced(b) {
    return Number(services.find((s) => s.id === b.service_id)?.price || 0) > 0;
  }

  // a marcação charged at the till (Cobrar): concluded with its invoice, never checked out - shown as Paga
  function isPaidMarcacao(b) {
    return !hasStay && b.status === 'CONCLUIDA' && !!b.invoice_id && !b.checked_out_at;
  }

  // a booking of a later day: charged on its own day only (booking_charge_service refuses it before)
  function isLaterDay(b) {
    return luandaDateParts(b.starts_at).date > luandaDateParts(new Date().toISOString()).date;
  }

  function resourceName(resourceId) {
    return resources.find((r) => r.id === resourceId)?.name || '-';
  }

  // The resource currently picked in the form (from formResources when creating,
  // or the page-level resources list when editing - see openEditForm) - drives
  // both which services are offered (matching resource_type_id, or generic
  // services with no resource_type_id) and whether one is mandatory
  // (ResourceTypeCatalog.requires_service, e.g. a CHAMBRE always has a rate).
  const selectedResource = (editingBookingId ? resources : formResources).find((r) => r.id === form.resourceId);
  const selectedResourceType = resourceTypesCatalog.find((t) => t.id === selectedResource?.resource_type_id);
  const availableServices = selectedResource
    ? services.filter((s) => !s.resource_type_id || s.resource_type_id === selectedResource.resource_type_id)
    : services;

  // Angola only ever operates in Africa/Luanda (UTC+1, no DST) - display must
  // show that time regardless of the viewing device's own system timezone, or a
  // browser/OS set to a different offset would render a misleading local hour
  // (see the "16h/14h" confusion - the stored UTC values were correct all along,
  // only the display was shifting by the device's own timezone difference).
  function formatDateTime(iso) {
    return new Date(iso).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Luanda' });
  }

  function luandaDateParts(iso) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Africa/Luanda', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(new Date(iso));
    const get = (type) => parts.find((p) => p.type === type)?.value || '00';
    return { date: `${get('year')}-${get('month')}-${get('day')}`, time: `${get('hour')}:${get('minute')}` };
  }

  function openCreateFormAt(resourceId, date, startMinutes) {
    const startTime = pad2(Math.floor(startMinutes / 60)) + ':' + pad2(startMinutes % 60);
    let endDate = date;
    let endTotal = startMinutes + 60;
    if (endTotal >= 1440) {
      endDate = addDays(date, 1);
      endTotal -= 1440;
    }
    setEditingBookingId(null);
    setForm({
      activityId: selectedActivityId, resourceId, serviceId: '', customerId: '',
      date, endDate, startTime, endTime: pad2(Math.floor(endTotal / 60)) + ':' + pad2(endTotal % 60),
      notes: '', guestName: '', partySize: '', endTouched: false,
    });
    setFormError('');
    setFormOpen(true);
  }

  // The customer of the invoice (Entrada, Cobrar): Consumidor final unless one is chosen, + creates one.
  function renderInvoiceCustomer() {
    return (
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Cliente da fatura (opcional - sem cliente: Consumidor final)</label>
            <div className="flex items-center gap-1.5">
              <div className="flex-1">
                <Select
                  value={walkInForm.customerId}
                  onChange={(v) => { setWalkInForm((p) => ({ ...p, customerId: v })); setWalkInPayments({}); }}
                  options={[{ value: '', label: 'Consumidor final' }, ...customers.map((c) => ({ value: c.id, label: c.name + (c.nif ? ' - NIF ' + c.nif : '') }))]}
                  placeholder="Consumidor final"
                />
              </div>
              <button type="button" onClick={openCustomerModal} disabled={!can('customers:create')} title="Novo cliente (nome e NIF)" className="flex items-center justify-center w-10 h-10 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer shrink-0 disabled:opacity-40 disabled:cursor-not-allowed">
                <Plus size={15} />
              </button>
            </div>
          </div>
    );
  }

  // The payment at this till (Entrada, Cobrar): the total, the withholding of a company customer, then the methods -
  // none ticked at first, ticking one puts the rest on it.
  function renderPayment(totalLabel) {
    return (
            <div className="bg-bg-inset border border-border rounded-md p-3.5 flex flex-col gap-2.5">
              <div className="flex items-center justify-between">
                <span className="text-text-muted text-[13px]">{totalLabel}</span>
                <span className="font-mono text-text-primary font-semibold">{formatKz(walkInTotal)} Kz</span>
              </div>
              {walkInRetention > 0 && (
                <>
                  <div className="flex items-center justify-between text-[13px]">
                    <span className="text-text-muted">Retenção na fonte (fica com o cliente)</span>
                    <span className="font-mono text-text-primary">- {formatKz(walkInRetention)} Kz</span>
                  </div>
                  <div className="flex items-center justify-between text-[13px]">
                    <span className="text-text-primary font-semibold">A pagar</span>
                    <span className="font-mono text-text-primary font-semibold">{formatKz(walkInDue)} Kz</span>
                  </div>
                </>
              )}
              {walkInMethods.map((m) => (
                <div key={m.id} className="flex items-center justify-between gap-3">
                  <label className="flex items-center gap-2 flex-1 cursor-pointer select-none">
                    <input type="checkbox" checked={m.id in walkInPayments} onChange={() => toggleWalkInPayment(m.id)} className="w-4 h-4 accent-accent cursor-pointer" />
                    <span className="text-[13px] text-text-primary">{m.short_label || m.name}</span>
                  </label>
                  {m.id in walkInPayments && (
                    <input type="number" min="0" step="0.01" value={walkInPayments[m.id]} onChange={(e) => setWalkInPayments((p) => ({ ...p, [m.id]: e.target.value }))} className="w-36 bg-bg-elevated border border-border rounded-md px-3 py-2 text-sm text-right font-mono text-text-primary outline-none focus:border-accent transition-colors" />
                  )}
                </div>
              ))}
              <div className={'text-[12px] px-3 py-2 rounded-r border-l-2 ' + (walkInRemaining === 0 ? 'bg-success/10 border-success text-success' : walkInRemaining > 0 ? 'bg-accent/10 border-accent text-accent' : 'bg-danger/10 border-danger text-danger')}>
                {walkInRemaining === 0 ? 'Valor exato' : walkInRemaining > 0 ? `Falta ${formatKz(walkInRemaining)} Kz` : `Excede em ${formatKz(Math.abs(walkInRemaining))} Kz`}
              </div>
            </div>
    );
  }

  function renderAgenda() {
    const weekMode = !!selectedResourceId;
    const days = agendaDays(agendaDate, weekMode);
    const nowParts = luandaDateParts(new Date().toISOString());
    const nowMin = toMinutes(nowParts.time);
    const canCreate = can('bookings:create');

    const columns = weekMode
      ? days.map((day) => ({ key: day, title: formatDayLabel(day), subtitle: null, day, resourceId: selectedResourceId }))
      : resources.map((r) => ({ key: r.id, title: r.name, subtitle: r.capacity ? r.capacity + ' lugares' : null, day: agendaDate, resourceId: r.id }));

    const visible = agendaBookings.filter((b) => b.status !== 'CANCELADA' && b.status !== 'NO_SHOW');
    const segsByCol = columns.map((col) => visible
      .filter((b) => b.resource_id === col.resourceId)
      .map((b) => {
        const s = luandaDateParts(b.starts_at);
        const e = luandaDateParts(b.ends_at);
        if (s.date > col.day || e.date < col.day) return null;
        const startMin = s.date < col.day ? 0 : toMinutes(s.time);
        const endMin = e.date > col.day ? 1440 : toMinutes(e.time);
        if (endMin <= startMin) return null;
        return { b, startMin, endMin, startsHere: s.date === col.day, endsHere: e.date === col.day };
      })
      .filter(Boolean));

    let startHour = AGENDA_DEFAULT_START;
    let endHour = AGENDA_DEFAULT_END;
    segsByCol.flat().forEach((sg) => {
      startHour = Math.min(startHour, Math.floor(sg.startMin / 60));
      endHour = Math.max(endHour, Math.ceil(sg.endMin / 60));
    });
    const hours = Array.from({ length: endHour - startHour }, (_, i) => startHour + i);
    const totalHeight = (endHour - startHour) * HOUR_PX;

    function handleSlotClick(col, ev) {
      if (!canCreate || col.day < nowParts.date) return;
      const rect = ev.currentTarget.getBoundingClientRect();
      const offset = Math.max(0, ev.clientY - rect.top);
      const minutes = startHour * 60 + Math.floor(offset / (HOUR_PX / 2)) * 30;
      openCreateFormAt(col.resourceId, col.day, Math.min(minutes, 23 * 60 + 30));
    }

    return (
      <div>
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          <button
            type="button"
            onClick={() => setAgendaDate(addDays(agendaDate, weekMode ? -7 : -1))}
            aria-label="Anterior"
            className="flex items-center justify-center w-9 h-9 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer"
          >
            <ChevronLeft size={16} />
          </button>
          <DateInput
            value={agendaDate}
            onChange={(ev) => { if (ev.target.value) setAgendaDate(ev.target.value); }}
            className="bg-bg-inset border border-border rounded-md px-3.5 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors"
          />
          <button
            type="button"
            onClick={() => setAgendaDate(addDays(agendaDate, weekMode ? 7 : 1))}
            aria-label="Seguinte"
            className="flex items-center justify-center w-9 h-9 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer"
          >
            <ChevronRight size={16} />
          </button>
          <button
            type="button"
            onClick={() => setAgendaDate(nowParts.date)}
            className="px-3.5 py-1.5 rounded-md text-[13px] font-medium bg-bg-elevated border border-border text-text-muted hover:text-text-primary transition-colors cursor-pointer"
          >
            Hoje
          </button>
          {weekMode && (
            <button
              type="button"
              onClick={() => setSelectedResourceId('')}
              className="px-3.5 py-1.5 rounded-md text-[13px] font-medium bg-bg-elevated border border-border text-text-muted hover:text-text-primary transition-colors cursor-pointer"
            >
              Ver todos os recursos
            </button>
          )}
          {agendaLoading && <Loader2 size={16} className="animate-spin text-accent" />}
          <span className="text-text-muted text-[12px]">
            {weekMode ? 'Semana de ' + formatDayLabel(days[0]) + ' - recurso selecionado' : 'Dia ' + formatDayLabel(agendaDate) + ' - selecione um recurso para ver a semana'}
          </span>
        </div>

        {columns.length === 0 ? (
          <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
            <CalendarClock size={28} className="text-text-muted mx-auto mb-3" />
            <p className="text-text-primary font-medium mb-1">Nenhum recurso ativo nesta atividade</p>
          </div>
        ) : (
          <div className="bg-bg-elevated border border-border rounded-lg overflow-x-auto">
            <div style={{ minWidth: 56 + columns.length * 140 }}>
              <div className="flex border-b border-border bg-bg-inset">
                <div className="w-14 shrink-0" />
                {columns.map((col) => (
                  <div key={col.key} className={'flex-1 min-w-[140px] px-3 py-2 border-l border-border ' + (weekMode && col.day === nowParts.date ? 'bg-accent/10' : '')}>
                    <p className="text-[13px] font-medium text-text-primary truncate">{col.title}</p>
                    {col.subtitle && <p className="text-[11px] text-text-muted">{col.subtitle}</p>}
                  </div>
                ))}
              </div>
              <div className="flex">
                <div className="w-14 shrink-0 relative" style={{ height: totalHeight }}>
                  {hours.map((h) => (
                    <span key={h} className="absolute right-2 text-[10px] text-text-muted font-mono" style={{ top: (h - startHour) * HOUR_PX + 2 }}>{pad2(h)}:00</span>
                  ))}
                </div>
                {columns.map((col, ci) => {
                  const clickable = canCreate && col.day >= nowParts.date;
                  const showNow = col.day === nowParts.date && nowMin >= startHour * 60 && nowMin <= endHour * 60;
                  return (
                    <div
                      key={col.key}
                      onClick={(ev) => handleSlotClick(col, ev)}
                      className={'flex-1 min-w-[140px] relative border-l border-border ' + (clickable ? 'cursor-pointer hover:bg-accent/5' : '')}
                      style={{ height: totalHeight }}
                    >
                      {hours.map((h) => (
                        <div key={h} className="absolute inset-x-0 border-t border-border/60 pointer-events-none" style={{ top: (h - startHour) * HOUR_PX }} />
                      ))}
                      {showNow && (
                        <div className="absolute inset-x-0 border-t-2 border-danger pointer-events-none z-10" style={{ top: (nowMin - startHour * 60) / 60 * HOUR_PX }} />
                      )}
                      {segsByCol[ci].map((sg) => {
                        const b = sg.b;
                        const s = luandaDateParts(b.starts_at);
                        const e = luandaDateParts(b.ends_at);
                        const who = b.guest_name || customers.find((c) => c.id === b.customer_id)?.name || '';
                        const svc = services.find((x) => x.id === b.service_id)?.name || '';
                        const editable = can('bookings:update') && (b.status === 'PENDENTE' || b.status === 'CONFIRMADA');
                        return (
                          <div
                            key={b.id}
                            onClick={(ev) => { ev.stopPropagation(); if (editable) openEditForm(b); }}
                            title={formatDateTime(b.starts_at) + ' - ' + formatDateTime(b.ends_at) + (who ? ' - ' + who : '')}
                            className={'absolute left-1 right-1 rounded-md border px-2 py-1 overflow-hidden text-[11px] leading-tight ' + (isPaidMarcacao(b) ? AGENDA_STATUS_STYLE.CONFIRMADA : (AGENDA_STATUS_STYLE[b.status] || AGENDA_STATUS_STYLE.PENDENTE)) + (editable ? ' cursor-pointer' : ' cursor-default')}
                            style={{ top: (sg.startMin - startHour * 60) / 60 * HOUR_PX, height: Math.max((sg.endMin - sg.startMin) / 60 * HOUR_PX - 2, 22) }}
                          >
                            <p className="font-mono font-semibold">{(sg.startsHere ? s.time : '00:00') + ' - ' + (sg.endsHere ? e.time : '24:00')}</p>
                            {who && <p className="truncate">{who}{b.party_size ? ' (' + b.party_size + ' pax)' : ''}</p>}
                            {svc && <p className="truncate opacity-80">{svc}</p>}
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      {!embedded && (
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
          <CalendarClock size={22} className="text-accent" />
          Reservas
        </h2>
      )}
      {!embedded && <p className="text-text-muted text-sm mb-6">Gerir reservas de quartos, praticantes, mesas ou qualquer outro recurso</p>}

      {activities.length > 1 && !activityId && (
        <div className="flex items-center gap-2 mb-4 flex-wrap">
          {activities.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelectedActivityId(a.id)}
              className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (selectedActivityId === a.id ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
            >
              {a.name}
            </button>
          ))}
        </div>
      )}

      {/* One row: the view (Lista / Agenda) on the left, the actions (Entrada for a hotel, Nova reserva) on the right. */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <button
          type="button"
          onClick={() => setViewMode('list')}
          className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (viewMode === 'list' ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
        >
          Lista
        </button>
        <button
          type="button"
          onClick={() => setViewMode('agenda')}
          className={'px-3.5 py-1.5 rounded-md text-[13px] font-medium transition-colors cursor-pointer ' + (viewMode === 'agenda' ? 'bg-accent text-white' : 'bg-bg-elevated border border-border text-text-muted hover:text-text-primary')}
        >
          Agenda
        </button>
        <div className="ml-auto flex items-center gap-2">
          {embedded && hasStay && (
            <button
              onClick={openWalkIn}
              disabled={resources.length === 0}
              title="Passagem paga já: quarto livre, serviço com duração"
              className="flex items-center gap-2 border border-accent text-accent hover:bg-accent/10 disabled:opacity-50 font-medium text-[13px] px-3.5 py-1.5 rounded-md transition-colors cursor-pointer"
            >
              <DoorOpen size={15} />
              Entrada
            </button>
          )}
          <button
            onClick={openCreateForm}
            disabled={resources.length === 0 || !can('bookings:create')}
            className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-[13px] px-3.5 py-1.5 rounded-md transition-colors cursor-pointer"
          >
            <Plus size={15} />
            Nova reserva
          </button>
        </div>
      </div>

      {!selectedActivityId && activities.length > 1 && !activityId && (
        <p className="text-text-muted text-[13px] mb-4">Selecione uma atividade para ver os recursos e as reservas</p>
      )}

      <div className="flex items-end gap-2.5 mb-5 flex-wrap">
        <div className="w-56">
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Recurso</label>
          <Select
            value={selectedResourceId}
            onChange={setSelectedResourceId}
            options={resources.map((r) => ({ value: r.id, label: r.name }))}
            placeholder="Todos os recursos"
          />
        </div>
        {viewMode === 'list' && (
          <>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">De</label>
          <DateInput value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Ate</label>
          <DateInput value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
        </div>
          </>
        )}
      </div>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {viewMode === 'agenda' ? renderAgenda() : loading ? (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      ) : bookings.length === 0 ? (
        <div className="bg-bg-elevated border border-border rounded-lg p-10 text-center">
          <CalendarClock size={28} className="text-text-muted mx-auto mb-3" />
          <p className="text-text-primary font-medium mb-1">Nenhuma reserva neste periodo</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {bookings.map((b) => (
            <div key={b.id} className="bg-bg-elevated border border-border rounded-lg px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
              <div>
                <p className="text-text-primary font-medium text-sm">{resourceName(b.resource_id)}</p>
                <p className="text-text-muted text-[12px] font-mono mt-0.5">{formatDateTime(b.starts_at)} - {formatDateTime(b.ends_at)}</p>
                {b.status === 'EM_CURSO' && new Date(b.ends_at) < new Date() && (
                  <p className="text-danger text-[12px] font-semibold mt-0.5">Excedido {Math.floor((Date.now() - new Date(b.ends_at).getTime()) / 60000)} min</p>
                )}
                {(b.guest_name || b.party_size) && (
                  <p className="text-text-primary text-[12px] mt-0.5">{b.guest_name}{b.party_size ? (b.guest_name ? ' - ' : '') + b.party_size + ' pax' : ''}</p>
                )}
                {b.notes && <p className="text-text-muted text-[12px] mt-0.5">{b.notes}</p>}
              </div>
              <div className="flex items-center gap-2">
                {/* a marcação charged at the till: paid, before, during and after the service - it keeps its slot */}
                <span className={'text-[11px] font-semibold px-2.5 py-1 rounded-full ' + (isPaidMarcacao(b) ? 'text-success bg-success/10' : (STATUS_COLORS[b.status] || ''))}>{isPaidMarcacao(b) ? 'Paga' : (STATUS_LABELS[b.status] || b.status)}</span>
                {checkActionId === b.id || statusUpdatingId === b.id ? (
                  <Loader2 size={16} className="animate-spin text-accent" />
                ) : b.status === 'EM_CURSO' ? (
                  <>
                    {b.stay_account_total > 0 && (
                      <span className="text-[12px] font-mono text-text-primary whitespace-nowrap" title="Conta da estadia (IVA incluído)">{formatKz(b.stay_account_total)} Kz</span>
                    )}
                    <button
                      onClick={() => openExtendForm(b)}
                      disabled={!can('bookings:update')}
                      className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <CalendarClock size={12} />
                      Prolongar
                    </button>
                    {b.stay_account_total > 0 ? (
                      // Something to pay: the check-out is the payment of the stay's account, at the till.
                      <span title={onPayStay ? 'Pagar a conta da estadia e terminar' : 'O check-out faz-se na Caixa, com o pagamento'}>
                        <button
                          onClick={() => onPayStay(b.stay_account_id)}
                          disabled={!onPayStay || !can('open_accounts:close')}
                          className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <CheckCircle2 size={13} />
                          Check-out
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => handleCheckOut(b.id)}
                        disabled={!can('hotel:checkout')}
                        className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <CheckCircle2 size={13} />
                        {b.invoice_id ? 'Saída' : 'Check-out'}
                      </button>
                    )}
                  </>
                ) : (b.status === 'PENDENTE' || b.status === 'CONFIRMADA') ? (
                  <>
                    <button
                      onClick={() => openEditForm(b)}
                      disabled={!can('bookings:update')}
                      className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <Pencil size={12} />
                      Editar
                    </button>
                    {hasStay ? (
                      <button
                        onClick={() => handleCheckIn(b.id)}
                        className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <CheckCircle2 size={13} />
                        Check-in
                      </button>
                    ) : isPriced(b) && (
                      <span title={!posId ? 'Cobra-se na Caixa, no painel Reservas' : isLaterDay(b) ? 'Cobra-se no próprio dia (' + formatDayLabel(luandaDateParts(b.starts_at).date) + ')' : 'Receber o serviço e concluir a reserva'}>
                        <button
                          onClick={() => openCharge(b)}
                          disabled={!posId || !can('bookings:charge') || isLaterDay(b)}
                          className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          <Banknote size={13} />
                          Cobrar
                        </button>
                      </span>
                    )}
                    {can('bookings:update') && (
                    <Select
                      value=""
                      onChange={(v) => handleStatusChange(b.id, v)}
                      // a priced booking is concluded by its payment (Cobrar, or the stay's check-out), never by hand
                      options={Object.entries(STATUS_LABELS).filter(([k]) => k !== b.status && k !== 'EM_CURSO' && !(k === 'CONCLUIDA' && isPriced(b))).map(([k, label]) => ({ value: k, label }))}
                      placeholder="Alterar estado"
                    />
                    )}
                  </>
                ) : (
                  <span className="text-text-muted text-[11px] italic">{b.status === 'CANCELADA' && b.invoice_id && !hasStay ? 'Anulada por nota de crédito' : 'Estado final'}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={walkInOpen} onClose={() => setWalkInOpen(false)} title="Entrada - passagem paga" maxWidthClass="max-w-xl">
        <form onSubmit={handleWalkInSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Quarto livre *</label>
              <Select
                value={walkInForm.resourceId}
                onChange={(v) => { setWalkInForm((p) => ({ ...p, resourceId: v, serviceId: '' })); setWalkInPayments({}); }}
                options={walkInRooms.map((r) => ({ value: r.resource_id, label: r.name }))}
                placeholder={walkInRooms.length ? 'Selecionar' : 'Nenhum quarto livre'}
              />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Serviço *</label>
              <Select
                value={walkInForm.serviceId}
                onChange={chooseWalkInService}
                options={walkInServices.map((s) => ({ value: s.id, label: s.name + ' (' + s.duration_minutes + ' min)' }))}
                placeholder={walkInForm.resourceId ? 'Selecionar' : 'Escolha o quarto'}
              />
            </div>
          </div>
          {renderInvoiceCustomer()}
          <div className="grid grid-cols-4 gap-3">
            <div className="col-span-3">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome do hóspede (opcional)</label>
              <input value={walkInForm.guestName} onChange={(e) => setWalkInForm((p) => ({ ...p, guestName: e.target.value }))} maxLength={150} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">N.º de pessoas</label>
              <input type="number" min="1" step="1" value={walkInForm.partySize} onChange={(e) => setWalkInForm((p) => ({ ...p, partySize: e.target.value }))} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
          </div>
          {walkInService && renderPayment('Total a pagar (IVA incluído) - até ' + new Date(Date.now() + walkInService.duration_minutes * 60000).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Luanda' }))}
          {walkInError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{walkInError}</div>
          )}
          <button type="submit" disabled={walkInSaving || !walkInService || walkInTotal <= 0 || walkInRemaining !== 0} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
            {walkInSaving ? <Loader2 size={17} className="animate-spin" /> : <DoorOpen size={17} />}
            {walkInSaving ? 'A registar...' : 'Receber e dar entrada'}
          </button>
        </form>
      </Modal>

      <Modal open={!!chargeTarget} onClose={() => setChargeTarget(null)} title={'Cobrar' + (chargeTarget ? ' - ' + resourceName(chargeTarget.resource_id) : '')} maxWidthClass="max-w-xl">
        {chargeTarget && (
          <form onSubmit={handleChargeSubmit} className="flex flex-col gap-4">
            <div className="text-[13px] text-text-primary">
              <p className="font-medium">{chargeService?.name || '-'}{saleQuantity > 1 ? ' × ' + saleQuantity : ''}</p>
              <p className="text-text-muted font-mono text-[12px] mt-0.5">{formatDateTime(chargeTarget.starts_at)} - {formatDateTime(chargeTarget.ends_at)}{chargeTarget.guest_name ? ' - ' + chargeTarget.guest_name : ''}</p>
            </div>
            {renderInvoiceCustomer()}
            {chargeService && renderPayment('Total a pagar (IVA incluído)')}
            {walkInError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{walkInError}</div>
            )}
            <button type="submit" disabled={walkInSaving || !chargeService || walkInTotal <= 0 || walkInRemaining !== 0} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
              {walkInSaving ? <Loader2 size={17} className="animate-spin" /> : <Banknote size={17} />}
              {walkInSaving ? 'A cobrar...' : 'Receber e concluir'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={!!extendBooking} onClose={() => setExtendBooking(null)} title={'Prolongar estadia' + (extendBooking ? ' - ' + resourceName(extendBooking.resource_id) : '')} maxWidthClass="max-w-md">
        {extendBooking && (
          <form onSubmit={handleExtendSubmit} className="flex flex-col gap-4">
            <p className="text-text-muted text-[13px]">Entrada {formatDateTime(extendBooking.starts_at)} - saída prevista {formatDateTime(extendBooking.ends_at)}. A diária da conta segue a nova data.</p>
            <div className="flex gap-3">
              <div className="flex-1">
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nova data de saída *</label>
                <DateInput value={extendForm.date} onChange={(e) => setExtendForm((p) => ({ ...p, date: e.target.value }))} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
              </div>
              <div className="w-36">
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Hora *</label>
                <input type="time" value={extendForm.time} onChange={(e) => setExtendForm((p) => ({ ...p, time: e.target.value }))} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
              </div>
            </div>
            {extendError && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{extendError}</div>
            )}
            <button type="submit" disabled={extendSaving} className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer">
              {extendSaving ? <Loader2 size={17} className="animate-spin" /> : <CalendarClock size={17} />}
              {extendSaving ? 'A guardar...' : 'Prolongar'}
            </button>
          </form>
        )}
      </Modal>

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={editingBookingId ? "Editar reserva" : "Nova reserva"} maxWidthClass="max-w-2xl">
        {/* A 4-column grid: the dates and hours are narrow (each as wide as N.º de pessoas), 4 on one line; the
            service, the guest and the notes take the whole width. */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-4 gap-3">
            {!editingBookingId && (
              <div>
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Atividade *</label>
                <Select
                  value={form.activityId}
                  onChange={(v) => setForm((p) => ({ ...p, activityId: v, resourceId: '' }))}
                  options={activities.map((a) => ({ value: a.id, label: a.name }))}
                  placeholder="Selecionar"
                />
              </div>
            )}
            <div className={editingBookingId ? 'col-span-3' : 'col-span-2'}>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Recurso *</label>
              <Select
                value={form.resourceId}
                onChange={handleResourceChange}
                options={(editingBookingId ? resources : formResources).map((r) => ({ value: r.id, label: r.name }))}
                placeholder="Selecionar"
              />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">N.º de pessoas</label>
              <input type="number" min="1" step="1" value={form.partySize} onChange={(e) => setForm((p) => ({ ...p, partySize: e.target.value }))} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
          </div>
          {(() => {
            const res = (editingBookingId ? resources : formResources).find((r) => r.id === form.resourceId);
            const pax = parseInt(form.partySize, 10);
            return res?.capacity && pax > res.capacity ? (
              <p className="text-accent text-[12px] -mt-2">Aviso: este recurso tem capacidade para {res.capacity} pessoas</p>
            ) : null;
          })()}
          <div className="grid grid-cols-4 gap-3">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data início *</label>
              <DateInput
                value={form.date}
                min={editingBookingId ? undefined : todayIso()}
                onChange={(e) => {
                  const newDate = e.target.value;
                  setForm((p) => withAutoEnd({ ...p, date: newDate, endDate: p.endDate < newDate ? newDate : p.endDate }));
                }}
                required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
              />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Hora entrada *</label>
              <input type="time" value={form.startTime} onChange={(e) => setForm((p) => withAutoEnd({ ...p, startTime: e.target.value }))} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data fim *</label>
              <DateInput value={form.endDate} min={form.date || undefined} onChange={(e) => setForm((p) => ({ ...p, endDate: e.target.value, endTouched: true }))} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Hora saída *</label>
              <input type="time" value={form.endTime} onChange={(e) => setForm((p) => ({ ...p, endTime: e.target.value, endTouched: true }))} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">
              Serviço{selectedResourceType?.requires_service ? ' *' : ' (opcional)'}
            </label>
            <Select
              value={form.serviceId}
              onChange={(v) => setForm((p) => withAutoEnd({ ...p, serviceId: v }))}
              options={availableServices.map((s) => ({ value: s.id, label: s.name + (s.duration_minutes ? ' (' + s.duration_minutes + ' min)' : '') }))}
              placeholder="Nenhum"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">{personWord === 'hóspede' ? 'Hóspede' : 'Cliente'} (opcional)</label>
            <div className="flex items-center gap-1.5">
              <div className="flex-1">
                <Select
                  value={form.customerId}
                  onChange={(v) => setForm((p) => ({ ...p, customerId: v }))}
                  options={customers.map((c) => ({ value: c.id, label: c.name }))}
                  placeholder="Cliente (opcional)"
                />
              </div>
              <button type="button" onClick={openCustomerModal} disabled={!can('customers:create')} className="flex items-center justify-center w-10 h-10 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer shrink-0 disabled:opacity-40 disabled:cursor-not-allowed">
                <Plus size={15} />
              </button>
            </div>
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome do {personWord} (opcional)</label>
            <input value={form.guestName} onChange={(e) => setForm((p) => ({ ...p, guestName: e.target.value }))} maxLength={150} placeholder="Ex: Família Silva" className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Notas (opcional)</label>
            <input value={form.notes} onChange={(e) => setForm((p) => ({ ...p, notes: e.target.value }))} className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
          {formError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{formError}</div>
          )}
          <button
            type="submit"
            disabled={saving}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {saving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {saving ? (editingBookingId ? 'A guardar...' : 'A criar...') : (editingBookingId ? 'Guardar alterações' : 'Criar reserva')}
          </button>
        </form>
      </Modal>
      <Modal open={posPickerOpen} onClose={() => setPosPickerOpen(false)} title="Selecionar ponto de venda">
        <div className="flex flex-col gap-4">
          <p className="text-text-muted text-[13px]">
            Existe mais de uma caixa aberta para esta atividade - indique qual usar para faturar esta estadia.
          </p>
          {posPickerOptions.length === 0 ? (
            <p className="text-text-muted text-[13px] text-center py-4">A carregar pontos de venda...</p>
          ) : (
            <Select
              value={posPickerSelected}
              onChange={setPosPickerSelected}
              options={posPickerOptions.map((p) => ({ value: p.id, label: p.name }))}
              placeholder="Selecionar"
            />
          )}
          {posPickerError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{posPickerError}</div>
          )}
          <button
            onClick={handlePosPickerConfirm}
            disabled={posPickerSaving || !posPickerSelected}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {posPickerSaving ? <Loader2 size={17} className="animate-spin" /> : <CheckCircle2 size={17} />}
            {posPickerSaving ? 'A fazer check-in...' : 'Confirmar check-in'}
          </button>
        </div>
      </Modal>
      <Modal open={customerModalOpen} onClose={() => setCustomerModalOpen(false)} title="Novo cliente">
        <form onSubmit={handleCustomerSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Nome *</label>
            <input value={customerForm.name} onChange={(e) => setCustomerForm((p) => ({ ...p, name: e.target.value }))} required autoFocus className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Telefone *</label>
            <input value={customerForm.phoneNumber} onChange={(e) => setCustomerForm((p) => ({ ...p, phoneNumber: e.target.value }))} required placeholder="+244..." className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">NIF (opcional)</label>
            <input value={customerForm.nif} onChange={(e) => setCustomerForm((p) => ({ ...p, nif: e.target.value, legalPersonType: p.typeTouched ? p.legalPersonType : guessLegalPersonType(e.target.value) }))} placeholder="Deixe vazio para consumidor final" className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
          {customerForm.nif.trim() && (
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Tipo *</label>
              <Select value={customerForm.legalPersonType} onChange={(v) => setCustomerForm((p) => ({ ...p, legalPersonType: v, typeTouched: true }))} options={LEGAL_PERSON_OPTIONS} />
            </div>
          )}
          {customerFormError && (
            <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{customerFormError}</div>
          )}
          <button
            type="submit"
            disabled={customerSaving}
            className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors cursor-pointer"
          >
            {customerSaving ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
            {customerSaving ? 'A criar...' : 'Criar cliente'}
          </button>
        </form>
      </Modal>
    </div>
  );
}

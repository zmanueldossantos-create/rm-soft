import { useState, useEffect } from 'react';
import { CalendarClock, Plus, Loader2, X, CheckCircle2, Pencil } from 'lucide-react';
import { listActivities } from '../api/activity';
import { listResources, listBookings, createBooking, updateBookingStatus, rescheduleBooking } from '../api/booking';
import { listPointsOfSale } from '../api/activity';
import { listResourceTypes } from '../api/booking';
import { listCustomers, createCustomer } from '../api/customers';
import { checkIn, checkOut } from '../api/hotel';
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

export default function Reservas() {
  const [activities, setActivities] = useState([]);
  const [selectedActivityId, setSelectedActivityId] = useState('');
  const [resources, setResources] = useState([]);
  const [services, setServices] = useState([]);
  const [resourceTypesCatalog, setResourceTypesCatalog] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [customerModalOpen, setCustomerModalOpen] = useState(false);
  const [customerForm, setCustomerForm] = useState({ name: '', phoneNumber: '', nif: '' });
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
  const [form, setForm] = useState({ activityId: '', resourceId: '', serviceId: '', customerId: '', date: todayIso(), endDate: todayIso(), startTime: '14:00', endTime: '12:00', notes: '' });
  const [formResources, setFormResources] = useState([]);
  const [editingBookingId, setEditingBookingId] = useState(null);
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    listActivities().then((data) => {
      const active = data.filter((a) => a.is_active);
      setActivities(active);
      if (active.length > 0) setSelectedActivityId(active[0].id);
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
    setForm({ activityId: selectedActivityId, resourceId: '', serviceId: '', customerId: '', date: today, endDate: today, startTime: '14:00', endTime: '12:00', notes: '' });
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
    });
    setFormError('');
    setFormOpen(true);
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
    if (selectedResourceType?.requires_service && !form.serviceId) {
      setFormError(`Este tipo de recurso (${selectedResourceType.name}) exige um servico associado a reserva`);
      return;
    }
    setSaving(true);
    try {
      const startsAt = form.date + 'T' + form.startTime + ':00';
      const endsAt = form.endDate + 'T' + form.endTime + ':00';
      if (editingBookingId) {
        await rescheduleBooking(editingBookingId, startsAt, endsAt, form.serviceId || null, form.notes || null, form.customerId || null);
      } else {
        await createBooking({
          resource_id: form.resourceId,
          service_id: form.serviceId || null,
          customer_id: form.customerId || null,
          starts_at: startsAt,
          ends_at: endsAt,
          notes: form.notes || null,
        });
      }
      setFormOpen(false);
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
      await checkIn(bookingId);
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

  function openCustomerModal() {
    setCustomerForm({ name: '', phoneNumber: '', nif: '' });
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
      });
      setCustomers((prev) => [...prev, created]);
      setForm((p) => ({ ...p, customerId: created.id }));
      setCustomerModalOpen(false);
    } catch (err) {
      setCustomerFormError(extractErrorMessage(err, 'Erro ao criar cliente'));
    } finally {
      setCustomerSaving(false);
    }
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

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5">
          <CalendarClock size={22} className="text-accent" />
          Reservas
        </h2>
        <button
          onClick={openCreateForm}
          disabled={resources.length === 0}
          className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white font-medium text-sm px-4 py-2 rounded-md transition-colors cursor-pointer"
        >
          <Plus size={16} />
          Nova reserva
        </button>
      </div>
      <p className="text-text-muted text-sm mb-6">Gerir reservas de quartos, praticiens, mesas ou qualquer outro recurso</p>

      {activities.length > 1 && (
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
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">De</label>
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
        </div>
        <div>
          <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Ate</label>
          <input type="date" value={dateTo} min={dateFrom || undefined} onChange={(e) => setDateTo(e.target.value)} className="bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
        </div>
      </div>

      {error && (
        <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r mb-4">{error}</div>
      )}

      {loading ? (
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
                {b.notes && <p className="text-text-muted text-[12px] mt-0.5">{b.notes}</p>}
              </div>
              <div className="flex items-center gap-2">
                <span className={'text-[11px] font-semibold px-2.5 py-1 rounded-full ' + (STATUS_COLORS[b.status] || '')}>{STATUS_LABELS[b.status] || b.status}</span>
                {checkActionId === b.id || statusUpdatingId === b.id ? (
                  <Loader2 size={16} className="animate-spin text-accent" />
                ) : b.status === 'EM_CURSO' ? (
                  <button
                    onClick={() => handleCheckOut(b.id)}
                    className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors cursor-pointer"
                  >
                    <CheckCircle2 size={13} />
                    Check-out
                  </button>
                ) : (b.status === 'PENDENTE' || b.status === 'CONFIRMADA') ? (
                  <>
                    <button
                      onClick={() => openEditForm(b)}
                      className="flex items-center gap-1.5 border border-border hover:border-accent text-text-primary text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors cursor-pointer"
                    >
                      <Pencil size={12} />
                      Editar
                    </button>
                    <button
                      onClick={() => handleCheckIn(b.id)}
                      className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white text-[12px] font-medium px-3 py-1.5 rounded-md transition-colors cursor-pointer"
                    >
                      <CheckCircle2 size={13} />
                      Check-in
                    </button>
                    <Select
                      value=""
                      onChange={(v) => handleStatusChange(b.id, v)}
                      options={Object.entries(STATUS_LABELS).filter(([k]) => k !== b.status && k !== 'EM_CURSO').map(([k, label]) => ({ value: k, label }))}
                      placeholder="Alterar estado"
                    />
                  </>
                ) : (
                  <span className="text-text-muted text-[11px] italic">Estado final</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={editingBookingId ? "Editar reserva" : "Nova reserva"} maxWidthClass="max-w-xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex gap-3">
            {!editingBookingId && (
              <div className="flex-1">
                <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Atividade *</label>
                <Select
                  value={form.activityId}
                  onChange={(v) => setForm((p) => ({ ...p, activityId: v, resourceId: '' }))}
                  options={activities.map((a) => ({ value: a.id, label: a.name }))}
                  placeholder="Selecionar atividade"
                />
              </div>
            )}
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Recurso *</label>
              <Select
                value={form.resourceId}
                onChange={(v) => setForm((p) => ({ ...p, resourceId: v }))}
                options={(editingBookingId ? resources : formResources).map((r) => ({ value: r.id, label: r.name }))}
                placeholder="Selecionar"
              />
            </div>
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data inicio *</label>
              <input
                type="date" value={form.date}
                min={editingBookingId ? undefined : todayIso()}
                onChange={(e) => {
                  const newDate = e.target.value;
                  setForm((p) => ({ ...p, date: newDate, endDate: p.endDate < newDate ? newDate : p.endDate }));
                }}
                required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors"
              />
            </div>
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Data fim *</label>
              <input type="date" value={form.endDate} min={form.date || undefined} onChange={(e) => setForm((p) => ({ ...p, endDate: e.target.value }))} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Hora de entrada (no dia de inicio) *</label>
              <input type="time" value={form.startTime} onChange={(e) => setForm((p) => ({ ...p, startTime: e.target.value }))} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
            <div className="flex-1">
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Hora de saida (no dia de fim) *</label>
              <input type="time" value={form.endTime} onChange={(e) => setForm((p) => ({ ...p, endTime: e.target.value }))} required className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
            </div>
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">
              Servico{selectedResourceType?.requires_service ? ' *' : ' (opcional)'}
            </label>
            <Select
              value={form.serviceId}
              onChange={(v) => setForm((p) => ({ ...p, serviceId: v }))}
              options={availableServices.map((s) => ({ value: s.id, label: s.name }))}
              placeholder="Nenhum"
            />
          </div>
          <div>
            <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Hospede (opcional)</label>
            <div className="flex items-center gap-1.5">
              <div className="flex-1">
                <Select
                  value={form.customerId}
                  onChange={(v) => setForm((p) => ({ ...p, customerId: v }))}
                  options={customers.map((c) => ({ value: c.id, label: c.name }))}
                  placeholder="Cliente (opcional)"
                />
              </div>
              <button type="button" onClick={openCustomerModal} className="flex items-center justify-center w-10 h-10 rounded-md border border-border text-text-muted hover:text-accent hover:border-accent transition-colors cursor-pointer shrink-0">
                <Plus size={15} />
              </button>
            </div>
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
            {saving ? (editingBookingId ? 'A guardar...' : 'A criar...') : (editingBookingId ? 'Guardar alteracoes' : 'Criar reserva')}
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
            <input value={customerForm.nif} onChange={(e) => setCustomerForm((p) => ({ ...p, nif: e.target.value }))} placeholder="Deixe vazio para consumidor final" className="w-full bg-bg-inset border border-border rounded-md px-3.5 py-2.5 text-sm text-text-primary outline-none focus:border-accent transition-colors" />
          </div>
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
    </main>
  );
}

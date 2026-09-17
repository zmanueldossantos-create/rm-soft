import apiClient from './client';

// ---------- Resource types (managed catalog: Chambre, Praticien, Mesa...) ----------

export async function listResourceTypes() {
  const res = await apiClient.get('/resource-types');
  return res.data;
}

export async function createResourceType(name, requiresService = false) {
  const res = await apiClient.post('/resource-types', { name, requires_service: requiresService });
  return res.data;
}

export async function updateResourceType(resourceTypeId, name, requiresService = false) {
  const res = await apiClient.patch('/resource-types/' + resourceTypeId, { name, requires_service: requiresService });
  return res.data;
}

export async function toggleResourceTypeStatus(resourceTypeId) {
  const res = await apiClient.post('/resource-types/' + resourceTypeId + '/toggle');
  return res.data;
}

// ---------- Resources (generic bookable "thing" - room, therapist, table...) ----------

export async function listResources(activityId = null, resourceType = null) {
  const params = {};
  if (activityId) params.activity_id = activityId;
  if (resourceType) params.resource_type = resourceType;
  const res = await apiClient.get('/resources', { params });
  return res.data;
}

export async function createResource(activityId, resourceTypeId, name, capacity = null) {
  const res = await apiClient.post('/resources', { activity_id: activityId, resource_type_id: resourceTypeId, name, capacity });
  return res.data;
}

export async function updateResource(resourceId, name, capacity = null) {
  const res = await apiClient.patch('/resources/' + resourceId, { name, capacity });
  return res.data;
}

export async function toggleResourceStatus(resourceId) {
  const res = await apiClient.post('/resources/' + resourceId + '/toggle');
  return res.data;
}

// ---------- Bookings (reservation of a Resource for a time span) ----------

export async function listBookings(filters = {}) {
  const params = {};
  if (filters.resourceId) params.resource_id = filters.resourceId;
  if (filters.dateFrom) params.date_from = filters.dateFrom;
  if (filters.dateTo) params.date_to = filters.dateTo;
  const res = await apiClient.get('/bookings', { params });
  return res.data;
}

export async function createBooking(payload) {
  const res = await apiClient.post('/bookings', payload);
  return res.data;
}

export async function updateBookingStatus(bookingId, newStatus) {
  const res = await apiClient.patch('/bookings/' + bookingId + '/status', { status: newStatus });
  return res.data;
}

export async function rescheduleBooking(bookingId, startsAt, endsAt, serviceId = null, notes = null, customerId = null) {
  const res = await apiClient.patch('/bookings/' + bookingId + '/reschedule', { starts_at: startsAt, ends_at: endsAt, service_id: serviceId, notes, customer_id: customerId });
  return res.data;
}

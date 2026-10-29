import apiClient from './client';

// Faturação Eletrónica (AGT).
// The company (Definições da Empresa, the gestor): the taxpayer's key, the connection test, the journal of the calls.
export async function getCompanyAgt() {
  return (await apiClient.get('/company/me/agt')).data;
}

// privateKey '' removes the key; the key is never sent back (only its size and fingerprint)
export async function saveCompanyAgtKey(privateKey) {
  return (await apiClient.put('/company/me/agt/key', { private_key: privateKey })).data;
}

export async function testCompanyAgt() {
  return (await apiClient.post('/company/me/agt/test')).data;
}

export async function getCompanyAgtCalls(limit = 30) {
  return (await apiClient.get('/company/me/agt/calls', { params: { limit } })).data;
}

// The platform (Configurações, SUPER_ADMIN): environment, producer's access, software identity and signature.
export async function getAgtSettings() {
  return (await apiClient.get('/admin/agt-settings')).data;
}

// password / softwareKey: null keeps the saved one, '' removes it
export async function updateAgtSettings(data) {
  return (await apiClient.put('/admin/agt-settings', {
    environment: data.environment,
    username: data.username || null,
    password: data.password,
    product_id: data.productId || null,
    signature_version: data.signatureVersion === '' || data.signatureVersion == null ? null : Number(data.signatureVersion),
    software_key: data.softwareKey,
    software_signature: data.softwareSignature,
    qr_url: data.qrUrl == null ? null : data.qrUrl.trim(),  // '' back to the default
  })).data;
}

export async function generateAgtSoftwareKey(replace = false) {
  return (await apiClient.post('/admin/agt-settings/software-key', null, { params: { replace } })).data;
}

// Homologação: send as one of the AGT's test NIFs (null: the company's own NIF)
export async function setCompanyAgtTestNif(nif) {
  return (await apiClient.put('/company/me/agt/test-nif', { nif: nif || null })).data;
}

// The AGT's test NIFs (SUPER_ADMIN): imported from the TEST_NIF file, keys kept encrypted and never sent back
export async function getAgtTestTaxpayers() {
  return (await apiClient.get('/admin/agt-test-taxpayers')).data;
}

export async function importAgtTestTaxpayers(text) {
  return (await apiClient.post('/admin/agt-test-taxpayers/import', { text })).data;
}

export async function deleteAgtTestTaxpayer(nif) {
  return (await apiClient.delete('/admin/agt-test-taxpayers/' + encodeURIComponent(nif))).data;
}

// Contingência: the gestor's switch (on until he switches it off)
export async function setCompanyAgtContingency(on) {
  return (await apiClient.post('/company/me/agt/contingency', { on })).data;
}

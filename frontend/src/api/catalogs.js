// API calls for the 8 platform-wide base catalogs (SUPER_ADMIN only).
import apiClient from './client';

function makeCatalogApi(basePath) {
  return {
    list: async (params) => (await apiClient.get('/catalogs/' + basePath, { params })).data,
    create: async (payload) => (await apiClient.post('/catalogs/' + basePath, payload)).data,
    update: async (id, payload) => (await apiClient.patch('/catalogs/' + basePath + '/' + id, payload)).data,
    toggle: async (id) => (await apiClient.patch('/catalogs/' + basePath + '/' + id + '/toggle-status')).data,
  };
}

export const countriesApi = makeCatalogApi('countries');
export const currenciesApi = makeCatalogApi('currencies');
export const provincesApi = makeCatalogApi('provinces');
export const municipalitiesApi = makeCatalogApi('municipalities');
export const banksApi = makeCatalogApi('banks');
export const paymentMethodsApi = makeCatalogApi('payment-methods');
export const paymentTermsApi = makeCatalogApi('payment-terms');
export const vatCodesApi = makeCatalogApi('vat-codes');

export const documentTypesApi = makeCatalogApi('document-types');
export const unitsApi = makeCatalogApi('units');
export const withholdingTaxesApi = makeCatalogApi('withholding-taxes');
export const movementTypesApi = makeCatalogApi('movement-types');
export const denominationsApi = makeCatalogApi('denominations');

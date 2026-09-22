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

// Document types with their rules, readable by every signed-in user (the screens decide what they offer from them).
// One shared request for all the screens, renewed after a minute (the super admin may change a rule).
let rulesCache = { at: 0, promise: null };
export const documentRulesApi = {
  list: () => {
    if (!rulesCache.promise || Date.now() - rulesCache.at > 60000) {
      const promise = apiClient.get('/catalogs/document-rules').then((res) => res.data).then(async (rules) => {
        // Overlay this company's own requires_payment_term choice on top of the platform default (absence of
        // access to that route - most roles - just keeps the platform default, same graceful fallback as elsewhere).
        let prefs = [];
        try {
          prefs = (await apiClient.get('/tesouraria/document-type-payment-term-preferences')).data;
        } catch (err) {
          return rules;
        }
        const prefByTypeId = Object.fromEntries(prefs.map((p) => [p.id, p.requires_payment_term]));
        return rules.map((r) => (r.id in prefByTypeId ? { ...r, requires_payment_term: prefByTypeId[r.id] } : r));
      });
      rulesCache = { at: Date.now(), promise };
      promise.catch(() => { if (rulesCache.promise === promise) rulesCache = { at: 0, promise: null }; });
    }
    return rulesCache.promise;
  },
};
export const unitsApi = makeCatalogApi('units');
export const withholdingTaxesApi = makeCatalogApi('withholding-taxes');
export const movementTypesApi = makeCatalogApi('movement-types');
export const denominationsApi = makeCatalogApi('denominations');

// Marca do software: the name and logo the users of this installation see (SUPER_ADMIN, Configurações → Sistema).
// Read once at start-up (public: the login screen needs it); the tab's title and icon follow it.
import { create } from 'zustand';
import apiClient from '../api/client';
import { API_ORIGIN } from '../api/config';

const DEFAULT = { name: 'RM SOFT', logo_path: null, header: 'NOME', vendor: null, custom: false };

function applyToDocument(brand) {
  document.title = brand.custom ? brand.name : 'RM SOFT - Software de Gestão';
  if (brand.logo_path) {
    document.querySelectorAll('link[rel~="icon"], link[rel="apple-touch-icon"]').forEach((link) => {
      link.removeAttribute('type');
      link.removeAttribute('sizes');
      link.href = API_ORIGIN + brand.logo_path;
    });
  }
}

export const useBrandStore = create((set) => ({
  ...DEFAULT,
  load: async () => {
    try {
      const brand = { ...DEFAULT, ...(await apiClient.get('/auth/branding')).data };
      applyToDocument(brand);
      set(brand);
    } catch {
      // server unreachable: RM SOFT until the next load
    }
  },
  // after a change in Configurações: every screen follows at once
  apply: (data) => {
    const brand = { ...DEFAULT, ...data };
    applyToDocument(brand);
    set(brand);
  },
}));

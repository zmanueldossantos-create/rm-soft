// Zustand store - authentication state.
// Persists tokens to localStorage so the session survives a page reload.
import { create } from 'zustand';

const STORAGE_KEY = 'erp_auth';

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveToStorage(data) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
}

function clearStorage() {
  localStorage.removeItem(STORAGE_KEY);
}

const stored = loadFromStorage();

export const useAuthStore = create((set) => ({
  accessToken: stored?.accessToken || null,
  refreshToken: stored?.refreshToken || null,
  user: stored?.user || null,
  isAuthenticated: !!stored?.accessToken,
  // Permission codes of the logged-in user (from /permissions/mine); null = not loaded yet.
  permissions: null,

  login: (accessToken, refreshToken, user) => {
    saveToStorage({ accessToken, refreshToken, user });
    set({ accessToken, refreshToken, user, isAuthenticated: true });
  },

  logout: () => {
    clearStorage();
    set({ accessToken: null, refreshToken: null, user: null, isAuthenticated: false, permissions: null });
  },

  setUser: (user) => {
    set((state) => {
      const updated = { ...state, user };
      saveToStorage({ accessToken: state.accessToken, refreshToken: state.refreshToken, user });
      return { user };
    });
  },

  setPermissions: (permissions) => set({ permissions }),
}));

// The toasts (top right): successes, errors, information - from any screen, and from the API client for the server's
// errors. One message shown once: the same text again restarts its toast instead of stacking a copy.
import { create } from 'zustand';

const DURATION = { success: 4000, info: 5000, error: 7000 };
const MAX = 4;
let next = 1;

export const useToastStore = create((set) => ({
  toasts: [],
  push: (type, message) => {
    const text = typeof message === 'string' ? message.trim() : '';
    if (!text) return;
    set((state) => {
      const others = state.toasts.filter((t) => !(t.type === type && t.message === text));
      const toast = { id: next++, type, message: text, duration: DURATION[type] || 5000 };
      return { toasts: [...others, toast].slice(-MAX) };
    });
  },
  remove: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));

// toast.success('Produto guardado'), toast.error(message), toast.info(message) - anywhere, outside React too
export const toast = {
  success: (message) => useToastStore.getState().push('success', message),
  error: (message) => useToastStore.getState().push('error', message),
  info: (message) => useToastStore.getState().push('info', message),
};

// The PDF preview opened from code that has no screen of its own (an API helper): one viewer for the whole app,
// mounted in App - the same «Imprimir» / «Guardar» (a real file name) as every page's preview.
import { create } from 'zustand';

export const usePdfViewerStore = create((set, get) => ({
  doc: null,  // { url, title, fileName }
  open: (doc) => {
    const previous = get().doc;
    if (previous?.url) URL.revokeObjectURL(previous.url);
    set({ doc });
  },
  close: () => {
    const doc = get().doc;
    if (doc?.url) URL.revokeObjectURL(doc.url);
    set({ doc: null });
  },
}));

export const openPdf = (doc) => usePdfViewerStore.getState().open(doc);

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';

// stacked: this modal opens on top of another already-open one (e.g. Liquidar pro-forma over Consultar
// documentos) - higher z-index, and no own backdrop since the modal underneath already dims the page.
// variant="drawer": slides in from the left between the navbar (h-14) and the footer (h-11), starting after a page
// sidebar (drawerLeftClass, e.g. "left-16" at the Caixa); on close it slides back out before being removed.
const DRAWER_OUT_MS = 220;

export default function Modal({
  open, onClose, title, subtitle, children, footer, maxWidthClass = 'max-w-md', stacked = false,
  variant = 'center', drawerLeftClass = 'left-0',
}) {
  const isDrawer = variant === 'drawer';
  const [rendered, setRendered] = useState(open);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (open) {
      setRendered(true);
      setLeaving(false);
      return undefined;
    }
    if (!isDrawer || !rendered) {
      setRendered(false);
      return undefined;
    }
    setLeaving(true);
    const timer = setTimeout(() => {
      setRendered(false);
      setLeaving(false);
    }, DRAWER_OUT_MS);
    return () => clearTimeout(timer);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!rendered && !open) return null;

  const header = (
    <div className="flex items-center justify-between px-6 py-4 border-b border-border shrink-0">
      <div>
        <h3 className="font-display font-semibold text-[15px] text-text-primary">
          {title}
        </h3>
        {subtitle && <p className="text-[12px] text-text-muted mt-0.5">{subtitle}</p>}
      </div>
      <button
        onClick={onClose}
        className="text-text-muted hover:text-text-primary transition-colors cursor-pointer"
        aria-label="Fechar"
      >
        <X size={20} />
      </button>
    </div>
  );
  const body = <div className="px-6 py-5 overflow-y-auto scrollbar-thin flex-1 min-h-0">{children}</div>;
  const foot = footer && <div className="border-t border-border shrink-0">{footer}</div>;

  if (isDrawer) {
    return (
      <div className={'fixed top-14 bottom-11 right-0 z-30 ' + drawerLeftClass}>
        <div className={'absolute inset-0 bg-black/40 ' + (leaving ? 'animate-fade-out' : 'animate-fade-in')} onClick={onClose} />
        <div className={'relative h-full w-full bg-bg-elevated border-r border-border shadow-2xl flex flex-col ' + (leaving ? 'animate-drawer-out ' : 'animate-drawer-in ') + maxWidthClass}>
          {header}
          {body}
          {foot}
        </div>
      </div>
    );
  }

  if (!open) return null;
  return (
    <div className={'fixed inset-0 flex items-center justify-center p-4 ' + (stacked ? 'z-[60]' : 'z-50')}>
      {!stacked && (
        <div
          className="absolute inset-0 bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        />
      )}
      {stacked && <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />}
      <div className={'relative bg-bg-elevated border border-border rounded-lg w-full shadow-2xl flex flex-col max-h-[90vh] ' + maxWidthClass}>
        {header}
        {body}
        {foot}
      </div>
    </div>
  );
}

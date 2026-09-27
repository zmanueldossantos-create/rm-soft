import { X } from 'lucide-react';

// stacked: this modal opens on top of another already-open one (e.g. Liquidar pro-forma over Consultar
// documentos) - higher z-index, and no own backdrop since the modal underneath already dims the page.
export default function Modal({ open, onClose, title, subtitle, children, footer, maxWidthClass = 'max-w-md', stacked = false }) {
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
        <div className="px-6 py-5 overflow-y-auto scrollbar-thin flex-1 min-h-0">{children}</div>
        {footer && <div className="border-t border-border shrink-0">{footer}</div>}
      </div>
    </div>
  );
}

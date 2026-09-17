import { AlertTriangle } from 'lucide-react';

export default function ConfirmDialog({ open, onConfirm, onCancel, title, message, confirmLabel = 'Confirmar', danger = false }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-bg-elevated border border-border rounded-lg w-full max-w-sm shadow-2xl p-6">
        <div className="flex items-start gap-3 mb-4">
          <div className={'w-9 h-9 rounded-full flex items-center justify-center shrink-0 ' + (danger ? 'bg-danger/10' : 'bg-accent/10')}>
            <AlertTriangle size={18} className={danger ? 'text-danger' : 'text-accent'} />
          </div>
          <div>
            <h3 className="font-display font-semibold text-[15px] text-text-primary mb-1">{title}</h3>
            <p className="text-text-muted text-sm">{message}</p>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-text-muted hover:text-text-primary border border-border rounded-md transition-colors cursor-pointer"
          >
            Cancelar
          </button>
          <button
            onClick={onConfirm}
            className={
              'px-4 py-2 text-sm font-semibold text-white rounded-md transition-colors cursor-pointer ' +
              (danger ? 'bg-danger hover:bg-danger/80' : 'bg-accent hover:bg-accent-hover')
            }
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

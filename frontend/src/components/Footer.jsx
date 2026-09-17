import { useAuthStore } from '../store/authStore';

const APP_NAME = 'RM SOFT';
const APP_VERSION = import.meta.env.VITE_APP_VERSION || '1.0.0';

export default function Footer() {
  const user = useAuthStore((state) => state.user);

  return (
    <footer className="fixed bottom-0 inset-x-0 z-40 h-11 bg-bg-elevated border-t border-border px-4 sm:px-7 flex items-center justify-between text-[12px] text-text-muted">
      <span className="truncate">
        {user?.full_name} <span className="text-accent">({user?.role})</span>
      </span>
      <span className="font-mono text-[11px] shrink-0 ml-3">
        {APP_NAME} <span className="text-text-muted/60">v{APP_VERSION}</span>
      </span>
    </footer>
  );
}

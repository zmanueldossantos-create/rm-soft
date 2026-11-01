import UserMenu from './UserMenu';
import { useBrandStore } from '../store/brandStore';

const APP_VERSION = import.meta.env.VITE_APP_VERSION || '1.0.0';

export default function Footer() {
  const brand = useBrandStore();
  return (
    <footer className="fixed bottom-0 inset-x-0 z-40 h-11 bg-bg-elevated border-t border-border px-4 sm:px-7 flex items-center justify-between text-[12px] text-text-muted">
      <UserMenu />
      <span className="font-mono text-[11px] shrink-0 ml-3">
        {brand.name} <span className="text-text-muted/60">v{APP_VERSION}</span>
        {brand.vendor && <span className="text-text-muted/60"> · Desenvolvido por {brand.vendor}</span>}
      </span>
    </footer>
  );
}

import { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useLocation, Outlet } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { Building2, LogOut, LayoutDashboard, Sun, Moon, Package, Users, Calendar, Receipt, Settings, Package2, UserCog, History, FileText, Landmark, LayoutGrid, Store, Wheat, Factory, Wallet, SlidersHorizontal, Tags, Wrench, ChevronDown, Cog, Plus, ArrowLeftRight, Calculator, ClipboardList, Gauge, PiggyBank, CreditCard, Boxes, CalendarClock, Wallet2, PackageMinus } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useThemeStore } from '../store/themeStore';
import { getCurrentPeriod } from '../api/fiscal';
import Footer from './Footer';

function NavLink({ to, icon: Icon, label, active }) {
  return (
    <Link
      to={to}
      className={
        'flex items-center gap-1.5 text-sm font-medium px-3 py-2 rounded-md transition-colors cursor-pointer shrink-0 ' +
        (active
          ? 'text-accent bg-accent/10'
          : 'text-text-muted hover:text-text-primary hover:bg-bg-inset')
      }
    >
      <Icon size={16} />
      <span className="hidden sm:inline">{label}</span>
    </Link>
  );
}

function NavGroup({ icon: Icon, label, items, isActive }) {
  const [open, setOpen] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (
        btnRef.current && !btnRef.current.contains(e.target) &&
        menuRef.current && !menuRef.current.contains(e.target)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  function toggleOpen() {
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      setCoords({ top: rect.bottom + 4, left: rect.left });
    }
    setOpen((prev) => !prev);
  }

  const anyActive = items.some((item) => isActive(item.to));

  return (
    <div className="relative shrink-0">
      <button
        ref={btnRef}
        type="button"
        onClick={toggleOpen}
        className={
          'flex items-center gap-1.5 text-sm font-medium px-3 py-2 rounded-md transition-colors cursor-pointer shrink-0 ' +
          (anyActive ? 'text-accent bg-accent/10' : 'text-text-muted hover:text-text-primary hover:bg-bg-inset')
        }
      >
        <Icon size={16} />
        <span className="hidden sm:inline">{label}</span>
        <ChevronDown size={13} className={'transition-transform ' + (open ? 'rotate-180' : '')} />
      </button>
      {open && createPortal(
        <div
          ref={menuRef}
          style={{ position: 'fixed', top: coords.top, left: coords.left }}
          className="bg-bg-elevated border border-border rounded-md shadow-lg py-1 min-w-[180px] z-[100]"
        >
          {items.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              onClick={() => setOpen(false)}
              className={
                'flex items-center gap-2 px-3.5 py-2.5 text-sm transition-colors ' +
                (isActive(item.to) ? 'text-accent bg-accent/10' : 'text-text-primary hover:bg-bg-inset')
              }
            >
              <item.icon size={15} />
              {item.label}
            </Link>
          ))}
        </div>,
        document.body
      )}
    </div>
  );
}

export default function Layout() {
  const navScrollRef = useRef(null);

  function handleNavWheel(e) {
    // Converts the mouse wheel's vertical scroll into horizontal scroll on
    // this navbar - regular mouse wheels don't scroll horizontal overflow
    // by default, so without this the items past the visible edge (e.g.
    // SAF-T) are unreachable for anyone without a touchpad or Shift+wheel.
    if (e.deltaY === 0) return;
    e.currentTarget.scrollLeft += e.deltaY;
    e.preventDefault();
  }

  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const theme = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const [periodLabel, setPeriodLabel] = useState(null);

  useEffect(() => {
    if (user?.role && user.role !== 'SUPER_ADMIN') {
      getCurrentPeriod()
        .then((data) => setPeriodLabel(data.label))
        .catch(() => setPeriodLabel(null));
    }
  }, [user?.role]);

  function handleLogout() {
    logout();
    navigate('/login');
  }

  function isActive(path) {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  }

  return (
    <div className="min-h-screen bg-bg-primary">
      <nav className="fixed top-0 inset-x-0 z-50 h-14 bg-bg-elevated border-b border-border px-4 sm:px-7 flex items-center gap-3">
        <span className="font-display font-bold text-base text-accent shrink-0">
          RM SOFT
        </span>

        <div className="relative flex-1 min-w-0 h-full">
          <div ref={navScrollRef} onWheel={handleNavWheel} className="flex items-center gap-1 sm:gap-2 overflow-x-auto scrollbar-hover-thin h-full">
            <NavLink to="/dashboard" icon={LayoutDashboard} label="Painel" active={isActive('/dashboard')} />
            {user?.role === 'SUPER_ADMIN' && (
              <NavLink to="/admin/companies" icon={Building2} label="Empresas" active={isActive('/admin/companies')} />
            )}
            {user?.role === 'SUPER_ADMIN' && (
              <NavLink to="/configuracoes" icon={SlidersHorizontal} label="Configurações" active={isActive('/configuracoes')} />
            )}
            {user?.role === 'GESTOR' && (
              <>
                <div className="w-px h-5 bg-border mx-1 shrink-0 self-center" />
                <NavLink to="/products" icon={Package} label="Produtos" active={isActive('/products')} />
                <NavLink to="/services" icon={Wrench} label="Serviços" active={isActive('/services')} />
              </>
            )}
            {user?.role === 'GESTOR' && (
              <NavLink to="/materia-prima" icon={Wheat} label="Matéria-prima" active={isActive('/materia-prima')} />
            )}
            {user?.role === 'GESTOR' && (
              <>
                <NavGroup
                icon={Factory}
                label="Produção"
                isActive={isActive}
                items={[
                  { to: '/producao', icon: Factory, label: 'Produtos configurados' },
                  { to: '/producao/historico', icon: ClipboardList, label: 'Resumo de Produção' },
                ]}
              />
                <div className="w-px h-5 bg-border mx-1 shrink-0 self-center" />
              </>
            )}
            {user?.role === 'GESTOR' && (
              <NavLink to="/customers" icon={Users} label="Clientes" active={isActive('/customers')} />
            )}
            {(user?.role === 'GESTOR' || user?.role === 'CAIXA') && (
              <NavLink to="/caixa" icon={Wallet} label="Caixa" active={isActive('/caixa')} />
            )}
            {(user?.role === 'GESTOR' || user?.role === 'CAIXA') && (
              <NavLink to="/invoices" icon={Receipt} label="Faturas" active={isActive('/invoices')} />
            )}
            {(user?.role === 'GESTOR' || user?.role === 'ARMAZENISTA') && (
              <>
                <div className="w-px h-5 bg-border mx-1 shrink-0 self-center" />
                <NavGroup
                  icon={Package2}
                  label="Gestão de Stocks"
                  isActive={isActive}
                  items={[
                    { to: '/stock/dashboard', icon: Gauge, label: 'Resumo de Stock' },
                    { to: '/stock', icon: Package2, label: 'Armazéns e Stock' },
                    { to: '/stock-movements', icon: History, label: 'Histórico de Movimentos' },
                  ]}
                />
                <div className="w-px h-5 bg-border mx-1 shrink-0 self-center" />
              </>
            )}
            {user?.role === 'GESTOR' && (
              <NavLink to="/users" icon={UserCog} label="Utilizadores" active={isActive('/users')} />
            )}
            {user?.role === 'GESTOR' && (
              <NavGroup
                icon={Cog}
                label="Configurações"
                isActive={isActive}
                items={[
                  { to: '/company-settings', icon: Building2, label: 'Empresa' },
                  { to: '/categorias', icon: Tags, label: 'Catálogos' },
                ]}
              />
            )}
            {user?.role === 'GESTOR' && (
              <NavGroup
                icon={Calculator}
                label="Contabilidade"
                isActive={isActive}
                items={[
                  { to: '/fiscal-periods', icon: Calendar, label: 'Periodos/Exercicio' },
                ]}
              />
            )}
            {user?.role === 'GESTOR' && (
              <NavLink to="/tesouraria" icon={PiggyBank} label="Tesouraria" active={isActive('/tesouraria')} />
            )}
            {user?.role === 'GESTOR' && (
              <NavLink to="/recursos" icon={Boxes} label="Recursos" active={isActive('/recursos')} />
            )}
            {(user?.role === 'GESTOR' || user?.role === 'CAIXA') && (
              <NavLink to="/reservas" icon={CalendarClock} label="Reservas" active={isActive('/reservas')} />
            )}
            {user?.role === 'GESTOR' && (
              <NavLink to="/ocupacao" icon={History} label="Ocupação" active={isActive('/ocupacao')} />
            )}
            {(user?.role === 'GESTOR' || user?.role === 'ARMAZENISTA') && (
              <NavLink to="/consumo-interno" icon={PackageMinus} label="Consumo Interno" active={isActive('/consumo-interno')} />
            )}
            {(user?.role === 'GESTOR' || user?.role === 'CAIXA') && (
              <NavLink to="/contas-abertas" icon={Wallet2} label="Contas Abertas" active={isActive('/contas-abertas')} />
            )}
            {user?.role === 'GESTOR' && (
              <NavLink to="/saf-t" icon={FileText} label="SAF-T" active={isActive('/saf-t')} />
            )}
          </div>
          <div className="pointer-events-none absolute inset-y-0 left-0 w-6 bg-gradient-to-r from-bg-elevated to-transparent" />
          <div className="pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-bg-elevated to-transparent" />
        </div>

        <div className="flex items-center gap-2 sm:gap-4 text-[13px] text-text-muted shrink-0">
          {periodLabel && (
            <span className="hidden md:flex items-center gap-1.5 font-mono text-[12px] text-text-muted border border-border rounded-md px-2.5 py-1.5">
              <Calendar size={13} className="text-accent" />
              {periodLabel}
            </span>
          )}
          <button
            onClick={toggleTheme}
            aria-label="Alternar tema"
            className="flex items-center justify-center w-9 h-9 border border-border hover:border-accent rounded-md transition-colors cursor-pointer text-text-primary"
          >
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <button
            onClick={handleLogout}
            aria-label="Terminar sessão"
            title="Terminar sessão"
            className="flex items-center justify-center w-9 h-9 border border-border hover:border-accent hover:text-danger text-text-primary rounded-md transition-colors cursor-pointer"
          >
            <LogOut size={15} />
          </button>
        </div>
      </nav>

      <div className="pt-14 pb-11 min-h-screen">
        <Outlet />
      </div>

      <Footer />
    </div>
  );
}


import { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useLocation, Outlet } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { Building2, LogOut, LayoutDashboard, Sun, Moon, Package, Users, Calendar, Receipt, Settings, Package2, UserCog, History, FileText, Landmark, LayoutGrid, Store, Wheat, Factory, Wallet, SlidersHorizontal, Tags, Wrench, ChevronDown, Cog, Plus, ArrowLeftRight, Calculator, ClipboardList, Gauge, PiggyBank, CreditCard, Boxes, CalendarClock, Wallet2, PackageMinus, Truck, ShieldCheck } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useThemeStore } from '../store/themeStore';
import { getCurrentPeriod } from '../api/fiscal';
import { getMyPermissions } from '../api/permissions';
import { useCan } from '../utils/permissions';
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
  const setPermissions = useAuthStore((state) => state.setPermissions);
  const theme = useThemeStore((state) => state.theme);
  const toggleTheme = useThemeStore((state) => state.toggleTheme);
  const can = useCan();
  const [periodLabel, setPeriodLabel] = useState(null);
  const [partialLabel, setPartialLabel] = useState(null); // the soft-closed period, if any

  useEffect(() => {
    if (user?.role && user.role !== 'SUPER_ADMIN') {
      getCurrentPeriod()
        .then((data) => { setPeriodLabel(data.label); setPartialLabel(data.partial_label || null); })
        .catch(() => setPeriodLabel(null));
    }
  }, [user?.role]);

  // Loads this user's permission codes once per session (Layout mounts after
  // login). Fails closed: if the call fails, non-GESTOR users see no gated
  // items - the backend refuses their requests anyway.
  useEffect(() => {
    if (user?.role && user.role !== 'SUPER_ADMIN') {
      getMyPermissions()
        .then(setPermissions)
        .catch(() => { if (user.role !== 'GESTOR') setPermissions([]); });
    }
  }, [user?.role]);

  function handleLogout() {
    logout();
    navigate('/login');
  }

  function isActive(path) {
    return location.pathname === path || location.pathname.startsWith(path + '/');
  }

  // Menu groups - each item is shown only if the user holds its permission.
  const productionItems = [
    { to: '/producao', icon: Factory, label: 'Produtos configurados', perm: 'recipes:view' },
    { to: '/producao/historico', icon: ClipboardList, label: 'Resumo de Produção', perm: 'recipes:view' },
  ].filter((item) => (item.perms ? can.any(item.perms) : can(item.perm)));

  const stockItems = [
    { to: '/stock/dashboard', icon: Gauge, label: 'Resumo de Stock', perm: 'stock:view' },
    { to: '/stock', icon: Package2, label: 'Armazéns e Stock', perm: 'warehouses:view' },
    { to: '/stock-movements', icon: History, label: 'Histórico de Movimentos', perm: 'stock:view' },
  ].filter((item) => (item.perms ? can.any(item.perms) : can(item.perm)));

  const settingsItems = [
    { to: '/company-settings', icon: Building2, label: 'Empresa', perm: 'company:view' },
    { to: '/categorias', icon: Tags, label: 'Catálogos', perms: ['product_categories:manage', 'service_types:manage', 'tesouraria:reasons_manage', 'resource_types:manage', 'consumption_reasons:manage', 'tesouraria:payment_prefs_manage'] },
  ].filter((item) => (item.perms ? can.any(item.perms) : can(item.perm)));

  const accountingItems = [
    { to: '/fiscal-periods', icon: Calendar, label: 'Periodos/Exercicio', perm: 'fiscal_periods:view' },
  ].filter((item) => (item.perms ? can.any(item.perms) : can(item.perm)));

  return (
    <div className="min-h-screen bg-bg-primary">
      <nav className="fixed top-0 inset-x-0 z-50 h-14 bg-bg-elevated border-b border-border px-4 sm:px-7 flex items-center gap-3">
        <span className="font-display font-bold text-base text-accent shrink-0">
          RM SOFT
        </span>

        <div className="relative flex-1 min-w-0 h-full">
          <div ref={navScrollRef} onWheel={handleNavWheel} className="flex items-center gap-1 sm:gap-2 overflow-x-auto scrollbar-hover-thin h-full">
            {user?.role === 'GESTOR' && (
              <NavLink to="/dashboard" icon={LayoutDashboard} label="Painel" active={isActive('/dashboard')} />
            )}
            {user?.role === 'SUPER_ADMIN' && (
              <NavLink to="/admin/companies" icon={Building2} label="Empresas" active={isActive('/admin/companies')} />
            )}
            {user?.role === 'SUPER_ADMIN' && (
              <NavLink to="/configuracoes" icon={SlidersHorizontal} label="Configurações" active={isActive('/configuracoes')} />
            )}
            {user?.role === 'SUPER_ADMIN' && (
              <NavLink to="/visao-global" icon={LayoutGrid} label="Visao global" active={isActive('/visao-global')} />
            )}
            {(can('products:manage') || can('services:manage')) && (
              <>
                <div className="w-px h-5 bg-border mx-1 shrink-0 self-center" />
                {can('products:manage') && (
                  <NavLink to="/products" icon={Package} label="Produtos" active={isActive('/products')} />
                )}
                {can('services:manage') && (
                  <NavLink to="/services" icon={Wrench} label="Serviços" active={isActive('/services')} />
                )}
              </>
            )}
            {can('products:manage') && can('recipes:view') && (
              <NavLink to="/materia-prima" icon={Wheat} label="Matéria-prima" active={isActive('/materia-prima')} />
            )}
            {productionItems.length > 0 && (
              <>
                <NavGroup icon={Factory} label="Produção" isActive={isActive} items={productionItems} />
                <div className="w-px h-5 bg-border mx-1 shrink-0 self-center" />
              </>
            )}
            {can('customers:manage') && (
              <NavLink to="/customers" icon={Users} label="Clientes" active={isActive('/customers')} />
            )}
            {can('pos:view') && (
              <NavLink to="/caixa" icon={Wallet} label="Caixa" active={isActive('/caixa')} />
            )}
            {user?.role === 'GESTOR' && can('invoices:view') && (
              <NavLink to="/invoices" icon={Receipt} label="Faturas" active={isActive('/invoices')} />
            )}
            {stockItems.length > 0 && (
              <>
                <div className="w-px h-5 bg-border mx-1 shrink-0 self-center" />
                <NavGroup icon={Package2} label="Gestão de Stocks" isActive={isActive} items={stockItems} />
                <div className="w-px h-5 bg-border mx-1 shrink-0 self-center" />
              </>
            )}
            {user?.role === 'GESTOR' && (
              <NavLink to="/users" icon={UserCog} label="Utilizadores" active={isActive('/users')} />
            )}
            {settingsItems.length > 0 && (
              <NavGroup icon={Cog} label="Configurações" isActive={isActive} items={settingsItems} />
            )}
            {accountingItems.length > 0 && (
              <NavGroup icon={Calculator} label="Contabilidade" isActive={isActive} items={accountingItems} />
            )}
            {can('tesouraria:reasons_manage') && (
              <NavLink to="/tesouraria" icon={PiggyBank} label="Tesouraria" active={isActive('/tesouraria')} />
            )}
            {can('resources:manage') && (
              <NavLink to="/recursos" icon={Boxes} label="Recursos" active={isActive('/recursos')} />
            )}
            {can('bookings:view') && (
              <NavLink to="/reservas" icon={CalendarClock} label="Reservas" active={isActive('/reservas')} />
            )}
            {can('hotel:occupancy_view') && (
              <NavLink to="/ocupacao" icon={History} label="Ocupação" active={isActive('/ocupacao')} />
            )}
            {can('internal_consumption:view') && (
              <NavLink to="/consumo-interno" icon={PackageMinus} label="Consumo Interno" active={isActive('/consumo-interno')} />
            )}
            {can('suppliers:manage') && (
              <NavLink to="/fornecedores" icon={Truck} label="Fornecedores" active={isActive('/fornecedores')} />
            )}
            {user?.role === 'GESTOR' && (
              <NavLink to="/permissoes" icon={ShieldCheck} label="Permissoes" active={isActive('/permissoes')} />
            )}
            {can('open_accounts:view') && (
              <NavLink to="/contas-abertas" icon={Wallet2} label="Contas Abertas" active={isActive('/contas-abertas')} />
            )}
            {can('saf_t:export') && (
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
              {periodLabel}{partialLabel && <span className="ml-1.5 text-amber-500">· {partialLabel} (parcial)</span>}
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
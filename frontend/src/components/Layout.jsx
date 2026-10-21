import { useState, useEffect, useRef } from 'react';
import { ChefHat, History as KitchenHistoryIcon } from 'lucide-react';
import { Link, useNavigate, useLocation, Outlet } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { Building2, LogOut, LayoutDashboard, Sun, Moon, Package, Users, Calendar, Receipt, Settings, Package2, UserCog, History, FileText, Landmark, LayoutGrid, Store, Wheat, Factory, Wallet, SlidersHorizontal, Tags, Wrench, ChevronDown, Cog, Plus, ArrowLeftRight, Calculator, ClipboardList, Gauge, PiggyBank, CreditCard, Boxes, CalendarClock, Wallet2, PackageMinus, Truck, ShieldCheck, FileInput, Send, HandCoins, Bot, HelpCircle, LifeBuoy } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import apiClient from '../api/client';
import { useThemeStore } from '../store/themeStore';
import { getCurrentPeriod } from '../api/fiscal';
import { getMyPermissions } from '../api/permissions';
import { getPharmacyContext } from '../api/pharmacy';
import { useCan } from '../utils/permissions';
import Footer from './Footer';
import AssistantPanel, { readStored, writeStored } from './AssistantPanel';
import HelpPanel from './HelpPanel';
import { getAssistantStatus } from '../api/ai';

// A square icon button of the top bar, its name shown below it on hover (keeps the bar narrow).
function IconButton({ icon: Icon, label, active, onClick }) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={'group relative flex items-center justify-center w-9 h-9 border rounded-md transition-colors cursor-pointer ' + (active ? 'border-accent text-accent bg-accent/10' : 'border-border hover:border-accent text-text-primary')}
    >
      <Icon size={16} />
      <span className="pointer-events-none absolute top-full mt-2 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md bg-bg-elevated border border-border px-2.5 py-1 text-[12px] text-text-primary shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50">
        {label}
      </span>
    </button>
  );
}

function NavLink({ to, icon: Icon, label, active }) {
  return (
    <Link
      to={to}
      className={
        'flex items-center gap-1.5 text-[13px] font-semibold uppercase tracking-wide px-3 py-2 rounded-md transition-colors cursor-pointer shrink-0 ' +
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
          'flex items-center gap-1.5 text-[13px] font-semibold uppercase tracking-wide px-3 py-2 rounded-md transition-colors cursor-pointer shrink-0 ' +
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
                'flex items-center gap-2 px-3.5 py-2.5 text-[12.5px] font-medium uppercase tracking-wide transition-colors ' +
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

  // The AI assistant: its button only for a role allowed to use it, in a company where it is switched on
  const canUseAssistant = can('assistant:use');
  const [assistantStatus, setAssistantStatus] = useState(null);
  const [assistantOpen, setAssistantOpen] = useState(() => readStored('rm.assistant.open') === '1'); // reopened after a reload
  useEffect(() => {
    writeStored('rm.assistant.open', assistantOpen ? '1' : null);
  }, [assistantOpen]);
  // The Ajuda panel: same place as the assistant's, so opening one closes the other
  const [helpOpen, setHelpOpen] = useState(() => readStored('rm.help.open') === '1' && readStored('rm.assistant.open') !== '1');
  useEffect(() => {
    writeStored('rm.help.open', helpOpen ? '1' : null);
  }, [helpOpen]);
  const toggleHelp = () => { setHelpOpen((v) => !v); setAssistantOpen(false); };
  const toggleAssistant = () => { setAssistantOpen((v) => !v); setHelpOpen(false); };
  useEffect(() => {
    if (!canUseAssistant || user?.role === 'SUPER_ADMIN') {
      setAssistantStatus(null);
      return;
    }
    getAssistantStatus().then(setAssistantStatus).catch(() => setAssistantStatus(null));
  }, [canUseAssistant, user?.role]);

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

  // The Farmácia's screens only for a company with the Farmácia sector (read from its modules).
  const [pharmacyEnabled, setPharmacyEnabled] = useState(false);
  useEffect(() => {
    if (user?.role && user.role !== 'SUPER_ADMIN') {
      getPharmacyContext().then((c) => setPharmacyEnabled(!!c.enabled)).catch(() => setPharmacyEnabled(false));
    }
  }, [user?.role]);

  function handleLogout() {
    logout();
    navigate('/login');
  }

  // Acesso de suporte RM SOFT: a banner all the time, and «Sair do suporte» ends it at once
  const support = user?.support || null;
  const hhmm = (v) => (v ? new Date(v).toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit' }) : '');
  async function endSupport() {
    try { await apiClient.post('/auth/support/end'); } catch { /* ended or expired already: leave anyway */ }
    logout();
    navigate('/login');
  }
  // the time left, second by second; at zero the access is over: back to the login
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!support) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [support?.expires_at]);
  const left = support ? Math.max(0, Math.floor((new Date(support.expires_at).getTime() - now) / 1000)) : null;
  useEffect(() => {
    if (support && left === 0) endSupport();
  }, [left === 0]);
  const countdown = left === null ? '' : `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;

  // The menu of the company's users, in 7 groups - each entry is shown only to who may open it (show), a group with
  // a single visible entry is a plain link, a group with none is not shown (a sector without bookings has no Reservas).
  const visible = (items) => items.filter((item) => item.show);
  const menuGroups = [
    {
      key: 'vendas', icon: Receipt, label: 'Vendas', items: visible([
        { to: '/caixa', icon: Wallet, label: 'Caixa', show: can('pos:view') },
        { to: '/invoices', icon: Receipt, label: 'Faturas', show: user?.role === 'GESTOR' && can('invoices:view') },
        { to: '/customers', icon: Users, label: 'Clientes', show: can('customers:manage') },
        { to: '/receitas', icon: FileText, label: 'Receitas e registos', show: pharmacyEnabled && can('pharmacy:registers') },
        { to: '/contas-abertas', icon: Wallet2, label: 'Contas Abertas', show: can('open_accounts:view') },
        { to: '/cozinha', icon: ChefHat, label: 'Cozinha - pedidos em curso', show: can('kitchen:view') },
        { to: '/cozinha/historico', icon: KitchenHistoryIcon, label: 'Cozinha - histórico', show: can('kitchen:history') },
      ]),
    },
    {
      key: 'catalogo', icon: Package, label: 'Catálogo', items: visible([
        { to: '/products', icon: Package, label: 'Produtos', show: can('products:manage') },
        { to: '/services', icon: Wrench, label: 'Serviços', show: can('services:manage') },
        { to: '/materia-prima', icon: Wheat, label: 'Matéria-prima', show: can('products:manage') && can('recipes:view') },
        { to: '/producao', icon: Factory, label: 'Produtos configurados', show: can('recipes:view') },
        { to: '/producao/historico', icon: ClipboardList, label: 'Resumo de Produção', show: can('recipes:view') },
      ]),
    },
    {
      key: 'stock', icon: Package2, label: 'Stock', items: visible([
        { to: '/stock/dashboard', icon: Gauge, label: 'Resumo de Stock', show: can('stock:view') },
        { to: '/stock', icon: Package2, label: 'Armazéns e Stock', show: can('warehouses:view') },
        { to: '/stock-movements', icon: History, label: 'Histórico de Movimentos', show: can('stock:view') },
        { to: '/consumo-interno', icon: PackageMinus, label: 'Consumo Interno', show: can('internal_consumption:view') },
        { to: '/fornecedores', icon: Truck, label: 'Fornecedores', show: can('suppliers:manage') },
        { to: '/compras', icon: FileInput, label: 'Faturas de compra', show: can('purchases:view') },
        { to: '/pagamentos-fornecedores', icon: HandCoins, label: 'Pagamentos a fornecedores', show: can('purchases:view') },
        { to: '/guias', icon: Send, label: 'Guias', show: can('guias:view') },
      ]),
    },
    {
      key: 'reservas', icon: CalendarClock, label: 'Reservas', items: visible([
        { to: '/recursos', icon: Boxes, label: 'Recursos', show: can('resources:manage') },
        { to: '/reservas', icon: CalendarClock, label: 'Reservas', show: can('bookings:view') },
        { to: '/recursos/historico', icon: History, label: 'Histórico', show: can('resources:history') },
      ]),
    },
    {
      key: 'financas', icon: Landmark, label: 'Finanças', items: visible([
        { to: '/tesouraria', icon: PiggyBank, label: 'Tesouraria', show: can('tesouraria:overview') },
        { to: '/fiscal-periods', icon: Calendar, label: 'Períodos/Exercício', show: can('fiscal_periods:view') },
        { to: '/apuramento-iva', icon: Calculator, label: 'Apuramento do IVA', show: can('vat:return') },
        { to: '/saf-t', icon: FileText, label: 'SAF-T', show: can('saf_t:export') },
      ]),
    },
    {
      key: 'administracao', icon: Cog, label: 'Administração', items: visible([
        { to: '/company-settings', icon: Building2, label: 'Empresa', show: can('company:view') },
        { to: '/categorias', icon: Tags, label: 'Catálogos', show: can.any(['product_categories:manage', 'service_types:manage', 'tesouraria:reasons_manage', 'resource_types:manage', 'consumption_reasons:manage', 'tesouraria:payment_prefs_manage', 'pharmaceutical_forms:manage']) },
        { to: '/users', icon: UserCog, label: 'Utilizadores', show: user?.role === 'GESTOR' },
        { to: '/permissoes', icon: ShieldCheck, label: 'Permissões', show: user?.role === 'GESTOR' },
      ]),
    },
  ];

  // A menu entry is active on its own page and its sub-pages, unless a more precise entry matches better:
  // /stock must not light up on /stock/dashboard, and /stock-movements is not a sub-page of /stock.
  function isActive(path) {
    const here = location.pathname;
    const matches = (p) => here === p || here.startsWith(p + '/');
    if (!matches(path)) return false;
    const groupPaths = menuGroups.flatMap((g) => g.items).map((i) => i.to);
    return !groupPaths.some((p) => p !== path && p.length > path.length && matches(p));
  }

  return (
    <div className="min-h-screen bg-bg-primary">
      <nav className="fixed top-0 inset-x-0 z-50 h-14 bg-bg-elevated border-b border-border px-4 sm:px-7 flex items-center gap-3">
        <span className="font-display font-extrabold text-xl sm:text-2xl tracking-wide text-accent shrink-0">
          RM SOFT
        </span>

        <div className="relative flex-1 min-w-0 h-full">
          {/* the menu centred: a row as wide as its items, in the middle of the scroll area (mx-auto) - when it is
              wider than the bar it starts at the left edge and scrolls, nothing is cut on the left */}
          <div ref={navScrollRef} onWheel={handleNavWheel} className="flex overflow-x-auto scrollbar-hover-thin h-full">
          <div className="flex items-center gap-1 sm:gap-2 w-max mx-auto h-full">
            {user?.role === 'CAIXA' ? (
              // The cashier works from the till only: everything else is in its side panels
              // (documents, articles, moedeiro, operations, daily report, open accounts).
              <NavLink to="/caixa" icon={Wallet} label="Caixa" active={isActive('/caixa')} />
            ) : (
            <>
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
              <NavLink to="/visao-global" icon={LayoutGrid} label="Visão global" active={isActive('/visao-global')} />
            )}
            {menuGroups.map((group) => (
              group.items.length > 1 ? (
                <NavGroup key={group.key} icon={group.icon} label={group.label} isActive={isActive} items={group.items} />
              ) : group.items.length === 1 ? (
                <NavLink key={group.key} to={group.items[0].to} icon={group.items[0].icon} label={group.items[0].label} active={isActive(group.items[0].to)} />
              ) : null
            ))}
            </>
            )}
          </div>
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
          {user?.role && (
            <IconButton icon={HelpCircle} label="Ajuda" active={helpOpen} onClick={toggleHelp} />
          )}
          {assistantStatus?.enabled && (
            <IconButton icon={Bot} label="Assistente IA" active={assistantOpen} onClick={toggleAssistant} />
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

      {support && (
        <div className="fixed top-14 inset-x-0 z-40 h-9 bg-amber-400 text-amber-950 text-[13px] flex items-center justify-center gap-3 px-4">
          <LifeBuoy size={15} className="shrink-0" />
          <span className="truncate">
            <span className="font-semibold">Modo suporte RM SOFT</span> · {support.company_name} · entrou às {hhmm(support.started_at)}
          </span>
          <span title={'Termina às ' + hhmm(support.expires_at)}
            className={'shrink-0 font-mono font-semibold rounded px-2 py-0.5 ' + (left <= 300 ? 'bg-red-700 text-white animate-pulse' : 'bg-amber-950/10')}>
            restam {countdown}
          </span>
          <button onClick={endSupport} className="shrink-0 bg-amber-950 hover:bg-black text-amber-50 rounded px-2.5 py-0.5 font-semibold cursor-pointer">
            Sair do suporte
          </button>
        </div>
      )}

      <div className={(support ? 'pt-[92px]' : 'pt-14') + ' pb-11 min-h-screen'}>
        <Outlet />
      </div>

      {user?.role && <HelpPanel open={helpOpen} onClose={() => setHelpOpen(false)} />}

      {assistantStatus?.enabled && (
        <AssistantPanel open={assistantOpen} onClose={() => setAssistantOpen(false)} status={assistantStatus} onStatus={setAssistantStatus} />
      )}

      <Footer />
    </div>
  );
}
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Suporte from './pages/Suporte';
import Dashboard from './pages/Dashboard';
import AdminCompanies from './pages/AdminCompanies';
import Products from './pages/Products';
import MateriaPrima from './pages/MateriaPrima';
import Producao from './pages/Producao';
import StockDashboard from './pages/StockDashboard';
import ProductionHistory from './pages/ProductionHistory';
import Caixa from './pages/Caixa';
import Configuracoes from './pages/Configuracoes';
import Toaster from './components/Toaster';
import CatalogoReferencia from './pages/CatalogoReferencia';
import Planos from './pages/Planos';
import Pedidos from './pages/Pedidos';
import Categorias from './pages/Categorias';
import Services from './pages/Services';
import Customers from './pages/Customers';
import FiscalPeriods from './pages/FiscalPeriods';
import SaftExport from './pages/SaftExport';
import Invoices from './pages/Invoices';
import CompanySettings from './pages/CompanySettings';
import Stock from './pages/Stock';
import StockMovements from './pages/StockMovements';
import Users from './pages/Users';
import Tesouraria from './pages/Tesouraria';
import ApuramentoIva from './pages/ApuramentoIva';
import Receitas from './pages/Receitas';
import Compras from './pages/Compras';
import PagamentosFornecedores from './pages/PagamentosFornecedores';
import Guias from './pages/Guias';
import Recursos from './pages/Recursos';
import Reservas from './pages/Reservas';
import HistoricoRecursos from './pages/HistoricoRecursos';
import ConsumoInterno from './pages/ConsumoInterno';
import Fornecedores from './pages/Fornecedores';
import Permissoes from './pages/Permissoes';
import VisaoGlobal from './pages/VisaoGlobal';
import ContasAbertas from './pages/ContasAbertas';
import Cozinha from './pages/Cozinha';
import KitchenHistory from './pages/KitchenHistory';
import Layout from './components/Layout';
import { useAuthStore } from './store/authStore';
import RequirePermission from './components/RequirePermission';
import { homeFor } from './utils/roleHome';

function ProtectedRoute({ children }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  return isAuthenticated ? children : <Navigate to="/login" replace />;
}

function SuperAdminRoute({ children }) {
  const user = useAuthStore((state) => state.user);
  return user?.role === 'SUPER_ADMIN' ? children : <Navigate to={homeFor(user?.role)} replace />;
}

function GestorRoute({ children }) {
  const user = useAuthStore((state) => state.user);
  return user?.role === 'GESTOR' ? children : <Navigate to={homeFor(user?.role)} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/suporte" element={<Suporte />} />

        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<RequirePermission perm="dashboard:view" allowSuperAdmin><Dashboard /></RequirePermission>} />
          <Route path="/products" element={<RequirePermission perm="products:manage"><Products /></RequirePermission>} />
          <Route path="/materia-prima" element={<RequirePermission perm="products:manage"><MateriaPrima /></RequirePermission>} />
          <Route path="/producao" element={<RequirePermission perm="recipes:view"><Producao /></RequirePermission>} />
          <Route path="/producao/historico" element={<RequirePermission perm="recipes:view"><ProductionHistory /></RequirePermission>} />
          <Route path="/caixa" element={<RequirePermission perm="pos:view"><Caixa /></RequirePermission>} />
          <Route path="/configuracoes" element={<SuperAdminRoute><Configuracoes /></SuperAdminRoute>} />
          <Route path="/visao-global" element={<SuperAdminRoute><VisaoGlobal /></SuperAdminRoute>} />
          <Route path="/catalogo-referencia" element={<SuperAdminRoute><CatalogoReferencia /></SuperAdminRoute>} />
          <Route path="/planos" element={<SuperAdminRoute><Planos /></SuperAdminRoute>} />
          <Route path="/pedidos" element={<SuperAdminRoute><Pedidos /></SuperAdminRoute>} />
          <Route path="/categorias" element={<RequirePermission anyOf={['product_categories:manage', 'service_types:manage', 'tesouraria:reasons_manage', 'resource_types:manage', 'consumption_reasons:manage', 'tesouraria:payment_prefs_manage']}><Categorias /></RequirePermission>} />
          <Route path="/services" element={<RequirePermission perm="services:manage"><Services /></RequirePermission>} />
          <Route path="/customers" element={<RequirePermission perm="customers:manage"><Customers /></RequirePermission>} />
          <Route path="/fiscal-periods" element={<RequirePermission perm="fiscal_periods:view"><FiscalPeriods /></RequirePermission>} />
          <Route path="/saf-t" element={<RequirePermission perm="saf_t:export"><SaftExport /></RequirePermission>} />
          <Route path="/invoices" element={<RequirePermission perm="invoices:view"><Invoices /></RequirePermission>} />
          <Route path="/company-settings" element={<RequirePermission perm="company:view"><CompanySettings /></RequirePermission>} />
          <Route path="/stock" element={<RequirePermission perm="warehouses:view"><Stock /></RequirePermission>} />
          <Route path="/stock/dashboard" element={<RequirePermission perm="stock:view"><StockDashboard /></RequirePermission>} />
          <Route path="/stock-movements" element={<RequirePermission perm="stock:view"><StockMovements /></RequirePermission>} />
          <Route path="/users" element={<GestorRoute><Users /></GestorRoute>} />
          <Route path="/tesouraria" element={<RequirePermission perm="tesouraria:overview"><Tesouraria /></RequirePermission>} />
          <Route path="/apuramento-iva" element={<RequirePermission perm="vat:return"><ApuramentoIva /></RequirePermission>} />
          <Route path="/receitas" element={<RequirePermission perm="pharmacy:registers"><Receitas /></RequirePermission>} />
          <Route path="/recursos" element={<RequirePermission perm="resources:manage"><Recursos /></RequirePermission>} />
          <Route path="/reservas" element={<RequirePermission perm="bookings:view"><Reservas /></RequirePermission>} />
          <Route path="/recursos/historico" element={<RequirePermission perm="resources:history"><HistoricoRecursos /></RequirePermission>} />
          <Route path="/consumo-interno" element={<RequirePermission perm="internal_consumption:view"><ConsumoInterno /></RequirePermission>} />
          <Route path="/fornecedores" element={<RequirePermission perm="suppliers:manage"><Fornecedores /></RequirePermission>} />
          <Route path="/compras" element={<RequirePermission perm="purchases:view"><Compras /></RequirePermission>} />
          <Route path="/pagamentos-fornecedores" element={<RequirePermission perm="purchases:view"><PagamentosFornecedores /></RequirePermission>} />
          <Route path="/guias" element={<RequirePermission perm="guias:view"><Guias /></RequirePermission>} />
          <Route path="/permissoes" element={<GestorRoute><Permissoes /></GestorRoute>} />
          <Route path="/contas-abertas" element={<RequirePermission perm="open_accounts:view"><ContasAbertas /></RequirePermission>} />
          <Route path="/cozinha" element={<RequirePermission perm="kitchen:view"><Cozinha /></RequirePermission>} />
          <Route path="/cozinha/historico" element={<RequirePermission perm="kitchen:history"><KitchenHistory /></RequirePermission>} />
          <Route
            path="/admin/companies"
            element={
              <SuperAdminRoute>
                <AdminCompanies />
              </SuperAdminRoute>
            }
          />
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}









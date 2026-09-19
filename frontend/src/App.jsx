import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import AdminCompanies from './pages/AdminCompanies';
import Products from './pages/Products';
import MateriaPrima from './pages/MateriaPrima';
import Producao from './pages/Producao';
import StockDashboard from './pages/StockDashboard';
import ProductionHistory from './pages/ProductionHistory';
import Caixa from './pages/Caixa';
import Configuracoes from './pages/Configuracoes';
import Categorias from './pages/Categorias';
import Services from './pages/Services';
import NovaFatura from './pages/NovaFatura';
import Customers from './pages/Customers';
import FiscalPeriods from './pages/FiscalPeriods';
import SaftExport from './pages/SaftExport';
import Invoices from './pages/Invoices';
import CompanySettings from './pages/CompanySettings';
import Stock from './pages/Stock';
import StockMovements from './pages/StockMovements';
import Users from './pages/Users';
import Tesouraria from './pages/Tesouraria';
import Recursos from './pages/Recursos';
import Reservas from './pages/Reservas';
import Ocupacao from './pages/Ocupacao';
import ConsumoInterno from './pages/ConsumoInterno';
import Fornecedores from './pages/Fornecedores';
import Permissoes from './pages/Permissoes';
import ContasAbertas from './pages/ContasAbertas';
import Layout from './components/Layout';
import { useAuthStore } from './store/authStore';

function ProtectedRoute({ children }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  return isAuthenticated ? children : <Navigate to="/login" replace />;
}

function SuperAdminRoute({ children }) {
  const user = useAuthStore((state) => state.user);
  return user?.role === 'SUPER_ADMIN' ? children : <Navigate to="/dashboard" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />

        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/products" element={<Products />} />
          <Route path="/materia-prima" element={<MateriaPrima />} />
          <Route path="/producao" element={<Producao />} />
          <Route path="/producao/historico" element={<ProductionHistory />} />
          <Route path="/caixa" element={<Caixa />} />
          <Route path="/configuracoes" element={<Configuracoes />} />
          <Route path="/categorias" element={<Categorias />} />
          <Route path="/services" element={<Services />} />
          <Route path="/invoices/new" element={<NovaFatura />} />
          <Route path="/customers" element={<Customers />} />
          <Route path="/fiscal-periods" element={<FiscalPeriods />} />
          <Route path="/saf-t" element={<SaftExport />} />
          <Route path="/invoices" element={<Invoices />} />
          <Route path="/company-settings" element={<CompanySettings />} />
          <Route path="/stock" element={<Stock />} />
          <Route path="/stock/dashboard" element={<StockDashboard />} />
          <Route path="/stock-movements" element={<StockMovements />} />
          <Route path="/users" element={<Users />} />
          <Route path="/tesouraria" element={<Tesouraria />} />
          <Route path="/recursos" element={<Recursos />} />
          <Route path="/reservas" element={<Reservas />} />
          <Route path="/ocupacao" element={<Ocupacao />} />
          <Route path="/consumo-interno" element={<ConsumoInterno />} />
          <Route path="/fornecedores" element={<Fornecedores />} />
          <Route path="/permissoes" element={<Permissoes />} />
          <Route path="/contas-abertas" element={<ContasAbertas />} />
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









import { useState, useEffect } from 'react';
import { LayoutDashboard, TrendingUp, Receipt, AlertTriangle, Loader2, Package2, Send, Clock, CheckCircle2, XCircle, ListChecks } from 'lucide-react';
import { getDashboardSummary } from '../api/dashboard';
import { getMyCompanySetup } from '../api/company';
import { useAuthStore } from '../store/authStore';
import { extractErrorMessage } from '../utils/errors';
import { useCan } from '../utils/permissions';
import SetupChecklist from '../components/SetupChecklist';

// "Esconder" is remembered per user in this browser; only offered once the required steps are done.
const hiddenKey = (userId) => 'rmsoft.setup.hidden.' + userId;
function readHidden(userId) {
  try { return localStorage.getItem(hiddenKey(userId)) === '1'; } catch { return false; }
}
function writeHidden(userId) {
  try { localStorage.setItem(hiddenKey(userId), '1'); } catch { /* the card simply comes back next time */ }
}

// Configuração inicial on the gestor's dashboard: shown until every step is done (or hidden once the required ones are).
function SetupCard({ userId }) {
  const [setup, setSetup] = useState(null);
  const [hidden, setHidden] = useState(() => readHidden(userId));
  useEffect(() => {
    getMyCompanySetup().then(setSetup).catch(() => setSetup(null));
  }, []);
  if (!setup || setup.all_done || (hidden && setup.complete)) return null;
  return (
    <div className="bg-bg-elevated border border-border rounded-lg p-5 mb-6">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <h3 className="font-display font-semibold text-[16px] text-text-primary flex items-center gap-2">
            <ListChecks size={18} className="text-accent" />
            Configuração inicial
          </h3>
          <p className="text-[12px] text-text-muted mt-0.5">
            {setup.complete
              ? 'Os passos obrigatórios estão concluídos. Os recomendados melhoram os documentos e o trabalho da equipa.'
              : 'Conclua estes passos para começar a faturar. Cada passo fica marcado sozinho quando estiver feito.'}
          </p>
        </div>
        {setup.complete && (
          <button
            type="button"
            onClick={() => { writeHidden(userId); setHidden(true); }}
            className="shrink-0 px-3 py-1.5 rounded-md border border-border text-[12px] font-medium text-text-muted hover:text-text-primary transition-colors cursor-pointer"
          >
            Esconder
          </button>
        )}
      </div>
      <SetupChecklist data={setup} />
    </div>
  );
}

function formatMoney(value) {
  return new Intl.NumberFormat('pt-PT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value) + ' Kz';
}

function formatQty(value) {
  return value % 1 === 0 ? String(value) : String(value).replace('.', ',');
}

const STATUS_STYLE = {
  PENDENTE: { icon: Clock, color: 'text-text-muted', bg: 'bg-text-muted/10', label: 'Pendente' },
  POR_ENVIAR: { icon: Send, color: 'text-accent', bg: 'bg-accent/10', label: 'Por enviar' },
  ENVIADA: { icon: CheckCircle2, color: 'text-success', bg: 'bg-success/10', label: 'Enviada' },
  ERRO: { icon: XCircle, color: 'text-danger', bg: 'bg-danger/10', label: 'Erro' },
};

export default function Dashboard() {
  const user = useAuthStore((state) => state.user);
  const can = useCan();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (user?.role === 'SUPER_ADMIN') {
      setLoading(false);
      return;
    }
    getDashboardSummary()
      .then(setSummary)
      .catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar painel')))
      .finally(() => setLoading(false));
  }, [user?.role]);

  if (user?.role === 'SUPER_ADMIN') {
    return (
      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
        <div className="bg-bg-elevated border border-border rounded-lg p-8 text-center">
          <h2 className="font-display font-semibold text-xl text-text-primary mb-2">
            Bem-vindo, {user?.full_name}
          </h2>
          <p className="text-text-muted text-sm">
            Utilize "Empresas" para gerir as empresas clientes da plataforma.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <LayoutDashboard size={22} className="text-accent" />
        Painel
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Olá, {user?.full_name}
      </p>

      {can('company:manage') && <SetupCard userId={user?.id} />}

      {loading && (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      )}

      {error && (
        <div className="px-6 py-4 text-danger text-sm bg-danger/10 rounded-lg">{error}</div>
      )}

      {!loading && !error && summary && (
        <div className="flex flex-col gap-6">
          {/* Revenue cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-bg-elevated border border-border rounded-lg p-5">
              <div className="flex items-center gap-2 text-text-muted text-[11px] uppercase tracking-wide mb-2">
                <TrendingUp size={13} className="text-accent" />
                Faturação hoje
              </div>
              <p className="font-display font-semibold text-2xl text-text-primary">{formatMoney(summary.revenue_today)}</p>
            </div>
            <div className="bg-bg-elevated border border-border rounded-lg p-5">
              <div className="flex items-center gap-2 text-text-muted text-[11px] uppercase tracking-wide mb-2">
                <TrendingUp size={13} className="text-accent" />
                Faturação este mês
              </div>
              <p className="font-display font-semibold text-2xl text-text-primary">{formatMoney(summary.revenue_month)}</p>
            </div>
            <div className="bg-bg-elevated border border-border rounded-lg p-5">
              <div className="flex items-center gap-2 text-text-muted text-[11px] uppercase tracking-wide mb-2">
                <Receipt size={13} className="text-accent" />
                Faturas este mês
              </div>
              <p className="font-display font-semibold text-2xl text-text-primary">{summary.invoice_count_month}</p>
            </div>
            <div className="bg-bg-elevated border border-border rounded-lg p-5">
              <div className="flex items-center gap-2 text-text-muted text-[11px] uppercase tracking-wide mb-2">
                <Package2 size={13} className="text-accent" />
                Produtos em alerta
              </div>
              <p className={'font-display font-semibold text-2xl ' + (summary.low_stock_products.length > 0 ? 'text-danger' : 'text-text-primary')}>
                {summary.low_stock_products.length}
              </p>
            </div>
          </div>

          {/* Invoice status breakdown - only in Faturação Eletrónica (a MANUAL document is declared by the SAF-T) */}
          {summary.agt_realtime && (
          <div className="bg-bg-elevated border border-border rounded-lg p-5">
            <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide mb-3">Faturas por estado (este mês)</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {Object.entries(summary.invoices_by_status).map(([status, count]) => {
                const style = STATUS_STYLE[status] || STATUS_STYLE.PENDENTE;
                const Icon = style.icon;
                return (
                  <div key={status} className={'flex items-center gap-2.5 rounded-md px-3.5 py-3 ' + style.bg}>
                    <Icon size={16} className={style.color} />
                    <div>
                      <p className={'font-display font-semibold text-lg ' + style.color}>{count}</p>
                      <p className="text-[11px] text-text-muted">{style.label}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Low stock alerts */}
            <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
              <div className="px-5 py-3.5 border-b border-border flex items-center gap-2">
                <AlertTriangle size={15} className="text-danger" />
                <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Stock baixo</p>
              </div>
              {summary.low_stock_products.length === 0 ? (
                <div className="text-center py-10 text-text-muted text-sm">Nenhum produto em alerta</div>
              ) : (
                <div className="divide-y divide-border">
                  {summary.low_stock_products.map((p) => (
                    <div key={p.code} className="flex items-center justify-between px-5 py-3 text-sm">
                      <div>
                        <p className="font-display font-medium text-text-primary">{p.name}</p>
                        <p className="text-[12px] font-mono text-text-muted">{p.code}</p>
                      </div>
                      <p className="font-mono text-danger">{formatQty(p.quantity)} / {formatQty(p.min_stock_threshold)}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Recent invoices */}
            <div className="bg-bg-elevated border border-border rounded-lg overflow-hidden">
              <div className="px-5 py-3.5 border-b border-border flex items-center gap-2">
                <Receipt size={15} className="text-accent" />
                <p className="text-[11px] font-semibold text-text-muted uppercase tracking-wide">Últimas faturas</p>
              </div>
              {summary.recent_invoices.length === 0 ? (
                <div className="text-center py-10 text-text-muted text-sm">Nenhuma fatura emitida ainda</div>
              ) : (
                <div className="divide-y divide-border">
                  {summary.recent_invoices.map((inv) => (
                    <div key={inv.id} className="flex items-center justify-between px-5 py-3 text-sm">
                      <div>
                        <p className="font-display font-medium text-text-primary">{inv.series}/{inv.number}</p>
                        <p className="text-[12px] text-text-muted">{inv.customer_name || 'Sem cliente'} · {inv.business_date}</p>
                      </div>
                      <p className="font-mono text-text-primary">{formatMoney(inv.total)}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

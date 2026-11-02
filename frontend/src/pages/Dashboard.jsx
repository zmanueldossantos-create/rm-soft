import { useState, useEffect } from 'react';
import { LayoutDashboard, TrendingUp, Receipt, AlertTriangle, Loader2, Package2, Send, Clock, CheckCircle2, XCircle, ListChecks,
  BarChart3, Wallet, Trophy, Landmark, CalendarClock, Factory, HandCoins, ArrowDownToLine } from 'lucide-react';
import { Block, Kpi, SalesChart, PaymentsToday, TopProducts, Tills, LowStock, Expiring, ProductionToday, RecentDocuments,
  formatMoney, versusYesterday } from '../components/PainelBlocks';
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

const STATUS_STYLE = {
  PENDENTE: { icon: Clock, color: 'text-text-muted', bg: 'bg-text-muted/10', label: 'Pendente' },
  POR_ENVIAR: { icon: Send, color: 'text-accent', bg: 'bg-accent/10', label: 'Por enviar' },
  ENVIADA: { icon: Send, color: 'text-accent', bg: 'bg-accent/10', label: 'Enviada' },
  VALIDADA: { icon: CheckCircle2, color: 'text-success', bg: 'bg-success/10', label: 'Validada' },
  VALIDADA_P: { icon: CheckCircle2, color: 'text-amber-500', bg: 'bg-amber-500/10', label: 'Validada (penalização)' },
  ERRO: { icon: XCircle, color: 'text-danger', bg: 'bg-danger/10', label: 'Recusada' },
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
          {/* The day, the month, the money owed both ways (each only for who may see it) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {(() => { const vs = versusYesterday(summary.revenue_today, summary.revenue_yesterday);
              return <Kpi icon={TrendingUp} label="Vendas hoje" value={formatMoney(summary.revenue_today)} sub={vs.text} subTone={vs.tone} />; })()}
            <Kpi icon={TrendingUp} label="Vendas este mês" value={formatMoney(summary.revenue_month)}
              sub={summary.invoice_count_month + ' documento(s) de venda'} />
            {summary.receivables
              ? <Kpi icon={HandCoins} label="A receber de clientes" value={formatMoney(summary.receivables.total)}
                  sub={summary.receivables.overdue > 0 ? formatMoney(summary.receivables.overdue) + ' em atraso' : summary.receivables.count + ' fatura(s) por pagar'}
                  subTone={summary.receivables.overdue > 0 ? 'text-danger' : 'text-text-muted'} />
              : <Kpi icon={Package2} label="Produtos em alerta" value={summary.low_stock_products.length}
                  valueTone={summary.low_stock_products.length ? 'text-danger' : 'text-text-primary'} />}
            {summary.payables
              ? <Kpi icon={ArrowDownToLine} label="A pagar a fornecedores" value={formatMoney(summary.payables.total)}
                  sub={summary.payables.overdue > 0 ? formatMoney(summary.payables.overdue) + ' vencido' : summary.payables.count + ' fatura(s) de compra por pagar'}
                  subTone={summary.payables.overdue > 0 ? 'text-danger' : 'text-text-muted'} />
              : <Kpi icon={Receipt} label="Documentos este mês" value={summary.invoice_count_month} />}
          </div>

          {/* Faturação Eletrónica: the AGT not answering (contingência), documents late (the AGT penalises after 24 h) */}
          {summary.agt && (summary.agt.contingency || summary.agt.late > 0) && (
            <div className="flex flex-col gap-2">
              {summary.agt.contingency && (
                <div className="flex items-start gap-2.5 border border-amber-500/40 bg-amber-500/10 rounded-lg px-4 py-3 text-sm text-amber-500">
                  <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                  <span>
                    Faturação Eletrónica em <b>contingência</b>{summary.agt.manual ? ' (ativada manualmente)' : ' - a AGT não responde'}
                    {summary.agt.since ? ' desde ' + new Date(summary.agt.since).toLocaleString('pt-PT') : ''}.
                    {' '}{summary.agt.waiting} documento(s) em espera - seguem sozinhos quando a ligação voltar.
                    {!summary.agt.has_c_series && ' Sem série de contingência válida: os documentos usam a série normal - peça uma série C à AGT quando houver ligação.'}
                  </span>
                </div>
              )}
              {summary.agt.late > 0 && (
                <div className="flex items-start gap-2.5 border border-danger/40 bg-danger/10 rounded-lg px-4 py-3 text-sm text-danger">
                  <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                  <span>{summary.agt.late} documento(s) ainda não validado(s) pela AGT há mais de {summary.agt.late_hours} h - a AGT penaliza a partir das 24 h. Verifique a ligação à internet e Definições da Empresa → Faturação Eletrónica.</span>
                </div>
              )}
            </div>
          )}

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

          {/* Sales of the 30 days and what came in today */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Block icon={BarChart3} title="Vendas dos últimos 30 dias" className="lg:col-span-2">
              <SalesChart days={summary.sales_30_days} />
            </Block>
            <Block icon={Wallet} title="Recebido hoje" to={summary.tills ? '/tesouraria' : undefined}>
              <PaymentsToday payments={summary.payments_today} />
            </Block>
          </div>

          {/* What sells, the tills, the day's production */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Block icon={Trophy} title="Mais vendidos">
              <TopProducts today={summary.top_products_today} month={summary.top_products_month} />
            </Block>
            {summary.tills && (
              <Block icon={Landmark} title="Caixas" to="/tesouraria"><Tills tills={summary.tills} /></Block>
            )}
            {summary.production_today && (
              <Block icon={Factory} title="Produção de hoje" to="/producao/historico"><ProductionToday data={summary.production_today} /></Block>
            )}
          </div>

          {/* What will be missing, what expires, the last sales */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {summary.expiring !== undefined && (
              <Block icon={AlertTriangle} tone="text-danger" title="Stock baixo" to="/stock"><LowStock products={summary.low_stock_products} /></Block>
            )}
            {summary.expiring && (
              <Block icon={CalendarClock} tone="text-amber-500" title={'Validades (' + summary.expiring.alert_days + ' dias)'} to="/stock">
                <Expiring data={summary.expiring} />
              </Block>
            )}
            <Block icon={Receipt} title="Últimas vendas" to="/invoices"><RecentDocuments invoices={summary.recent_invoices} /></Block>
          </div>
        </div>
      )}
    </main>
  );
}

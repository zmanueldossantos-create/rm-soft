import { useState, useEffect } from 'react';
import { FileDown, Loader2, FileText } from 'lucide-react';
import Select from '../components/Select';
import { listFiscalYears, listFiscalPeriods } from '../api/fiscal';
import { downloadSaftFile } from '../api/saft';
import { extractErrorMessage } from '../utils/errors';

const MONTH_NAMES = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

export default function SaftExport() {
  const [years, setYears] = useState([]);
  const [selectedYearId, setSelectedYearId] = useState('');
  const [periods, setPeriods] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingPeriods, setLoadingPeriods] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    listFiscalYears()
      .then((data) => {
        setYears(data);
        if (data.length > 0) setSelectedYearId(data[0].id);
      })
      .catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar anos fiscais')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedYearId) return;
    setLoadingPeriods(true);
    setSelectedMonth('');
    listFiscalPeriods(selectedYearId)
      .then((data) => {
        setPeriods(data);
        const closed = data.filter((p) => !p.is_open);
        if (closed.length > 0) setSelectedMonth(String(closed[closed.length - 1].month));
      })
      .catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar períodos')))
      .finally(() => setLoadingPeriods(false));
  }, [selectedYearId]);

  const selectedYear = years.find((y) => y.id === selectedYearId);

  async function handleDownload() {
    setError('');
    setDownloading(true);
    try {
      await downloadSaftFile(selectedYear.year, parseInt(selectedMonth, 10));
    } catch (err) {
      setError(extractErrorMessage(err, 'Erro ao exportar SAF-T'));
    } finally {
      setDownloading(false);
    }
  }

  const monthOptions = periods.map((p) => ({
    value: String(p.month),
    label: MONTH_NAMES[p.month - 1] + (p.is_open ? ' (aberto)' : ' (fechado)'),
  }));

  return (
    <main className="max-w-[1600px] mx-auto px-4 sm:px-6 md:px-8 py-6 sm:py-9">
      <h2 className="font-display font-semibold text-[22px] text-text-primary flex items-center gap-2.5 mb-1">
        <FileText size={22} className="text-accent" />
        Exportação SAF-T
      </h2>
      <p className="text-text-muted text-sm mb-6">
        Exportação mensal para submissão manual ao portal da AGT (Modo Fatura)
      </p>

      {loading && (
        <div className="flex items-center justify-center py-16 text-text-muted text-sm">
          <Loader2 size={18} className="animate-spin mr-2" />
          A carregar...
        </div>
      )}

      {!loading && years.length === 0 && (
        <div className="text-center py-16 text-text-muted text-sm border border-dashed border-border rounded-lg">
          Nenhum ano fiscal disponível - abra um ano em "Períodos" primeiro
        </div>
      )}

      {!loading && years.length > 0 && (
        <div className="bg-bg-elevated border border-border rounded-lg p-6 max-w-lg">
          <div className="flex flex-col gap-4">
            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Ano fiscal</label>
              <Select
                value={selectedYearId}
                onChange={setSelectedYearId}
                options={years.map((y) => ({ value: y.id, label: String(y.year) }))}
                placeholder="Selecionar ano"
              />
            </div>

            <div>
              <label className="text-[11px] font-medium uppercase tracking-wide text-text-muted mb-1.5 block">Mês</label>
              {loadingPeriods ? (
                <div className="flex items-center gap-2 text-text-muted text-sm py-2">
                  <Loader2 size={14} className="animate-spin" />
                  A carregar meses...
                </div>
              ) : (
                <Select
                  value={selectedMonth}
                  onChange={setSelectedMonth}
                  options={monthOptions}
                  placeholder="Selecionar mês"
                />
              )}
            </div>

            {error && (
              <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">
                {error}
              </div>
            )}

            <button
              onClick={handleDownload}
              disabled={downloading || !selectedYear || !selectedMonth}
              className="mt-1 bg-accent hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer text-white font-semibold text-sm rounded-md py-3 flex items-center justify-center gap-2 transition-colors"
            >
              {downloading ? <Loader2 size={17} className="animate-spin" /> : <FileDown size={17} />}
              {downloading ? 'A gerar...' : 'Exportar ficheiro SAF-T'}
            </button>

            <p className="text-[11px] text-text-muted">
              O ficheiro gerado deve ser submetido manualmente no portal da AGT (Modo Fatura).
            </p>
          </div>
        </div>
      )}
    </main>
  );
}

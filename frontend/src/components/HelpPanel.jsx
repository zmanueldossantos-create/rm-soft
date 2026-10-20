// The Ajuda panel: the guide of the screen the user is on, the circuits («Como funciona»), every other screen's guide,
// a search across them, and - for the gestor - the company's Configuração inicial. The guides come from the server
// (app/services/help_guides.py), filtered by the user's permissions: the same text the AI assistant reads.
import { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { HelpCircle, X, Search, ChevronDown, ChevronRight, ChevronLeft, ListChecks, Loader2, ArrowRight, Route } from 'lucide-react';
import { useCan } from '../utils/permissions';
import { getHelpGuides } from '../api/help';
import { getMyCompanySetup } from '../api/company';
import { extractErrorMessage } from '../utils/errors';
import SetupChecklist from './SetupChecklist';

const fold = (text) => text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

// The guide of the screen the user is on: the most precise path that matches (/stock/dashboard before /stock).
function guideForPath(guides, pathname) {
  return guides
    .filter((g) => g.kind === 'page' && (pathname === g.path || pathname.startsWith(g.path + '/')))
    .sort((a, b) => b.path.length - a.path.length)[0] || null;
}

// The guides mentioning every word typed (accents ignored), the circuits first.
function searchGuides(guides, query) {
  const words = fold(query).split(/\s+/).filter(Boolean);
  return guides.filter((g) => {
    const text = fold([g.title, g.intro, ...g.steps.map((s) => s.text), ...g.tips, ...g.errors.flat()].join(' '));
    return words.every((w) => text.includes(w));
  });
}

const sectionTitle = 'text-[11px] font-semibold uppercase tracking-wide text-text-muted';

function GuideBody({ guide, moduleGuide, onOpen, onGo }) {
  return (
    <div className="flex flex-col gap-4 text-[13px] leading-relaxed">
      <p className="text-text-secondary">{guide.intro}</p>
      {moduleGuide && (
        <button type="button" onClick={() => onOpen(moduleGuide.id)} className="self-start flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-[12px] font-medium text-accent hover:border-accent transition-colors cursor-pointer">
          <Route size={13} /> Como funciona: {moduleGuide.title}
        </button>
      )}
      <div>
        <p className={sectionTitle + ' mb-2'}>Passo a passo</p>
        <ol className="flex flex-col gap-2">
          {guide.steps.map((step, i) => (
            <li key={i} className="flex gap-2.5">
              <span className="shrink-0 w-5 h-5 rounded-full bg-accent/15 text-accent text-[11px] font-semibold flex items-center justify-center mt-0.5">{i + 1}</span>
              <span className="flex-1 text-text-primary">{step.text}</span>
              {step.link && (
                <button type="button" onClick={() => onGo(step.link)} className="shrink-0 self-start flex items-center gap-1 px-2 py-0.5 rounded border border-border text-[11px] font-medium text-accent hover:border-accent transition-colors cursor-pointer">
                  Ir <ArrowRight size={11} />
                </button>
              )}
            </li>
          ))}
        </ol>
      </div>
      {guide.tips.length > 0 && (
        <div>
          <p className={sectionTitle + ' mb-2'}>Dicas</p>
          <ul className="flex flex-col gap-1.5 list-disc pl-5 text-text-secondary">
            {guide.tips.map((tip, i) => <li key={i}>{tip}</li>)}
          </ul>
        </div>
      )}
      {guide.errors.length > 0 && (
        <div>
          <p className={sectionTitle + ' mb-2'}>Erros frequentes</p>
          <div className="flex flex-col gap-2">
            {guide.errors.map(([problem, solution], i) => (
              <div key={i} className="border-l-2 border-amber-500 bg-amber-500/5 rounded-r px-3 py-2">
                <p className="font-medium text-text-primary">{problem}</p>
                <p className="text-text-secondary">{solution}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// A guide in a list: its title, opened in full on click.
function GuideLink({ guide, onOpen }) {
  return (
    <button type="button" onClick={() => onOpen(guide.id)} className="w-full flex items-center gap-2 px-3.5 py-2.5 border border-border rounded-md text-left text-sm font-medium text-text-primary hover:border-accent transition-colors cursor-pointer">
      {guide.kind === 'module' && <Route size={14} className="text-accent shrink-0" />}
      <span className="flex-1">{guide.title}</span>
      <ChevronRight size={15} className="text-text-muted" />
    </button>
  );
}

// The gestor's Configuração inicial, folded to its progress until opened.
function SetupSection() {
  const [setup, setSetup] = useState(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    getMyCompanySetup().then(setSetup).catch(() => setSetup(null));
  }, []);
  return (
    <div className="border border-border rounded-md overflow-hidden">
      <button type="button" onClick={() => setOpen((v) => !v)} className="w-full flex items-center gap-2 px-3.5 py-2.5 text-left text-sm font-medium text-text-primary hover:bg-bg-inset transition-colors cursor-pointer">
        <ListChecks size={15} className="text-accent" />
        Configuração inicial
        <span className={'ml-auto font-mono text-[12px] ' + (setup?.complete ? 'text-success' : 'text-text-muted')}>
          {setup ? `${setup.required_done} / ${setup.required_total}` : <Loader2 size={13} className="animate-spin" />}
        </span>
        {open ? <ChevronDown size={15} className="text-text-muted" /> : <ChevronRight size={15} className="text-text-muted" />}
      </button>
      {open && setup && <div className="px-3.5 pb-3.5 pt-1"><SetupChecklist data={setup} compact /></div>}
    </div>
  );
}

export default function HelpPanel({ open, onClose }) {
  const location = useLocation();
  const navigate = useNavigate();
  const can = useCan();
  const [guides, setGuides] = useState(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState(null); // a guide opened from a list (with «Voltar»)

  useEffect(() => {
    if (!open || guides) return;
    getHelpGuides().then(setGuides).catch((err) => setError(extractErrorMessage(err, 'Erro ao carregar a ajuda')));
  }, [open, guides]);
  useEffect(() => { setSelectedId(null); }, [location.pathname]);

  if (!open) return null;
  const list = guides || [];
  const byId = Object.fromEntries(list.map((g) => [g.id, g]));
  const current = guideForPath(list, location.pathname);
  const selected = selectedId ? byId[selectedId] : null;
  const results = query.trim() ? searchGuides(list, query) : null;
  const modules = list.filter((g) => g.kind === 'module');
  const pages = list.filter((g) => g.kind === 'page' && g.id !== current?.id);
  const openGuide = (id) => { setSelectedId(id); setQuery(''); };
  const body = (guide) => <GuideBody guide={guide} moduleGuide={guide.module ? byId[guide.module] : null} onOpen={openGuide} onGo={navigate} />;

  return (
    <aside className="fixed right-0 top-14 bottom-11 z-40 w-full sm:w-[460px] bg-bg-elevated border-l border-border shadow-2xl flex flex-col">
      <div className="flex items-center gap-3 px-5 py-3.5 border-b border-border">
        <div className="w-9 h-9 rounded-md bg-accent/10 flex items-center justify-center"><HelpCircle size={18} className="text-accent" /></div>
        <div className="flex-1">
          <p className="font-display font-semibold text-text-primary">Ajuda</p>
          <p className="text-[12px] text-text-muted">Guias de utilização do RM SOFT</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Fechar ajuda" className="w-9 h-9 flex items-center justify-center border border-border rounded-md text-text-muted hover:text-text-primary hover:border-accent transition-colors cursor-pointer">
          <X size={16} />
        </button>
      </div>
      <div className="px-5 py-3 border-b border-border">
        <div className="relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
          <input
            type="text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Pesquisar na ajuda... (ex.: fechar caixa)"
            className="w-full bg-bg-inset border border-border rounded-md pl-9 pr-3 py-2 text-sm text-text-primary outline-none focus:border-accent transition-colors"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin px-5 py-4 flex flex-col gap-4 *:shrink-0">
        {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3.5 py-2.5 text-[13px] rounded-r">{error}</div>}
        {!guides && !error && (
          <div className="flex items-center justify-center py-16 text-text-muted text-sm"><Loader2 size={18} className="animate-spin mr-2" />A carregar...</div>
        )}
        {guides && results && (
          <>
            <p className={sectionTitle}>{results.length} guia(s) encontrado(s)</p>
            {results.length === 0 && <p className="text-sm text-text-muted">Nenhum guia fala disso ainda. Pode perguntar ao suporte RM SOFT.</p>}
            {results.map((g) => <GuideLink key={g.id} guide={g} onOpen={openGuide} />)}
          </>
        )}
        {guides && !results && selected && (
          <div>
            <button type="button" onClick={() => setSelectedId(null)} className="flex items-center gap-1 text-[12px] font-medium text-text-muted hover:text-text-primary mb-3 cursor-pointer">
              <ChevronLeft size={14} /> Voltar
            </button>
            <p className={sectionTitle + ' mb-1'}>{selected.kind === 'module' ? 'Como funciona' : 'Ecrã'}</p>
            <h3 className="font-display font-semibold text-[17px] text-text-primary mb-3">{selected.title}</h3>
            {body(selected)}
          </div>
        )}
        {guides && !results && !selected && (
          <>
            {can('company:manage') && <SetupSection />}
            {current ? (
              <div>
                <p className={sectionTitle + ' mb-2'}>Neste ecrã</p>
                <h3 className="font-display font-semibold text-[17px] text-text-primary mb-3">{current.title}</h3>
                {body(current)}
              </div>
            ) : (
              <p className="text-sm text-text-muted">Este ecrã ainda não tem guia. Escolha um guia abaixo ou pesquise.</p>
            )}
            {modules.length > 0 && (
              <div className="flex flex-col gap-2">
                <p className={sectionTitle}>Como funciona</p>
                {modules.map((g) => <GuideLink key={g.id} guide={g} onOpen={openGuide} />)}
              </div>
            )}
            {pages.length > 0 && (
              <div className="flex flex-col gap-2">
                <p className={sectionTitle}>Outros ecrãs</p>
                {pages.map((g) => <GuideLink key={g.id} guide={g} onOpen={openGuide} />)}
              </div>
            )}
          </>
        )}
      </div>
    </aside>
  );
}

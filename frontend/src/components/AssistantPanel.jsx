import { useState, useEffect, useRef } from 'react';
import { Bot, X, Send, Loader2, Plus, MessageSquare, ChevronDown } from 'lucide-react';
import { listAiConversations, getAiMessages, askAssistant } from '../api/ai';
import { extractErrorMessage } from '../utils/errors';

const SUGGESTIONS = [
  'Quanto vendi hoje?',
  'Que produtos estão abaixo do stock mínimo?',
  'Quem me deve dinheiro?',
  'Quanto dinheiro há nas caixas?',
];

// **bold** inside a line, as React elements (never raw HTML)
function inline(text, keyPrefix) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4
      ? <strong key={keyPrefix + i} className="font-semibold text-text-primary">{part.slice(2, -2)}</strong>
      : <span key={keyPrefix + i}>{part}</span>,
  );
}

// The assistant's answer: paragraphs, «- » lists, «#» titles and | tables |, the little markdown the AI writes.
function Answer({ text }) {
  const lines = text.split('\n');
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (trimmed.startsWith('|')) {
      const rows = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        const cells = lines[i].trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
        if (!cells.every((c) => /^:?-{2,}:?$/.test(c))) rows.push(cells);
        i += 1;
      }
      blocks.push(
        <div key={'t' + i} className="overflow-x-auto my-1">
          <table className="text-[12px] border-collapse">
            <tbody>
              {rows.map((cells, r) => (
                <tr key={r} className={r === 0 ? 'font-semibold' : 'border-t border-border'}>
                  {cells.map((c, k) => <td key={k} className="px-2 py-1 align-top">{inline(c, r + '-' + k + '-')}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^[-*•]\s+/.test(trimmed)) {
      const items = [];
      while (i < lines.length && /^[-*•]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*•]\s+/, ''));
        i += 1;
      }
      blocks.push(
        <ul key={'l' + i} className="list-disc pl-5 my-1 flex flex-col gap-0.5">
          {items.map((it, k) => <li key={k}>{inline(it, k + '-')}</li>)}
        </ul>,
      );
      continue;
    }
    if (trimmed) {
      const title = /^#{1,4}\s+/.test(trimmed);
      blocks.push(<p key={'p' + i} className={title ? 'font-semibold text-text-primary mt-1' : ''}>{inline(trimmed.replace(/^#{1,4}\s+/, ''), i + '-')}</p>);
    }
    i += 1;
  }
  return <div className="flex flex-col gap-1.5">{blocks}</div>;
}

// The AI assistant, in a panel on the right: the user's conversations, a question, the answer. The company and the
// permissions are the server's business - the panel only shows what comes back.
export default function AssistantPanel({ open, onClose, status, onStatus }) {
  const [conversations, setConversations] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    listAiConversations().then(setConversations).catch(() => setConversations([]));
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  function newConversation() {
    setConversationId(null);
    setMessages([]);
    setError('');
    setHistoryOpen(false);
    inputRef.current?.focus();
  }

  async function openConversation(id) {
    setHistoryOpen(false);
    setError('');
    try {
      setMessages(await getAiMessages(id));
      setConversationId(id);
    } catch (err) {
      setError(extractErrorMessage(err, 'Não foi possível abrir a conversa'));
    }
  }

  async function send(text) {
    const message = (text ?? question).trim();
    if (!message || sending) return;
    setError('');
    setSending(true);
    setQuestion('');
    setMessages((prev) => [...prev, { id: 'pending', role: 'user', content: message }]);
    try {
      const result = await askAssistant(message, conversationId);
      setMessages((prev) => [...prev.filter((m) => m.id !== 'pending'), { id: 'q' + result.message.id, role: 'user', content: message }, result.message]);
      setConversationId(result.conversation.id);
      onStatus({ ...status, used: result.used, limit: result.limit });
      if (!conversationId) listAiConversations().then(setConversations).catch(() => {});
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== 'pending'));
      setQuestion(message);
      setError(extractErrorMessage(err, 'O assistente não respondeu'));
    } finally {
      setSending(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  if (!open) return null;
  const limitReached = status.used >= status.limit;
  const current = conversations.find((c) => c.id === conversationId);

  return (
    <aside className="fixed right-0 top-14 bottom-11 z-40 w-full sm:w-[460px] bg-bg-elevated border-l border-border shadow-2xl flex flex-col">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <div className="w-8 h-8 rounded-md bg-accent/10 flex items-center justify-center shrink-0">
          <Bot size={16} className="text-accent" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-display font-semibold text-sm text-text-primary">Assistente</p>
          <p className="text-[11px] text-text-muted font-mono">{status.used} / {status.limit} mensagens este mês</p>
        </div>
        <button type="button" onClick={newConversation} title="Nova conversa" className="flex items-center gap-1 border border-border hover:border-accent text-text-primary text-[12px] rounded-md px-2.5 py-1.5 cursor-pointer">
          <Plus size={13} />Nova
        </button>
        <button type="button" onClick={onClose} aria-label="Fechar" className="flex items-center justify-center w-8 h-8 rounded-md border border-border text-text-muted hover:text-text-primary hover:border-accent cursor-pointer">
          <X size={15} />
        </button>
      </div>

      <div className="relative px-4 py-2 border-b border-border">
        <button type="button" onClick={() => setHistoryOpen((v) => !v)} className="w-full flex items-center gap-2 text-[12px] text-text-muted hover:text-text-primary cursor-pointer">
          <MessageSquare size={13} />
          <span className="truncate flex-1 text-left">{current ? current.title : conversationId ? 'Conversa' : 'Nova conversa'}</span>
          <span className="shrink-0">{conversations.length} {conversations.length === 1 ? 'conversa' : 'conversas'}</span>
          <ChevronDown size={13} className={historyOpen ? 'rotate-180 transition-transform' : 'transition-transform'} />
        </button>
        {historyOpen && (
          <div className="absolute left-2 right-2 top-full mt-1 z-10 bg-bg-elevated border border-border rounded-md shadow-xl max-h-72 overflow-y-auto scrollbar-thin">
            {conversations.length === 0 && <p className="text-[12px] text-text-muted px-3 py-3">Ainda sem conversas</p>}
            {conversations.map((c) => (
              <button key={c.id} type="button" onClick={() => openConversation(c.id)}
                className={'w-full text-left px-3 py-2 text-[12px] hover:bg-bg-inset cursor-pointer border-b border-border last:border-0 ' + (c.id === conversationId ? 'text-accent' : 'text-text-primary')}>
                <span className="block truncate">{c.title}</span>
                <span className="block text-[11px] text-text-muted font-mono">{new Date(c.updated_at).toLocaleString('pt-PT', { dateStyle: 'short', timeStyle: 'short' })}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-4 py-4 flex flex-col gap-3">
        {messages.length === 0 && !sending && (
          <div className="flex flex-col gap-3 mt-2">
            <p className="text-[13px] text-text-muted">Pergunte sobre o stock, as vendas, as dívidas de clientes e fornecedores, as caixas ou um documento.</p>
            <div className="flex flex-col gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" disabled={limitReached || !status.available} onClick={() => send(s)}
                  className="text-left text-[13px] border border-border hover:border-accent rounded-md px-3 py-2 text-text-primary cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={m.role === 'user' ? 'self-end max-w-[85%]' : 'self-start max-w-[95%]'}>
            <div className={'text-[13px] leading-relaxed rounded-lg px-3.5 py-2.5 ' + (m.role === 'user' ? 'bg-accent text-white whitespace-pre-wrap' : 'bg-bg-inset text-text-primary border border-border')}>
              {m.role === 'user' ? m.content : <Answer text={m.content} />}
            </div>
          </div>
        ))}
        {sending && (
          <div className="self-start flex items-center gap-2 text-[12px] text-text-muted bg-bg-inset border border-border rounded-lg px-3.5 py-2.5">
            <Loader2 size={13} className="animate-spin" />A consultar os dados...
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="border-t border-border px-4 py-3 flex flex-col gap-2">
        {!status.available && <div className="bg-amber-500/10 border-l-2 border-amber-500 text-amber-500 [.light_&]:text-amber-700 px-3 py-2 text-[12px] rounded-r">O assistente ainda não está configurado na plataforma.</div>}
        {limitReached && <div className="bg-amber-500/10 border-l-2 border-amber-500 text-amber-500 [.light_&]:text-amber-700 px-3 py-2 text-[12px] rounded-r">Limite mensal de mensagens atingido.</div>}
        {error && <div className="bg-danger/10 border-l-2 border-danger text-danger px-3 py-2 text-[12px] rounded-r">{error}</div>}
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            maxLength={2000}
            disabled={sending || limitReached || !status.available}
            placeholder="Escreva a sua pergunta... (Enter para enviar)"
            className="flex-1 resize-none bg-bg-inset border border-border rounded-md px-3 py-2 text-[13px] text-text-primary outline-none focus:border-accent transition-colors disabled:opacity-50"
          />
          <button type="button" onClick={() => send()} disabled={sending || !question.trim() || limitReached || !status.available} aria-label="Enviar"
            className="flex items-center justify-center w-10 h-10 rounded-md bg-accent hover:bg-accent-hover text-white cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed shrink-0">
            {sending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </aside>
  );
}

import { useCallback, useEffect, useRef, useState } from 'react';
import { getCustomerDisplay } from '../api/customerDisplay';

// The Caixa feeds its customer's screen (pages/EcraCliente.jsx, opened on the till's second monitor) through a
// BroadcastChannel: same browser, same PC - instant, and it keeps working with no network. One channel per till.
//
// Messages (Caixa -> screen):
//   { type: 'idle' }                                       no sale: the welcome and the pictures
//   { type: 'sale', lines, discount, retention, total, received, change }
//   { type: 'done', document, total, change }              the sale is made: «Obrigado» for a few seconds
// (screen -> Caixa): { type: 'hello' } when it opens - the Caixa answers with what it shows now.

export const displayChannelName = (posId) => 'rm_ecra_cliente:' + posId;

export function displayUrl(posId, activityId) {
  return '/ecra-cliente?pos=' + encodeURIComponent(posId) + '&activity=' + encodeURIComponent(activityId);
}

export function useCustomerDisplay(posId, activityId) {
  const [allowed, setAllowed] = useState(false);
  const channelRef = useRef(null);
  const lastRef = useRef({ type: 'idle' });

  // the plan's option: without it, the Caixa shows no button and sends nothing
  useEffect(() => {
    let alive = true;
    setAllowed(false);
    if (!activityId) return undefined;
    getCustomerDisplay(activityId)
      .then((d) => { if (alive) setAllowed(!!d.allowed); })
      .catch(() => { if (alive) setAllowed(false); });
    return () => { alive = false; };
  }, [activityId]);

  useEffect(() => {
    if (!allowed || !posId || typeof BroadcastChannel === 'undefined') return undefined;
    const channel = new BroadcastChannel(displayChannelName(posId));
    channel.onmessage = (event) => {
      if (event.data?.type === 'hello') channel.postMessage(lastRef.current);
    };
    channelRef.current = channel;
    channel.postMessage(lastRef.current);
    return () => { channel.close(); channelRef.current = null; };
  }, [allowed, posId]);

  const send = useCallback((message) => {
    lastRef.current = message.type === 'done' ? { type: 'idle' } : message;
    try {
      channelRef.current?.postMessage(message);
    } catch {
      // a closed channel: the screen is not open - nothing to do
    }
  }, []);

  const open = useCallback(() => {
    if (!posId || !activityId) return;
    window.open(displayUrl(posId, activityId), 'rm_ecra_cliente_' + posId, 'popup,width=1024,height=768');
  }, [posId, activityId]);

  return { allowed, send, open };
}

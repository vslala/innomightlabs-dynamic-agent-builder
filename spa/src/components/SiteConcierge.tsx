/**
 * Mira, the site concierge: the InnoMight Labs chat widget on our own public pages.
 *
 * embed.js mounts once and has no teardown, so it is loaded a single time and
 * hidden with CSS on dashboard routes, where the launcher would sit on top of the
 * workspace's own controls. The `pk_live_` key is public by design; the API
 * only accepts it from the key's allowed origins.
 */

import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

const EMBED_SRC = 'https://cdn.innomightlabs.com/embed.js';
const CONCIERGE_API_KEY = 'pk_live_2c5f4f7f5f1d0eccf5d5532a4fd04973';

export function SiteConcierge() {
  const { pathname } = useLocation();
  const hidden = pathname === '/dashboard' || pathname.startsWith('/dashboard/');

  useEffect(() => {
    if (document.querySelector(`script[src="${EMBED_SRC}"]`)) return;
    const script = document.createElement('script');
    script.src = EMBED_SRC;
    script.async = true;
    script.dataset.apiKey = CONCIERGE_API_KEY;
    script.dataset.launcherLabel = 'Ask Mira';
    script.dataset.greeting = "Hi, I'm Mira. Ask me anything about InnoMight Labs.";
    script.dataset.placeholder = 'Ask about agents, automations, pricing…';
    document.body.appendChild(script);
  }, []);

  useEffect(() => {
    document.body.toggleAttribute('data-concierge-hidden', hidden);
  }, [hidden]);

  return null;
}

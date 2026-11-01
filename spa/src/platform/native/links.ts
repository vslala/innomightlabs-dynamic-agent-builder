import { App } from "@capacitor/app";
import { Browser } from "@capacitor/browser";
import { parseAppLink } from "../appLinks";
import type { Links } from "../types";

/**
 * The system browser (SFSafariViewController / Custom Tabs) for every page that leaves the app, and the URL
 * scheme for coming back. Google refuses sign-in inside a web view, so nothing is opened in this one.
 */
export function createNativeLinks(scheme: string): Links {
  const open = async (url: string) => {
    await Browser.open({ url });
  };

  return {
    returnTo: (path) => `${scheme}://return${path}`,
    openAuthPage: async (url) => {
      await open(url);
      return true;
    },
    openExternal: open,
    onAppLink: (handler) => {
      // The same link can arrive twice: as the launch URL of a cold start and as an appUrlOpen event.
      const seen = new Set<string>();
      const receive = (url: string | undefined) => {
        if (!url || seen.has(url)) return;
        seen.add(url);
        const link = parseAppLink(url, scheme);
        if (!link) return;
        // The sign-in sheet is still on top; close it (it is already gone if the person closed it).
        void Browser.close().catch(() => {});
        handler(link);
      };
      const listener = App.addListener("appUrlOpen", ({ url }) => receive(url));
      void App.getLaunchUrl().then((launch) => receive(launch?.url));
      return () => void listener.then((handle) => handle.remove());
    },
  };
}

import { useEffect, useState } from "react";
import { ArrowLeft, Download, PackageOpen } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { Footer } from "../components/Footer";
import { Navbar } from "../components/Navbar";
import { MarkdownRenderer } from "../components/ui/markdown-renderer";
import { downloadsApiService } from "../services/downloads";
import type { PluginDownloadDetail } from "../types/downloads";
import styles from "./Downloads.module.css";

function PluginIcon({ plugin }: { plugin: PluginDownloadDetail }) {
  return (
    <div className={styles.iconWrap}>
      {plugin.icon_url ? (
        <img src={plugin.icon_url} alt="" />
      ) : (
        <PackageOpen size={30} className={styles.fallbackIcon} aria-hidden="true" />
      )}
    </div>
  );
}

export function PluginDetailsPage() {
  const { pluginId } = useParams<{ pluginId: string }>();
  const [plugin, setPlugin] = useState<PluginDownloadDetail | null>(null);
  const [status, setStatus] = useState<"loading" | "success" | "error" | "missing">("loading");

  useEffect(() => {
    let active = true;

    const loadPlugin = async () => {
      if (!pluginId) {
        setStatus("missing");
        return;
      }

      try {
        setStatus("loading");
        const response = await downloadsApiService.getPlugin(pluginId);
        if (!active) {
          return;
        }
        setPlugin(response);
        setStatus("success");
      } catch {
        if (!active) {
          return;
        }
        setStatus("error");
      }
    };

    loadPlugin();

    return () => {
      active = false;
    };
  }, [pluginId]);

  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <div className={styles.main}>
          <Link className={styles.backLink} to="/downloads">
            <ArrowLeft size={18} aria-hidden="true" />
            Downloads
          </Link>

          {status === "loading" && (
            <div className={styles.stateNotice}>Loading plugin details...</div>
          )}

          {(status === "error" || status === "missing") && (
            <div className={styles.stateNotice}>
              This plugin detail page is unavailable. Please return to downloads and try again.
            </div>
          )}

          {status === "success" && plugin && (
            <section className={styles.detailLayout}>
              <aside className={styles.sidePanel}>
                <div className={styles.cardHeader}>
                  <PluginIcon plugin={plugin} />
                  <div className={styles.meta}>
                    <div className={styles.kind}>{plugin.kind}</div>
                    <h1 className={styles.name}>{plugin.name}</h1>
                  </div>
                </div>
                <p className={styles.tagline}>{plugin.tagline}</p>
                <p className={styles.description}>{plugin.description}</p>
                <div className={styles.facts}>
                  <span className={styles.pill}>{plugin.platform}</span>
                  <span className={styles.pill}>v{plugin.version}</span>
                </div>
                <a className={styles.primaryButton} href={plugin.download_url}>
                  <Download size={18} aria-hidden="true" />
                  Download
                </a>
              </aside>

              <article className={styles.readmePanel}>
                <MarkdownRenderer content={plugin.readme_markdown} className={styles.markdown} />
              </article>
            </section>
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}

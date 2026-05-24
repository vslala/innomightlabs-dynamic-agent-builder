import { useEffect, useState } from "react";
import { Download, Info, PackageOpen } from "lucide-react";
import { Link } from "react-router-dom";
import { Footer } from "../components/Footer";
import { Navbar } from "../components/Navbar";
import { downloadsApiService } from "../services/downloads";
import type { PluginDownloadSummary } from "../types/downloads";
import styles from "./Downloads.module.css";

function formatBytes(bytes?: number | null): string | null {
  if (!bytes) {
    return null;
  }
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function PluginIcon({ plugin }: { plugin: PluginDownloadSummary }) {
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

export function DownloadsPage() {
  const [plugins, setPlugins] = useState<PluginDownloadSummary[]>([]);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");

  useEffect(() => {
    let active = true;

    const loadPlugins = async () => {
      try {
        setStatus("loading");
        const response = await downloadsApiService.listPlugins();
        if (!active) {
          return;
        }
        setPlugins(response.plugins);
        setStatus("success");
      } catch {
        if (!active) {
          return;
        }
        setStatus("error");
      }
    };

    loadPlugins();

    return () => {
      active = false;
    };
  }, []);

  return (
    <>
      <Navbar />
      <main className={styles.page}>
        <div className={styles.main}>
          <section className={styles.hero}>
            <span className={styles.eyebrow}>Innomight downloads</span>
            <h1 className={styles.title}>Plugins for building where you already work</h1>
            <p className={styles.subtitle}>
              Add Innomight to your editor and website workflows with packaged extensions that connect directly to your automations.
            </p>
          </section>

          {status === "loading" && (
            <div className={styles.stateNotice}>Loading plugin downloads...</div>
          )}

          {status === "error" && (
            <div className={styles.stateNotice}>
              Downloads are temporarily unavailable. Please refresh to generate new download links.
            </div>
          )}

          {status === "success" && (
            <section className={styles.grid} aria-label="Available plugins">
              {plugins.map((plugin) => {
                const size = formatBytes(plugin.size_bytes);
                return (
                  <article key={plugin.id} className={styles.pluginCard}>
                    <div className={styles.cardHeader}>
                      <PluginIcon plugin={plugin} />
                      <div className={styles.meta}>
                        <div className={styles.kind}>{plugin.kind}</div>
                        <h2 className={styles.name}>{plugin.name}</h2>
                      </div>
                    </div>

                    <p className={styles.tagline}>{plugin.tagline}</p>
                    <p className={styles.description}>{plugin.description}</p>

                    <div className={styles.facts}>
                      <span className={styles.pill}>{plugin.platform}</span>
                      <span className={styles.pill}>v{plugin.version}</span>
                      {size && <span className={styles.pill}>{size}</span>}
                    </div>

                    <div className={styles.actions}>
                      <a className={styles.primaryButton} href={plugin.download_url}>
                        <Download size={18} aria-hidden="true" />
                        Download
                      </a>
                      <Link className={styles.secondaryButton} to={`/downloads/plugins/${plugin.id}`}>
                        <Info size={18} aria-hidden="true" />
                        Details
                      </Link>
                    </div>
                  </article>
                );
              })}
            </section>
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}

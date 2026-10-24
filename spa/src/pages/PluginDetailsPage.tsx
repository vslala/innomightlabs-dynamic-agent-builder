import { useEffect, useState } from "react";
import { ArrowLeft, Download, PackageOpen } from "lucide-react";
import { Link, useMatch } from "react-router-dom";
import { Footer } from "../components/Footer";
import { Navbar } from "../components/Navbar";
import { MarkdownRenderer } from "../components/ui/markdown-renderer";
import { downloadsApiService } from "../services/downloads";
import type { PluginDownloadDetail } from "../types/downloads";
import styles from "./Downloads.module.css";

// Files are in plugins/wordpress/innomight-ai-search/.wordpress-org and are published by the public-pages Vite plugin.
const WORDPRESS_SEARCH_DEMOS = [
  {
    file: "demo",
    poster: "screenshot-4.png",
    title: "Find posts and ask a follow-up",
    description: "Search the site, ask the agent for posts on a topic, then narrow the answer with a follow-up question.",
  },
  {
    file: "demo-microservices",
    poster: "screenshot-7.png",
    title: "Get a reading order and an article summary",
    description: "Search a topic, ask in which order to read every match, have one article summarised from its full text, and find newer related posts.",
  },
] as const;

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
  // Fixed public routes do not populate useParams; match the URL for both forms.
  const pluginId = useMatch("/downloads/plugins/:pluginId")?.params.pluginId;
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
                {plugin.id === "wordpress-ai-search" && (
                  <section className={styles.demoSection} aria-labelledby="wordpress-search-demo-title">
                    <h2 id="wordpress-search-demo-title" className={styles.demoHeading}>
                      See WordPress AI Search in action
                    </h2>
                    <p className={styles.demoDescription}>
                      Two real recordings of a visitor using the chat on a live blog. English captions are available in each player.
                    </p>
                    {WORDPRESS_SEARCH_DEMOS.map((demo) => (
                      <figure key={demo.file} className={styles.demoFigure}>
                        <figcaption>
                          <h3 id={`${demo.file}-title`} className={styles.demoTitle}>{demo.title}</h3>
                          <p id={`${demo.file}-description`} className={styles.demoDescription}>{demo.description}</p>
                        </figcaption>
                        <video
                          className={styles.demoVideo}
                          controls
                          playsInline
                          preload="none"
                          poster={`${import.meta.env.BASE_URL}plugins/wordpress-ai-search/${demo.poster}`}
                          aria-labelledby={`${demo.file}-title`}
                          aria-describedby={`${demo.file}-description`}
                        >
                          <source src={`${import.meta.env.BASE_URL}plugins/wordpress-ai-search/${demo.file}.mp4`} type="video/mp4" />
                          <track
                            kind="captions"
                            src={`${import.meta.env.BASE_URL}plugins/wordpress-ai-search/${demo.file}.vtt`}
                            srcLang="en"
                            label="English"
                            default
                          />
                          Your browser does not support embedded video. <a href={`${import.meta.env.BASE_URL}plugins/wordpress-ai-search/${demo.file}.mp4`}>Download the demo video</a>.
                        </video>
                      </figure>
                    ))}
                  </section>
                )}
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

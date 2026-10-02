import { Link } from "react-router-dom";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../../components/ui/tabs";
import styles from "./WidgetSnippets.module.css";

interface WidgetSnippetsProps {
  publicKey: string;
}

/** Install snippets for both widgets that run on a widget key: the classic script and the iframe embed. */
export function WidgetSnippets({ publicKey }: WidgetSnippetsProps) {
  return (
    <div className={styles.snippets}>
      <p className={styles.title}>Integration Code</p>
      <Tabs defaultValue="embedded">
        <TabsList>
          <TabsTrigger value="embedded">Embedded widget</TabsTrigger>
          <TabsTrigger value="classic">Classic widget</TabsTrigger>
        </TabsList>

        <TabsContent value="embedded">
          <p className={styles.hint}>
            Runs in its own frame, so your site's styles can't affect it. Add <code>data-mode="inline"</code> and{" "}
            <code>data-target</code> to place it inside a container instead of a floating button. See{" "}
            <Link to="/docs/quick-start#embedded-widget">all options</Link>.
          </p>
          <pre className={styles.code}>
{`<script
  src="https://cdn.innomightlabs.com/embed.js"
  data-api-key="${publicKey}"
  async></script>`}
          </pre>
        </TabsContent>

        <TabsContent value="classic">
          <p className={styles.hint}>Add this snippet to your website to embed the chat widget:</p>
          <pre className={styles.code}>
{`<script>
  (function () {
    var script = document.createElement('script');
    var widgetVersion = Math.floor(Date.now() / 300000);
    script.src = 'https://cdn.innomightlabs.com/widget.js?v=' + widgetVersion;
    script.async = true;
    script.onload = function () {
      InnomightChat.init({
        apiKey: '${publicKey}',
        position: 'bottom-right'
      });
    };
    document.head.appendChild(script);
  })();
</script>`}
          </pre>
        </TabsContent>
      </Tabs>
    </div>
  );
}

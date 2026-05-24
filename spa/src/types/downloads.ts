export interface PluginDownloadSummary {
  id: string;
  name: string;
  kind: string;
  tagline: string;
  description: string;
  version: string;
  platform: string;
  filename: string;
  download_url: string;
  icon_url?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
}

export interface PluginDownloadDetail extends PluginDownloadSummary {
  readme_markdown: string;
}

export interface PluginDownloadsResponse {
  plugins: PluginDownloadSummary[];
}

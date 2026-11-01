import { Directory, Filesystem } from "@capacitor/filesystem";
import { Share } from "@capacitor/share";
import type { Files } from "../types";

/** A web view can't download: the file goes to the app's cache and out through the share sheet. */
export function createNativeFiles(): Files {
  return {
    saveOrShare: async ({ data, filename }) => {
      const { uri } = await Filesystem.writeFile({ path: filename, data: await base64Of(data), directory: Directory.Cache });
      await Share.share({ files: [uri] });
    },
  };
}

async function base64Of(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

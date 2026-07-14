import { useState, useEffect } from "react";

import apiClient from "./client";

/**
 * Fetching files that now require a token.
 *
 * `<img src="...">` cannot send an Authorization header — the browser just does
 * a plain GET. Since /uploads is authenticated now, images have to be fetched
 * with the token and turned into a blob: URL.
 *
 * The cache is not an optimisation, it's a necessity: the same avatar appears on
 * every card, every comment and every timeline row. Without it, one board render
 * would fire dozens of identical requests and leak an object URL for each.
 */
const cache = new Map(); // path -> Promise<objectURL>

export function fetchFileUrl(path) {
  if (!path) return Promise.resolve(null);

  if (!cache.has(path)) {
    const promise = apiClient
      .get(path, { responseType: "blob" })
      .then((r) => URL.createObjectURL(r.data))
      .catch((err) => {
        // Don't cache a failure forever — a transient 500 shouldn't leave a
        // permanently broken avatar until the tab is reloaded.
        cache.delete(path);
        throw err;
      });
    cache.set(path, promise);
  }
  return cache.get(path);
}

/** Blob URLs are per-document; drop them all when the user signs out. */
export function clearFileCache() {
  for (const promise of cache.values()) {
    promise.then((url) => url && URL.revokeObjectURL(url)).catch(() => {});
  }
  cache.clear();
}

/** Resolve an authenticated file path to something an <img> or <a> can use. */
export function useFileUrl(path) {
  const [url, setUrl] = useState(null);

  useEffect(() => {
    let cancelled = false;
    if (!path) {
      setUrl(null);
      return undefined;
    }

    fetchFileUrl(path)
      .then((objectUrl) => {
        if (!cancelled) setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setUrl(null); // fall back to initials / the paperclip
      });

    // Deliberately does NOT revoke on unmount: the URL is shared via the cache
    // and another card is very likely still showing it.
    return () => {
      cancelled = true;
    };
  }, [path]);

  return url;
}

/** Download an attachment under its original filename, with the token attached. */
export async function downloadFile(path, filename) {
  const { data } = await apiClient.get(path, { responseType: "blob" });
  const url = URL.createObjectURL(data);

  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "download";
  document.body.appendChild(a);
  a.click();
  a.remove();

  URL.revokeObjectURL(url);
}

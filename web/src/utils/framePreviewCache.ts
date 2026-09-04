const prefetchedUrls = new Set<string>();

export async function getCachedPreviewObjectUrl(
  url: string,
): Promise<string | undefined> {
  return url;
}

export function prefetchFramePreviewUrls(urls: (string | null | undefined)[]) {
  urls.forEach((url) => {
    if (!url || prefetchedUrls.has(url)) {
      return;
    }
    prefetchedUrls.add(url);
    fetch(url);
  });
}

export function clearFramePreviewCache() {
  prefetchedUrls.clear();
}

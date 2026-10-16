const PREFETCH_BATCH_SIZE = 5;
const PREFETCH_TIMEOUT_MS = 15000;

const prefetchedUrls = new Set<string>();
const inFlightUrls = new Map<string, Promise<void>>();
const inFlightControllers = new Map<string, AbortController>();
/** Bumped on clear so in-flight fetches cannot re-populate the cache. */
let cacheEpoch = 0;

function uniqueUrls(urls: (string | null | undefined)[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const url of urls) {
    if (!url || seen.has(url)) {
      continue;
    }
    seen.add(url);
    result.push(url);
  }
  return result;
}

async function prefetchOne(url: string): Promise<void> {
  if (prefetchedUrls.has(url)) {
    return;
  }
  const inFlight = inFlightUrls.get(url);
  if (inFlight) {
    return inFlight;
  }

  const epoch = cacheEpoch;
  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(),
    PREFETCH_TIMEOUT_MS,
  );

  const promise = fetch(url, { signal: controller.signal })
    .then(() => {
      if (epoch === cacheEpoch) {
        prefetchedUrls.add(url);
      }
    })
    .catch(() => {
      // Best-effort warm of the browser cache; allow a later retry.
    })
    .finally(() => {
      window.clearTimeout(timeout);
      if (inFlightControllers.get(url) === controller) {
        inFlightControllers.delete(url);
      }
      if (inFlightUrls.get(url) === promise) {
        inFlightUrls.delete(url);
      }
    });

  inFlightControllers.set(url, controller);
  inFlightUrls.set(url, promise);
  return promise;
}

/**
 * Prefetch preview image URLs in batches. Priority URLs (e.g. the current
 * frame when a layer is added) are fetched to completion before the rest
 * start, then remaining URLs proceed in batches of PREFETCH_BATCH_SIZE.
 * Each request has a timeout so one hung URL cannot stall the queue.
 */
export async function prefetchFramePreviewUrls(
  urls: (string | null | undefined)[],
  options?: { priorityUrls?: (string | null | undefined)[] },
): Promise<void> {
  const priority = uniqueUrls(options?.priorityUrls ?? []);
  const prioritySet = new Set(priority);
  const rest = uniqueUrls(urls).filter((url) => !prioritySet.has(url));

  for (const url of priority) {
    await prefetchOne(url);
  }

  for (let i = 0; i < rest.length; i += PREFETCH_BATCH_SIZE) {
    const batch = rest.slice(i, i + PREFETCH_BATCH_SIZE);
    await Promise.all(batch.map((url) => prefetchOne(url)));
  }
}

export async function getCachedPreviewObjectUrl(
  url: string,
): Promise<string | undefined> {
  return url;
}

export function clearFramePreviewCache() {
  cacheEpoch += 1;
  prefetchedUrls.clear();
  for (const controller of inFlightControllers.values()) {
    controller.abort();
  }
  inFlightControllers.clear();
  inFlightUrls.clear();
}

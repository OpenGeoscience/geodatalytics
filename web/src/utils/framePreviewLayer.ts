import type {
  FramePreview,
  FramePreviewBounds,
  FramePreviewCorner,
  RasterMetadata,
} from "@/types";
import type { Map, MapSourceDataEvent } from "maplibre-gl";
import proj4 from "proj4";
import { getCachedPreviewObjectUrl } from "./framePreviewCache";

export const PREVIEW_FADE_DURATION_MS = 400;

const CORNER_KEYS = ["ul", "ur", "lr", "ll"] as const;
type CornerKey = (typeof CORNER_KEYS)[number];

function clampRasterOpacity(value: number): number {
  return Math.min(1, Math.max(0, value));
}

export function previewSourceId(layerKey: string, frameIndex: number) {
  return `${layerKey}.preview.${frameIndex}`;
}

export function previewLayerId(layerKey: string, frameIndex: number) {
  return `${previewSourceId(layerKey, frameIndex)}.raster`;
}

export function isPreviewMapLayerId(mapLayerId: string) {
  return mapLayerId.includes(".preview.");
}

function toLngLat(srs: string, x: number, y: number): [number, number] {
  if (srs && srs !== "EPSG:4326") {
    return proj4(srs, "EPSG:4326", [x, y]) as [number, number];
  }
  return [x, y];
}

function hasCornerBounds(
  bounds: FramePreviewBounds,
): bounds is FramePreviewBounds & Record<CornerKey, FramePreviewCorner> {
  return CORNER_KEYS.every((corner) => bounds[corner] !== undefined);
}

function cornersFromRasterMetadata(
  rasterBounds: RasterMetadata["bounds"],
): FramePreviewBounds | undefined {
  if (!CORNER_KEYS.every((corner) => rasterBounds[corner])) {
    return undefined;
  }

  const corners = Object.fromEntries(
    CORNER_KEYS.map((corner) => {
      const point = rasterBounds[corner]!;
      const [x, y] = toLngLat(rasterBounds.srs, point.x, point.y);
      return [corner, { x, y }];
    }),
  ) as Record<CornerKey, FramePreviewCorner>;

  const lngs = CORNER_KEYS.map((corner) => corners[corner].x);
  const lats = CORNER_KEYS.map((corner) => corners[corner].y);

  return {
    srs: "EPSG:4326",
    xmin: Math.min(...lngs),
    xmax: Math.max(...lngs),
    ymin: Math.min(...lats),
    ymax: Math.max(...lats),
    ...corners,
  };
}

export function resolvePreviewBounds(
  preview: FramePreview,
  raster?: RasterMetadata,
): FramePreviewBounds {
  if (hasCornerBounds(preview.bounds)) {
    return preview.bounds;
  }

  if (raster?.bounds) {
    const rasterCorners = cornersFromRasterMetadata(raster.bounds);
    if (rasterCorners) {
      return rasterCorners;
    }
  }

  return preview.bounds;
}

function boundsToCoordinates(
  bounds: FramePreviewBounds,
): [[number, number], [number, number], [number, number], [number, number]] {
  if (hasCornerBounds(bounds)) {
    return [
      toLngLat(bounds.srs, bounds.ul.x, bounds.ul.y),
      toLngLat(bounds.srs, bounds.ur.x, bounds.ur.y),
      toLngLat(bounds.srs, bounds.lr.x, bounds.lr.y),
      toLngLat(bounds.srs, bounds.ll.x, bounds.ll.y),
    ];
  }

  const { xmin, xmax, ymin, ymax, srs } = bounds;
  return [
    toLngLat(srs, xmin, ymax),
    toLngLat(srs, xmax, ymax),
    toLngLat(srs, xmax, ymin),
    toLngLat(srs, xmin, ymin),
  ];
}

export async function upsertPreviewLayer(
  map: Map,
  layerKey: string,
  frameIndex: number,
  preview: FramePreview,
  raster?: RasterMetadata,
  opacity = 1,
  visible = true,
) {
  const sourceId = previewSourceId(layerKey, frameIndex);
  const mapLayerId = previewLayerId(layerKey, frameIndex);
  const objectUrl = await getCachedPreviewObjectUrl(preview.url);
  if (!objectUrl) {
    return undefined;
  }

  const coordinates = boundsToCoordinates(
    resolvePreviewBounds(preview, raster),
  );
  const existingSource = map.getSource(sourceId);
  if (existingSource) {
    if (map.getLayer(mapLayerId)) {
      map.removeLayer(mapLayerId);
    }
    map.removeSource(sourceId);
  }
  map.addSource(sourceId, {
    type: "image",
    url: objectUrl,
    coordinates,
  });

  const previewOpacity = clampRasterOpacity(opacity);
  const visibility = visible ? "visible" : "none";

  if (!map.getLayer(mapLayerId)) {
    map.addLayer({
      id: mapLayerId,
      type: "raster",
      source: sourceId,
      layout: {
        visibility,
      },
      paint: {
        "raster-opacity": previewOpacity,
        "raster-fade-duration": 0,
      },
    });
  } else {
    map.setPaintProperty(mapLayerId, "raster-opacity", previewOpacity);
    map.setLayoutProperty(mapLayerId, "visibility", visibility);
  }

  return mapLayerId;
}

export function hidePreviewLayer(
  map: Map,
  layerKey: string,
  frameIndex: number,
) {
  const mapLayerId = previewLayerId(layerKey, frameIndex);
  if (map.getLayer(mapLayerId)) {
    map.setLayoutProperty(mapLayerId, "visibility", "none");
  }
}

export function removePreviewLayer(
  map: Map,
  layerKey: string,
  frameIndex: number,
) {
  const sourceId = previewSourceId(layerKey, frameIndex);
  const mapLayerId = previewLayerId(layerKey, frameIndex);
  if (map.getLayer(mapLayerId)) {
    map.removeLayer(mapLayerId);
  }
  if (map.getSource(sourceId)) {
    map.removeSource(sourceId);
  }
}

function previewFrameIndexFromLayerId(
  layerKey: string,
  mapLayerId: string,
): number | undefined {
  const prefix = `${layerKey}.preview.`;
  if (!mapLayerId.startsWith(prefix)) {
    return undefined;
  }
  const rest = mapLayerId.slice(prefix.length);
  const frameIndex = Number.parseInt(rest.split(".")[0], 10);
  return Number.isNaN(frameIndex) ? undefined : frameIndex;
}

export function removePreviewLayersExcept(
  map: Map,
  layerKey: string,
  keepFrameIndices: number[],
) {
  const keep = new Set(keepFrameIndices);
  const frameIndicesToRemove = new Set<number>();

  map.getStyle().layers?.forEach((layer) => {
    const frameIndex = previewFrameIndexFromLayerId(layerKey, layer.id);
    if (frameIndex !== undefined && !keep.has(frameIndex)) {
      frameIndicesToRemove.add(frameIndex);
    }
  });

  frameIndicesToRemove.forEach((frameIndex) => {
    removePreviewLayer(map, layerKey, frameIndex);
  });
}

export function removeAllPreviewLayersForLayerKey(map: Map, layerKey: string) {
  map.getStyle().layers?.forEach((layer) => {
    if (layer.id.startsWith(`${layerKey}.preview.`)) {
      map.removeLayer(layer.id);
    }
  });
  Object.keys(map.getStyle().sources ?? {}).forEach((sourceId) => {
    if (sourceId.startsWith(`${layerKey}.preview.`)) {
      map.removeSource(sourceId);
    }
  });
}

export function waitForRasterSourceLoaded(
  map: Map,
  sourceId: string,
  timeoutMs = 10000,
): Promise<void> {
  return new Promise((resolve) => {
    if (!map.getSource(sourceId)) {
      resolve();
      return;
    }
    if (map.isSourceLoaded(sourceId)) {
      resolve();
      return;
    }

    const timeout = window.setTimeout(() => {
      map.off("sourcedata", onSourceData);
      resolve();
    }, timeoutMs);

    function onSourceData(event: MapSourceDataEvent) {
      if (event.sourceId === sourceId && event.isSourceLoaded) {
        window.clearTimeout(timeout);
        map.off("sourcedata", onSourceData);
        resolve();
      }
    }

    map.on("sourcedata", onSourceData);
  });
}

export async function fadeRasterOpacities(
  map: Map,
  layers: { id: string; from: number; to: number }[],
  durationMs: number,
) {
  const start = performance.now();
  await new Promise<void>((resolve) => {
    function step(now: number) {
      const progress = Math.min(1, (now - start) / durationMs);
      layers.forEach(({ id, from, to }) => {
        if (map.getLayer(id)) {
          const opacity = progress >= 1 ? to : from + (to - from) * progress;
          map.setPaintProperty(
            id,
            "raster-opacity",
            clampRasterOpacity(opacity),
          );
        }
      });
      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        resolve();
      }
    }
    requestAnimationFrame(step);
  });
}

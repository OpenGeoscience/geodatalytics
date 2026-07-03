import { defineStore } from "pinia";
import { ref } from "vue";
import type { FramePreview, Layer, LayerFrame, LayerStyle } from "@/types";
import type { Map as MaplibreMap } from "maplibre-gl";
import {
  fadeRasterOpacities,
  hidePreviewLayer,
  PREVIEW_FADE_DURATION_MS,
  previewLayerId,
  removeAllPreviewLayersForLayerKey,
  removePreviewLayer,
  removePreviewLayersExcept,
  upsertPreviewLayer,
  waitForRasterSourceLoaded,
} from "@/utils/framePreviewLayer";
import { prefetchFramePreviewUrls } from "@/utils/framePreviewCache";
import { useLayerStore, useMapStore, useStyleStore } from ".";

function layerKey(layer: Layer) {
  return `${layer.id}.${layer.copy_id}`;
}

function orderedRasterFrames(frames: LayerFrame[]) {
  return frames
    .filter((frame) => frame.raster)
    .toSorted((a, b) => a.index - b.index);
}

function previewsForLayer(layer: Layer, style: LayerStyle | undefined) {
  return style?.multiframe_previews ?? layer.multiframe_previews;
}

function previewAtFrameIndex(
  previews: (FramePreview | null)[] | undefined,
  rasterFrames: LayerFrame[],
  frameIndex: number,
): FramePreview | undefined {
  const position = rasterFrames.findIndex(
    (frame) => frame.index === frameIndex,
  );
  if (position < 0) {
    return undefined;
  }
  return previews?.[position] ?? undefined;
}

function adjacentRasterFrames(
  rasterFrames: LayerFrame[],
  currentFrameIndex: number,
) {
  const position = rasterFrames.findIndex(
    (frame) => frame.index === currentFrameIndex,
  );
  if (position < 0) {
    return [];
  }
  return [rasterFrames[position - 1], rasterFrames[position + 1]].filter(
    (frame): frame is LayerFrame => frame !== undefined,
  );
}

export const useFramePreviewStore = defineStore("framePreview", () => {
  const activePreviewByLayerKey = new Map<string, number>();
  const transitionGenerationByLayerKey = new Map<string, number>();

  // Reactive set of layer keys whose preview overlay is currently visible on
  // the map (i.e. the user is looking at a preview image, not the real tiles).
  // Used to drive UI indicators in the layers and legend panels.
  const displayingPreviewLayerKeys = ref<Set<string>>(new Set());

  function markPreviewDisplayed(layerKeyValue: string) {
    if (!displayingPreviewLayerKeys.value.has(layerKeyValue)) {
      const next = new Set(displayingPreviewLayerKeys.value);
      next.add(layerKeyValue);
      displayingPreviewLayerKeys.value = next;
    }
  }

  function clearPreviewDisplayed(layerKeyValue: string) {
    if (displayingPreviewLayerKeys.value.has(layerKeyValue)) {
      const next = new Set(displayingPreviewLayerKeys.value);
      next.delete(layerKeyValue);
      displayingPreviewLayerKeys.value = next;
    }
  }

  function isDisplayingPreview(layer: Layer) {
    return displayingPreviewLayerKeys.value.has(layerKey(layer));
  }

  function bumpGeneration(layerKeyValue: string) {
    const next = (transitionGenerationByLayerKey.get(layerKeyValue) ?? 0) + 1;
    transitionGenerationByLayerKey.set(layerKeyValue, next);
    return next;
  }

  function prefetchLayerPreviews(layer: Layer, style?: LayerStyle) {
    const previews = previewsForLayer(layer, style);
    if (!previews?.length) {
      return;
    }
    prefetchFramePreviewUrls(previews.map((preview) => preview?.url));
  }

  async function preloadAdjacentPreviewLayers(
    map: MaplibreMap,
    layerKeyValue: string,
    previews: (FramePreview | null)[] | undefined,
    rasterFrames: LayerFrame[],
    currentFrameIndex: number,
    targetOpacity: number,
  ) {
    const adjacentFrames = adjacentRasterFrames(
      rasterFrames,
      currentFrameIndex,
    );
    const keepFrameIndices = [
      currentFrameIndex,
      ...adjacentFrames.map((frame) => frame.index),
    ];

    removePreviewLayersExcept(map, layerKeyValue, keepFrameIndices);

    const urlsToPrefetch: (string | null | undefined)[] = [];
    await Promise.all(
      adjacentFrames.map(async (frame) => {
        const preview = previewAtFrameIndex(
          previews,
          rasterFrames,
          frame.index,
        );
        if (!preview || !frame.raster) {
          return;
        }
        urlsToPrefetch.push(preview.url);
        await upsertPreviewLayer(
          map,
          layerKeyValue,
          frame.index,
          preview,
          frame.raster.metadata,
          targetOpacity,
          false,
        );
      }),
    );

    const currentPreview = previewAtFrameIndex(
      previews,
      rasterFrames,
      currentFrameIndex,
    );
    urlsToPrefetch.push(currentPreview?.url);
    prefetchFramePreviewUrls(urlsToPrefetch);
  }

  function hidePreviousPreview(map: MaplibreMap, layerKeyValue: string) {
    const previousFrameIndex = activePreviewByLayerKey.get(layerKeyValue);
    if (previousFrameIndex !== undefined) {
      hidePreviewLayer(map, layerKeyValue, previousFrameIndex);
    }
  }

  async function transitionToTiles(
    layer: Layer,
    frameIndex: number,
    layerKeyValue: string,
    generation: number,
    targetOpacity: number,
    tileLayerId: string,
    tileSourceId: string,
  ) {
    const mapStore = useMapStore();
    const map = mapStore.getMap();
    const previewMapLayerId = previewLayerId(layerKeyValue, frameIndex);

    if (transitionGenerationByLayerKey.get(layerKeyValue) !== generation) {
      return;
    }

    await waitForRasterSourceLoaded(map, tileSourceId);

    if (transitionGenerationByLayerKey.get(layerKeyValue) !== generation) {
      return;
    }

    if (!map.getLayer(tileLayerId) || !map.getLayer(previewMapLayerId)) {
      if (map.getLayer(tileLayerId)) {
        map.setPaintProperty(tileLayerId, "raster-opacity", targetOpacity);
      }
      removePreviewLayer(map, layerKeyValue, frameIndex);
      activePreviewByLayerKey.delete(layerKeyValue);
      clearPreviewDisplayed(layerKeyValue);
      return;
    }

    const tileOpacity =
      (map.getPaintProperty(tileLayerId, "raster-opacity") as number) ?? 0;
    const previewOpacity =
      (map.getPaintProperty(previewMapLayerId, "raster-opacity") as number) ??
      targetOpacity;
    await fadeRasterOpacities(
      map,
      [
        { id: previewMapLayerId, from: previewOpacity, to: 0 },
        { id: tileLayerId, from: tileOpacity, to: targetOpacity },
      ],
      PREVIEW_FADE_DURATION_MS,
    );

    if (transitionGenerationByLayerKey.get(layerKeyValue) !== generation) {
      return;
    }

    removePreviewLayer(map, layerKeyValue, frameIndex);
    activePreviewByLayerKey.delete(layerKeyValue);
    clearPreviewDisplayed(layerKeyValue);
  }

  async function showPreviewThenTiles(layer: Layer) {
    const layerStore = useLayerStore();
    const mapStore = useMapStore();
    const styleStore = useStyleStore();
    if (styleStore.isLayerStyleEditing(layer)) {
      return;
    }
    const map = mapStore.getMap();
    const layerKeyValue = layerKey(layer);
    const style = styleStore.selectedLayerStyles[layerKeyValue];
    const previews = previewsForLayer(layer, style);

    const frames = layerStore.layerFrames(layer);
    const rasterFrames = orderedRasterFrames(frames);
    if (rasterFrames.length <= 1) {
      return;
    }

    const currentFrame = rasterFrames.find(
      (frame) => frame.index === layer.current_frame_index,
    );
    if (!currentFrame?.raster || !layer.visible) {
      return;
    }

    const preview = previewAtFrameIndex(
      previews,
      rasterFrames,
      layer.current_frame_index,
    );

    const tileSourceId = mapStore.sourceIdFromLayerFrame(layer, currentFrame);
    const tileLayerId = `${tileSourceId}.raster`;
    const targetOpacity = style?.style_spec?.opacity ?? 1;

    const generation = bumpGeneration(layerKeyValue);
    hidePreviousPreview(map, layerKeyValue);

    if (!preview) {
      clearPreviewDisplayed(layerKeyValue);
      if (map.getLayer(tileLayerId)) {
        map.setPaintProperty(tileLayerId, "raster-opacity", targetOpacity);
      }
      void preloadAdjacentPreviewLayers(
        map,
        layerKeyValue,
        previews,
        rasterFrames,
        layer.current_frame_index,
        targetOpacity,
      );
      return;
    }

    const previewMapLayerId = await upsertPreviewLayer(
      map,
      layerKeyValue,
      layer.current_frame_index,
      preview,
      currentFrame.raster.metadata,
      targetOpacity,
    );
    if (!previewMapLayerId) {
      clearPreviewDisplayed(layerKeyValue);
      if (map.getLayer(tileLayerId)) {
        map.setPaintProperty(tileLayerId, "raster-opacity", targetOpacity);
      }
      return;
    }

    activePreviewByLayerKey.set(layerKeyValue, layer.current_frame_index);
    markPreviewDisplayed(layerKeyValue);

    if (map.getLayer(tileLayerId)) {
      map.setPaintProperty(tileLayerId, "raster-opacity", 0);
    }

    void preloadAdjacentPreviewLayers(
      map,
      layerKeyValue,
      previews,
      rasterFrames,
      layer.current_frame_index,
      targetOpacity,
    );

    void transitionToTiles(
      layer,
      layer.current_frame_index,
      layerKeyValue,
      generation,
      targetOpacity,
      tileLayerId,
      tileSourceId,
    );
  }

  function dismissPreviewForLayer(layer: Layer) {
    const mapStore = useMapStore();
    const layerStore = useLayerStore();
    const styleStore = useStyleStore();
    const map = mapStore.getMap();
    const layerKeyValue = layerKey(layer);

    bumpGeneration(layerKeyValue);
    removeAllPreviewLayersForLayerKey(map, layerKeyValue);
    activePreviewByLayerKey.delete(layerKeyValue);
    clearPreviewDisplayed(layerKeyValue);

    const frames = layerStore.layerFrames(layer);
    const currentFrame = frames.find(
      (frame) => frame.index === layer.current_frame_index,
    );
    if (!currentFrame?.raster) {
      return;
    }

    const tileLayerId = `${mapStore.sourceIdFromLayerFrame(layer, currentFrame)}.raster`;
    const style = styleStore.selectedLayerStyles[layerKeyValue];
    const targetOpacity = style?.style_spec?.opacity ?? 1;
    if (map.getLayer(tileLayerId)) {
      map.setPaintProperty(tileLayerId, "raster-opacity", targetOpacity);
    }
  }

  function cleanupLayer(layer: Layer) {
    const mapStore = useMapStore();
    const layerKeyValue = layerKey(layer);
    transitionGenerationByLayerKey.delete(layerKeyValue);
    activePreviewByLayerKey.delete(layerKeyValue);
    clearPreviewDisplayed(layerKeyValue);
    removeAllPreviewLayersForLayerKey(mapStore.getMap(), layerKeyValue);
  }

  function clearAll() {
    transitionGenerationByLayerKey.clear();
    activePreviewByLayerKey.clear();
    displayingPreviewLayerKeys.value = new Set();
  }

  return {
    displayingPreviewLayerKeys,
    isDisplayingPreview,
    prefetchLayerPreviews,
    showPreviewThenTiles,
    dismissPreviewForLayer,
    cleanupLayer,
    clearAll,
  };
});

import { defineStore } from "pinia";
import { ref } from "vue";
import type {
  FramePreview,
  Layer,
  LayerFrame,
  LayerStyle,
  TaskResult,
} from "@/types";
import type { Map as MaplibreMap } from "maplibre-gl";
import { getLayerStyle } from "@/api/rest";
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

const layerStore = useLayerStore();
const mapStore = useMapStore();
const styleStore = useStyleStore();

function layerKey(layer: Layer) {
  return `${layer.id}.${layer.copy_id}`;
}

function orderedRasterFrames(frames: LayerFrame[]) {
  return frames
    .filter((frame) => frame.raster)
    .toSorted((a, b) => a.index - b.index);
}

// Previews are only safe to display once the backend reports ready (every
// frame has a complete image). After a style save the API returns "notready"
// and omits multiframe_previews until regeneration finishes.
//
// Layer payloads carry the default-fingerprint preview set (empty params from
// conversion, or the layer's default_style params). Style payloads carry
// previews for that style's params. Use layer-level data when the active style
// is the default / unset synthetic style.
function usesLayerDefaultPreviews(
  layer: Layer,
  style: LayerStyle | undefined,
): boolean {
  if (style == null || style.id === undefined) {
    return true;
  }
  if (layer.default_style?.id != null) {
    return style.id === layer.default_style.id;
  }
  // No DB default style: treat is_default / synthetic default as the layer default.
  return style.is_default === true;
}

function previewsAreReady(
  layer: Layer,
  style: LayerStyle | undefined,
): boolean {
  if (style?.preview_status !== undefined) {
    return style.preview_status === "ready";
  }
  if (
    usesLayerDefaultPreviews(layer, style) &&
    layer.preview_status !== undefined
  ) {
    return layer.preview_status === "ready";
  }
  // Backward compatibility for payloads that omit preview_status entirely.
  return true;
}

function previewsForLayer(layer: Layer, style: LayerStyle | undefined) {
  if (!previewsAreReady(layer, style)) {
    return undefined;
  }
  if (style?.multiframe_previews?.length) {
    return style.multiframe_previews;
  }
  if (
    usesLayerDefaultPreviews(layer, style) &&
    layer.multiframe_previews?.length
  ) {
    return layer.multiframe_previews;
  }
  return undefined;
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

  // Called when a "frame_preview" TaskResult completes over the analytics
  // WebSocket. Reloads the freshly generated previews and reattaches them to
  // every selected layer copy that still has the regenerated style applied.
  async function onPreviewTaskComplete(task: TaskResult) {
    const layerStyleId = task.inputs?.layer_style_id as number | undefined;
    const layerId = task.inputs?.layer_id as number | undefined;
    if (layerId === undefined) {
      return;
    }

    const layerStore = useLayerStore();
    const styleStore = useStyleStore();

    // Conversion / dataset-default tasks have no layer_style_id; refresh the
    // layer payload which carries the default-fingerprint preview set.
    if (layerStyleId === undefined) {
      let updatedLayer: Layer;
      try {
        updatedLayer = await layerStore.fetchAvailableLayer(layerId);
      } catch {
        return;
      }

      layerStore.selectedLayers.forEach((layer) => {
        if (layer.id !== layerId) {
          return;
        }
        layer.multiframe_previews = updatedLayer.multiframe_previews;
        layer.preview_status = updatedLayer.preview_status;

        const key = layerKey(layer);
        const selectedStyle = styleStore.selectedLayerStyles[key];
        if (!usesLayerDefaultPreviews(layer, selectedStyle)) {
          return;
        }

        styleStore.selectedLayerStyles[key] = {
          ...(selectedStyle ?? {
            name: "None",
            is_default: true,
          }),
          preview_status: updatedLayer.preview_status,
          multiframe_previews: updatedLayer.multiframe_previews,
        };

        prefetchLayerPreviews(layer, styleStore.selectedLayerStyles[key]);
        if (!styleStore.isLayerStyleEditing(layer)) {
          void showPreviewThenTiles(layer);
        }
      });
      return;
    }

    let updatedStyle: LayerStyle;
    try {
      updatedStyle = await getLayerStyle(layerStyleId);
    } catch {
      // If the style was deleted or the fetch fails, there is nothing to attach.
      return;
    }

    // Keep availableLayers current so re-adding this layer picks up the new
    // default-style previews. Fire-and-forget; selected copies are updated below.
    void layerStore.fetchAvailableLayer(layerId).catch(() => undefined);

    layerStore.selectedLayers.forEach((layer) => {
      if (layer.id !== layerId) {
        return;
      }
      const key = layerKey(layer);
      const selectedStyle = styleStore.selectedLayerStyles[key];
      // Only reattach when this copy still has the regenerated style selected;
      // the user may have swapped to a different style while generation ran.
      if (!selectedStyle || selectedStyle.id !== layerStyleId) {
        return;
      }

      styleStore.selectedLayerStyles[key] = {
        ...selectedStyle,
        preview_status: updatedStyle.preview_status,
        multiframe_previews: updatedStyle.multiframe_previews,
      };

      // Mirror onto the layer object so the default-style fallback stays valid.
      if (updatedStyle.is_default) {
        layer.multiframe_previews = updatedStyle.multiframe_previews;
        layer.preview_status = updatedStyle.preview_status;
      }

      prefetchLayerPreviews(layer, styleStore.selectedLayerStyles[key]);
      if (!styleStore.isLayerStyleEditing(layer)) {
        void showPreviewThenTiles(layer);
      }
    });
  }

  return {
    displayingPreviewLayerKeys,
    isDisplayingPreview,
    prefetchLayerPreviews,
    showPreviewThenTiles,
    dismissPreviewForLayer,
    onPreviewTaskComplete,
    cleanupLayer,
    clearAll,
  };
});

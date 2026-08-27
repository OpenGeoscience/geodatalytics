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
  isPreviewMapLayerId,
  PREVIEW_FADE_DURATION_MS,
  previewLayerId,
  removeAllPreviewLayersForLayerKey,
  removePreviewLayer,
  removePreviewLayersExcept,
  upsertPreviewLayer,
  waitForRasterSourceLoaded,
} from "@/utils/framePreviewLayer";
import { prefetchFramePreviewUrls } from "@/utils/framePreviewCache";
import { useLayerStore } from "./layer";
import { useMapStore } from "./map";
import { useStyleStore } from "./style";

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

// Wait for scrubbing to pause before attaching/fetching raster tiles. Previews
// stay immediate so the slider feels responsive on large multiframe rasters.
const TILE_LOAD_SETTLE_MS = 1000;

export const useFramePreviewStore = defineStore("framePreview", () => {
  const layerStore = useLayerStore();
  const mapStore = useMapStore();
  const styleStore = useStyleStore();

  const activePreviewByLayerKey = new Map<string, number>();
  const transitionGenerationByLayerKey = new Map<string, number>();
  const tileLoadTimerByLayerKey = new Map<
    string,
    ReturnType<typeof setTimeout>
  >();

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
    return displayingPreviewLayerKeys.value.has(
      styleStore.layerStyleKey(layer),
    );
  }

  // True when this multiframe layer's previews are explicitly not ready
  // (missing / generating / regenerating). Omitted preview_status is treated
  // as ready for backward compatibility, matching previewsAreReady().
  function isGeneratingPreviews(layer: Layer) {
    const rasterFrames = orderedRasterFrames(layerStore.layerFrames(layer));
    if (rasterFrames.length <= 1) {
      return false;
    }
    const style =
      styleStore.selectedLayerStyles[styleStore.layerStyleKey(layer)];
    if (style?.preview_status !== undefined) {
      return style.preview_status === "notready";
    }
    if (
      usesLayerDefaultPreviews(layer, style) &&
      layer.preview_status !== undefined
    ) {
      return layer.preview_status === "notready";
    }
    return false;
  }

  function iconState(layer: Layer) {
    if (isDisplayingPreview(layer)) {
      return {
        visible: true,
        tooltip:
          "Showing a low-resolution preview while default resolution tiles load.",
        color: "primary" as const,
        class: {
          "preview-indicator--generating": false,
          "preview-indicator--hidden": false,
        },
      };
    }
    if (isGeneratingPreviews(layer)) {
      return {
        visible: true,
        tooltip: "Frame previews are being created.",
        color: undefined,
        class: {
          "preview-indicator--generating": true,
          "preview-indicator--hidden": false,
        },
      };
    }
    return {
      visible: false,
      tooltip: undefined,
      color: undefined,
      class: {
        "preview-indicator--generating": false,
        "preview-indicator--hidden": true,
      },
    };
  }

  function clearTileLoadTimer(layerKeyValue: string) {
    const timer = tileLoadTimerByLayerKey.get(layerKeyValue);
    if (timer !== undefined) {
      clearTimeout(timer);
      tileLoadTimerByLayerKey.delete(layerKeyValue);
    }
  }

  function bumpGeneration(layerKeyValue: string) {
    clearTileLoadTimer(layerKeyValue);
    const next = (transitionGenerationByLayerKey.get(layerKeyValue) ?? 0) + 1;
    transitionGenerationByLayerKey.set(layerKeyValue, next);
    return next;
  }

  function scheduleTileLoadAfterSettle(
    layerKeyValue: string,
    generation: number,
    loadTiles: () => void,
  ) {
    clearTileLoadTimer(layerKeyValue);
    const timer = setTimeout(() => {
      tileLoadTimerByLayerKey.delete(layerKeyValue);
      if (transitionGenerationByLayerKey.get(layerKeyValue) !== generation) {
        return;
      }
      loadTiles();
    }, TILE_LOAD_SETTLE_MS);
    tileLoadTimerByLayerKey.set(layerKeyValue, timer);
  }

  /**
   * Restore map layer z-order to match the layers panel.
   *
   * Walk selectedLayers bottom-to-top. For each layer, move its tile layers
   * up, then its preview overlays above those tiles. Lower panel rows are
   * processed first so higher rows end up on top.
   */
  function reorderPreviewLayers() {
    if (!mapStore.map) {
      return;
    }
    const map = mapStore.getMap();
    const userMapLayers = mapStore.getUserMapLayers();

    layerStore.selectedLayers.toReversed().forEach((layer) => {
      const layerKeyValue = styleStore.layerStyleKey(layer);

      layerStore.layerFrames(layer).forEach((frame) => {
        const sourceId = mapStore.sourceIdFromLayerFrame(layer, frame);
        userMapLayers.forEach((mapLayerId) => {
          if (isPreviewMapLayerId(mapLayerId)) {
            return;
          }
          if (mapLayerId.includes(sourceId) && map.getLayer(mapLayerId)) {
            map.moveLayer(mapLayerId);
          }
        });
      });

      const previewPrefix = `${layerKeyValue}.preview.`;
      const activeFrameIndex = activePreviewByLayerKey.get(layerKeyValue);
      userMapLayers.forEach((mapLayerId) => {
        if (!mapLayerId.startsWith(previewPrefix)) {
          return;
        }
        if (
          activeFrameIndex !== undefined &&
          mapLayerId === previewLayerId(layerKeyValue, activeFrameIndex)
        ) {
          return;
        }
        if (map.getLayer(mapLayerId)) {
          map.moveLayer(mapLayerId);
        }
      });
      if (activeFrameIndex !== undefined) {
        const activePreviewMapLayerId = previewLayerId(
          layerKeyValue,
          activeFrameIndex,
        );
        if (map.getLayer(activePreviewMapLayerId)) {
          map.moveLayer(activePreviewMapLayerId);
        }
      }
    });
  }

  function prefetchLayerPreviews(layer: Layer, style?: LayerStyle) {
    const previews = previewsForLayer(layer, style);
    if (!previews?.length) {
      return;
    }
    prefetchFramePreviewUrls(previews.map((preview) => preview?.url));
  }

  function hasReadyPreviewForCurrentFrame(layer: Layer) {
    if (styleStore.isLayerStyleEditing(layer)) {
      return false;
    }
    const rasterFrames = orderedRasterFrames(layerStore.layerFrames(layer));
    if (rasterFrames.length <= 1) {
      return false;
    }
    const style =
      styleStore.selectedLayerStyles[styleStore.layerStyleKey(layer)];
    return !!previewAtFrameIndex(
      previewsForLayer(layer, style),
      rasterFrames,
      layer.current_frame_index,
    );
  }

  function ensureRasterTilesOnMap(
    frame: LayerFrame,
    tileSourceId: string,
    tileLayerId: string,
    opacity: number,
  ) {
    const map = mapStore.getMap();
    if (!map.getLayer(tileLayerId)) {
      mapStore.addLayerFrameToMap(frame, tileSourceId, true, {
        rasterOpacity: opacity,
      });
      return;
    }
    map.setPaintProperty(tileLayerId, "raster-opacity", opacity);
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

  function hidePreviousPreview(
    map: MaplibreMap,
    layerKeyValue: string,
    nextFrameIndex: number,
  ) {
    const previousFrameIndex = activePreviewByLayerKey.get(layerKeyValue);
    if (
      previousFrameIndex !== undefined &&
      previousFrameIndex !== nextFrameIndex
    ) {
      hidePreviewLayer(map, layerKeyValue, previousFrameIndex);
    }
  }

  function isPreviewLayerVisible(
    map: MaplibreMap,
    mapLayerId: string,
  ): boolean {
    if (!map.getLayer(mapLayerId)) {
      return false;
    }
    return map.getLayoutProperty(mapLayerId, "visibility") === "visible";
  }

  /** Skip preview work when this layer is already settled for the current frame. */
  function previewAlreadySettled(
    map: MaplibreMap,
    layerKeyValue: string,
    settledFrameIndex: number,
    tileLayerId: string,
    previewMapLayerId: string,
    targetOpacity: number,
  ): boolean {
    const activeFrameIndex = activePreviewByLayerKey.get(layerKeyValue);
    if (activeFrameIndex === settledFrameIndex) {
      return isPreviewLayerVisible(map, previewMapLayerId);
    }

    if (activeFrameIndex !== undefined) {
      return false;
    }

    // Preview transition finished; tiles are showing at target opacity.
    if (map.getLayer(previewMapLayerId)) {
      return false;
    }
    if (!map.getLayer(tileLayerId)) {
      return false;
    }
    const tileOpacity =
      (map.getPaintProperty(tileLayerId, "raster-opacity") as number) ?? 0;
    return tileOpacity >= targetOpacity - 0.01;
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
      reorderPreviewLayers();
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
    reorderPreviewLayers();
  }

  async function showPreviewThenTiles(layer: Layer) {
    if (styleStore.isLayerStyleEditing(layer)) {
      return;
    }
    const map = mapStore.getMap();
    const layerKeyValue = styleStore.layerStyleKey(layer);
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
    const settledFrameIndex = layer.current_frame_index;
    const previewMapLayerId = previewLayerId(layerKeyValue, settledFrameIndex);

    if (
      previewAlreadySettled(
        map,
        layerKeyValue,
        settledFrameIndex,
        tileLayerId,
        previewMapLayerId,
        targetOpacity,
      )
    ) {
      reorderPreviewLayers();
      return;
    }

    const generation = bumpGeneration(layerKeyValue);

    if (!preview) {
      // Drop any leftover overlay (including adjacent preloads) so a stale
      // image cannot flash while tiles catch up after a style change.
      removeAllPreviewLayersForLayerKey(map, layerKeyValue);
      activePreviewByLayerKey.delete(layerKeyValue);
      clearPreviewDisplayed(layerKeyValue);
      ensureRasterTilesOnMap(
        currentFrame,
        tileSourceId,
        tileLayerId,
        targetOpacity,
      );
      return;
    }

    const upsertedPreviewLayerId = await upsertPreviewLayer(
      map,
      layerKeyValue,
      settledFrameIndex,
      preview,
      currentFrame.raster.metadata,
      targetOpacity,
    );
    if (transitionGenerationByLayerKey.get(layerKeyValue) !== generation) {
      // A newer scrub already took over; don't steal its settle timer or cover
      // its preview with this stale overlay.
      if (
        upsertedPreviewLayerId &&
        layer.current_frame_index !== settledFrameIndex
      ) {
        hidePreviewLayer(map, layerKeyValue, settledFrameIndex);
      }
      return;
    }
    if (!upsertedPreviewLayerId) {
      clearPreviewDisplayed(layerKeyValue);
      ensureRasterTilesOnMap(
        currentFrame,
        tileSourceId,
        tileLayerId,
        targetOpacity,
      );
      return;
    }

    activePreviewByLayerKey.set(layerKeyValue, settledFrameIndex);
    markPreviewDisplayed(layerKeyValue);
    reorderPreviewLayers();
    hidePreviousPreview(map, layerKeyValue, settledFrameIndex);

    // Keep any already-attached tiles invisible while scrubbing; do not start
    // fetching a new frame's tiles until the settle debounce fires.
    if (map.getLayer(tileLayerId)) {
      map.setPaintProperty(tileLayerId, "raster-opacity", 0);
    }

    preloadAdjacentPreviewLayers(
      map,
      layerKeyValue,
      previews,
      rasterFrames,
      settledFrameIndex,
      targetOpacity,
    ).then(() => reorderPreviewLayers());

    scheduleTileLoadAfterSettle(layerKeyValue, generation, () => {
      if (layer.current_frame_index !== settledFrameIndex) {
        return;
      }
      ensureRasterTilesOnMap(currentFrame, tileSourceId, tileLayerId, 0);
      reorderPreviewLayers();
      transitionToTiles(
        layer,
        settledFrameIndex,
        layerKeyValue,
        generation,
        targetOpacity,
        tileLayerId,
        tileSourceId,
      );
    });
  }

  /**
   * Drop stale preview overlays and hide current-frame tiles so the next
   * showPreviewThenTiles call re-attaches previews for the active style.
   */
  function prepareForStylePreviewReset(layer: Layer) {
    const map = mapStore.getMap();
    const layerKeyValue = styleStore.layerStyleKey(layer);

    bumpGeneration(layerKeyValue);
    removeAllPreviewLayersForLayerKey(map, layerKeyValue);
    activePreviewByLayerKey.delete(layerKeyValue);
    clearPreviewDisplayed(layerKeyValue);

    const frames = layerStore.layerFrames(layer);
    const currentFrame = frames.find(
      (frame) => frame.index === layer.current_frame_index,
    );
    if (currentFrame?.raster && layer.visible) {
      const tileLayerId = `${mapStore.sourceIdFromLayerFrame(layer, currentFrame)}.raster`;
      if (map.getLayer(tileLayerId)) {
        map.setPaintProperty(tileLayerId, "raster-opacity", 0);
      }
    }
    reorderPreviewLayers();
  }

  function dismissPreviewForLayer(layer: Layer) {
    const map = mapStore.getMap();
    const layerKeyValue = styleStore.layerStyleKey(layer);

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
    reorderPreviewLayers();
  }

  /** Clear stale preview payloads + map overlays after a style change. */
  function clearPreviewsForStyleChange(layer: Layer, styleId?: number) {
    layerStore.selectedLayers.forEach((candidate) => {
      if (candidate.id !== layer.id) return;

      const key = styleStore.layerStyleKey(candidate);
      const selectedStyle = styleStore.selectedLayerStyles[key];
      if (!selectedStyle) return;

      const matches =
        styleId !== undefined
          ? selectedStyle.id === styleId
          : candidate.copy_id === layer.copy_id;
      if (!matches) return;

      styleStore.selectedLayerStyles[key] = {
        ...selectedStyle,
        preview_status: "notready",
        multiframe_previews: undefined,
      };
      if (
        selectedStyle.is_default ||
        usesLayerDefaultPreviews(candidate, selectedStyle)
      ) {
        candidate.preview_status = "notready";
        candidate.multiframe_previews = undefined;
      }
      dismissPreviewForLayer(candidate);
    });
  }

  function cleanupLayer(layer: Layer) {
    const layerKeyValue = styleStore.layerStyleKey(layer);
    clearTileLoadTimer(layerKeyValue);
    transitionGenerationByLayerKey.delete(layerKeyValue);
    activePreviewByLayerKey.delete(layerKeyValue);
    clearPreviewDisplayed(layerKeyValue);
    removeAllPreviewLayersForLayerKey(mapStore.getMap(), layerKeyValue);
  }

  function clearAll() {
    tileLoadTimerByLayerKey.forEach((timer) => clearTimeout(timer));
    tileLoadTimerByLayerKey.clear();
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

        const key = styleStore.layerStyleKey(layer);
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
          showPreviewThenTiles(layer);
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
    layerStore.fetchAvailableLayer(layerId).catch(() => undefined);

    layerStore.selectedLayers.forEach((layer) => {
      if (layer.id !== layerId) {
        return;
      }
      const key = styleStore.layerStyleKey(layer);
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
        showPreviewThenTiles(layer);
      }
    });
  }

  return {
    displayingPreviewLayerKeys,
    isDisplayingPreview,
    isGeneratingPreviews,
    iconState,
    prefetchLayerPreviews,
    hasReadyPreviewForCurrentFrame,
    reorderPreviewLayers,
    showPreviewThenTiles,
    dismissPreviewForLayer,
    prepareForStylePreviewReset,
    clearPreviewsForStyleChange,
    onPreviewTaskComplete,
    cleanupLayer,
    clearAll,
  };
});

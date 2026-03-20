<script setup lang="ts">
import { ref, computed } from "vue";
import type { Layer } from "@/types";
import ColormapPreview from './ColormapPreview.vue';

import { useLayerStore, useStyleStore } from "@/store";
import { colormapMarkersSubsample } from "@/store/style";
const layerStore = useLayerStore();
const styleStore = useStyleStore();

const searchText = ref<string | undefined>();
const filteredLegend = computed(() => {
    return layerStore.selectedLayers?.filter((layer) => {
        return (
            (!searchText.value || layer.name.toLowerCase().includes(searchText.value.toLowerCase()))
        )
    })
})

function getColormapPreviews(layer: Layer) {
    const styleKey = `${layer.id}.${layer.copy_id}`;
    const currentStyleSpec = styleStore.selectedLayerStyles[styleKey].style_spec;
    if (!currentStyleSpec) return [];
    const currentFrame = layerStore.layerFrames(layer).find(
        (f) => f.index === layer.current_frame_index
    )
    const vector = currentFrame?.vector
    return currentStyleSpec.colors.map((colorConfig) => {
        const name = colorConfig.name
        let discrete = false;
        let nColors = 1;
        let colorBy = undefined;
        let range: [number | undefined, number | undefined] = [undefined, undefined];
        const useFeatureProps = vector && colorConfig.use_feature_props;
        let valueColors = undefined
        let colormap = styleStore.colormaps.find((cmap) => cmap.id === colorConfig.colormap?.id)
        if (colormap) {
            discrete = colorConfig.colormap?.discrete || discrete;
            nColors = colorConfig.colormap?.n_colors || nColors;
            colorBy = colorConfig.colormap?.color_by;
            range = colorConfig.colormap?.range || range;
        } else if (colorConfig.single_color) {
            colormap = {
                markers: [
                    { color: colorConfig.single_color, value: 0 },
                ]
            }
        }
        const propsSpec = vector?.summary?.properties;
        if (propsSpec && colorBy) {
            const colorByProp = propsSpec[colorBy]
            if (discrete && colormap && colorConfig.colormap) {
                const valueSet = Array.from(new Set(colorByProp.value_set.filter((v) => v)))
                const sortedValues = valueSet.sort((a: any, b: any) => a - b)
                const markers = colormapMarkersSubsample(colormap, colorConfig.colormap, nColors)
                valueColors = sortedValues.map((v, i) => {
                    if (markers) {
                        return {
                            value: v,
                            color: markers[Math.ceil((i + 1) / sortedValues.length * markers.length) - 1]?.color
                        }
                    }
                })
            } else if (!discrete && colorByProp.range) {
                range = colorByProp.range
            }
        }
        return {
            name,
            colormap,
            discrete,
            nColors,
            colorBy,
            range,
            useFeatureProps,
            valueColors,
        }
    })
}

function setVisibility(layer: Layer, visible = true) {
    layerStore.selectedLayers = layerStore.selectedLayers.map((l: Layer) => {
        if (l.id == layer.id) l.visible = visible;
        return l
    })
}

function getColorPropsCoverage(layer: Layer) {
  const frame_coverages = layerStore.layerFrames(layer).map(
    (frame) => frame.vector?.summary?.color_props_coverage || "none"
  )
  if (frame_coverages.every((c) => c === 'full')) return 'full'
  if (frame_coverages.every((c) => c === 'none')) return 'none'
  return 'partial'

}
</script>

<template>
    <div class="panel-content-outer with-search">
        <v-text-field v-model="searchText" label="Search Legend" variant="outlined" density="compact" class="mb-2"
            append-inner-icon="mdi-magnify" hide-details />
        <v-card class="panel-content-inner">
            <v-list v-if="filteredLegend?.length" density="compact">
                <v-list-item v-for="layer in filteredLegend" :key="layer.id">
                    <v-icon :icon="layer.visible ? 'mdi-eye-outline' : 'mdi-eye-off-outline'"
                        @click="setVisibility(layer, !layer.visible)" class="" />
                    {{ layer.name }}
                    <div v-for="colormap_preview in getColormapPreviews(layer)" class="ml-6">
                        <div v-if="getColormapPreviews(layer).length > 1">{{ colormap_preview.name }}</div>
                        <span v-if="colormap_preview.useFeatureProps && getColorPropsCoverage(layer) !== 'none'">
                          Use feature color properties
                          <span v-if="getColorPropsCoverage(layer) !== 'full'">; default to </span>
                        </span>
                        <div v-if="getColorPropsCoverage(layer) !== 'full'">
                          <span v-if="colormap_preview.colorBy">color by {{ colormap_preview.colorBy }}</span>
                          <span v-if="!colormap_preview.colormap">Use default style</span>
                          <div v-else>
                              <colormap-preview v-if="!colormap_preview.valueColors" :colormap="colormap_preview.colormap"
                                  :discrete="colormap_preview.discrete" :nColors="colormap_preview.nColors"
                                  :range="colormap_preview.range" />
                              <v-expansion-panels v-else>
                                  <v-expansion-panel static bg-color="transparent">
                                      <v-expansion-panel-title class="pa-0" min-height="0">
                                          <colormap-preview :colormap="colormap_preview.colormap"
                                              :discrete="colormap_preview.discrete" :nColors="colormap_preview.nColors"
                                              :range="colormap_preview.range" />
                                      </v-expansion-panel-title>
                                      <v-expansion-panel-text>
                                          <div v-for="row in colormap_preview.valueColors">
                                              <div v-if="row" class="d-flex" style="align-items: center;">
                                                  <div class="color-square" :style="{ backgroundColor: row.color }"></div>
                                                  {{ row.value }}
                                              </div>
                                          </div>
                                      </v-expansion-panel-text>
                                  </v-expansion-panel>
                              </v-expansion-panels>
                          </div>
                        </div>
                    </div>
                </v-list-item>
            </v-list>
        </v-card>
    </div>
</template>

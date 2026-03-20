<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import type { Ref } from 'vue';
import type { Layer, LayerStyle, StyleSpec } from '@/types';
import { getLayerStyles } from '@/api/rest';
import SliderNumericInput from '../SliderNumericInput.vue';

import { useStyleStore, usePanelStore, useLayerStore, useMapStore } from '@/store';
import { cloneDeep, debounce, map } from 'lodash';
import { useMapCompareStore } from '@/store/compare';
const styleStore = useStyleStore();
const panelStore = usePanelStore();
const mapStore = useMapStore();
const layerStore = useLayerStore();
const compareStore = useMapCompareStore();


const emit = defineEmits(["setLayerActive"]);
const props = defineProps<{
  layer: Layer;
  activeLayer: Layer | undefined;
}>();

const availableStyles = ref<LayerStyle[]>();
const currentStyleSpecs = ref<{A: StyleSpec | undefined, B: StyleSpec | undefined}>({A: undefined, B: undefined});

const styleKey = computed(() => {
    return `${props.layer.id}.${props.layer.copy_id}`;
})


const currentLayerStyles = computed(() => {
    let A = compareStore.compareLayerStyles.A[styleKey.value];
    let B = compareStore.compareLayerStyles.B[styleKey.value];
    if (!A) {
        A = {style: styleStore.selectedLayerStyles[styleKey.value], opacity: styleStore.selectedLayerStyles[styleKey.value]?.style_spec?.opacity || 1};
    }
    if (!B) {
        B = {style: styleStore.selectedLayerStyles[styleKey.value], opacity: styleStore.selectedLayerStyles[styleKey.value]?.style_spec?.opacity || 1};
    }
    return {
        A,
        B,
    }
});

const appliedStyleText = computed(() => {
    const text = {
        A: currentLayerStyles.value.A?.style.name ? `Style: ${currentLayerStyles.value.A.style.name}` : 'Configure styling',
        B: currentLayerStyles.value.B?.style.name ? `Style: ${currentLayerStyles.value.B.style.name}` : 'Configure styling',
    }
    const prependText = {
        A: compareStore.orientation === 'vertical' ? 'Left' : 'Top',
        B: compareStore.orientation === 'vertical' ? 'Right' : 'Bottom',
    }
    return `${prependText.A} - ${text.A} ${prependText.B} - ${text.B}`;
})

const frames = computed(() => {
    return layerStore.layerFrames(props.layer)
})

const currentFrame = computed(() => {
    return frames.value.find(
        (f) => f.index === props.layer.current_frame_index
    )
})

const mapLayerIds: Ref<string[]> = ref([]);

async function init() {
    resetCurrentStyle();
    if (props.activeLayer === props.layer) {
        const foundLayerIds = mapStore.getUserMapLayers().filter((layer) => {
            const { layerId, layerCopyId } = mapStore.parseLayerString(layer);
            if (layerId === props.layer.id && layerCopyId === props.layer.copy_id) {
                return true;
            }
        })
        if (foundLayerIds.length) {
            mapLayerIds.value = foundLayerIds;
        }
        getLayerStyles(props.layer.id).then((styles) => availableStyles.value = styles);

    }
}

function resetCurrentStyleForPanel(panel: 'A' | 'B') {
    const currentStyle = currentLayerStyles.value[panel]?.style;
    if (currentStyle?.id) {
        currentStyleSpecs.value[panel] = cloneDeep(currentStyle.style_spec);
    } else {
        if (props.layer.default_style) {
            currentStyleSpecs.value[panel] = cloneDeep(props.layer.default_style.style_spec);
        } else {
            currentStyleSpecs.value[panel] = styleStore.getDefaultStyleSpec(currentFrame.value?.raster, props.layer.id);
        }
    }
}

function resetCurrentStyle() {
    resetCurrentStyleForPanel('A');
    resetCurrentStyleForPanel('B');
}

function selectStyle(style: LayerStyle, panel: 'A' | 'B') {
    mapLayerIds.value.forEach((mapLayerId) => {
        if (!currentFrame.value) return;
        if (!style.style_spec) return;
        currentStyleSpecs.value[panel] = cloneDeep(style.style_spec);
        compareStore.compareLayerStyles[panel][styleKey.value]= { style: cloneDeep(style), opacity: currentStyleSpecs.value[panel]?.opacity || 1};
        const visibileLayers = panel === 'A' ? compareStore.mapLayersA : compareStore.mapLayersB;
        const visibility = visibileLayers.includes(mapLayerId) ? 'visible' : 'none';
        const result = styleStore.returnMapLayerStyle(mapLayerId, style.style_spec, currentFrame.value, currentFrame.value.vector, visibility);
        if (result) {
            compareStore.updateMapLayerStyle(panel, mapLayerId, result);
        }
    });
}

watch(() => panelStore.draggingPanel, () => {
    emit('setLayerActive', false)
})

function cancel() {
    emit('setLayerActive', false)
}

watch(() => props.activeLayer, init)
const debouncedStyleSpecUpdated = (panel: 'A' | 'B', opacity: number) => {
    const localCurrentStyleSpecs = currentStyleSpecs.value[panel];
    if (localCurrentStyleSpecs) {
        localCurrentStyleSpecs.opacity = opacity;
        if (!compareStore.compareLayerStyles[panel][styleKey.value]) {
            compareStore.compareLayerStyles[panel][styleKey.value] = {
                style: styleStore.selectedLayerStyles[styleKey.value],
                opacity: opacity,
            }
        }
        compareStore.compareLayerStyles[panel][styleKey.value].style = {
            ...currentLayerStyles.value[panel].style,
            style_spec: localCurrentStyleSpecs
        }
        compareStore.compareLayerStyles[panel][styleKey.value].opacity = opacity;
        const styleSpec = compareStore.compareLayerStyles[panel][styleKey.value].style.style_spec
        mapLayerIds.value.forEach((mapLayerId) => {
            if (!currentFrame.value) return;
            if (!styleSpec) return;
            const visibileLayers = panel === 'A' ? compareStore.mapLayersA : compareStore.mapLayersB;
            const visibility = visibileLayers.includes(mapLayerId) ? 'visible' : 'none';
            const result = styleStore.returnMapLayerStyle(mapLayerId, styleSpec, currentFrame.value, currentFrame.value.vector, visibility);
            if (result) {
                compareStore.updateMapLayerStyle(panel, mapLayerId, result);
            }
        });
    }
}

const getPanelLabel = (panel: 'A' | 'B') => {
    return compareStore.orientation === 'vertical' ? panel === 'A' ? 'Left Map' : 'Right Map' : panel === 'A' ? 'Top Map' : 'Bottom Map';
}

const panels = ref(['A', 'B'] as const);
</script>

<template>
    <v-menu
        :model-value="props.activeLayer === props.layer"
        location="end center"
        :close-on-content-click="false"
        persistent
        no-click-animation
        @update:model-value="emit('setLayerActive', props.activeLayer !== props.layer)"
    >
        <template v-slot:activator="{ props }">
            <v-icon
                v-bind="props"
                icon="mdi-cog"
                v-tooltip="appliedStyleText"
            />
        </template>
        <v-card v-if="currentStyleSpecs.A && currentStyleSpecs.B" class="layer-style-card mt-5" color="background">
            <div class="px-4 py-2" style="background-color: rgb(var(--v-theme-surface)); height: 40px">
                Edit Style
                <span class="secondary-text">(Layer: {{ layer.name }})</span>

                <v-icon
                    icon="mdi-close"
                    style="position: absolute; top: 10px; right: 5px;"
                    @click="cancel"
                />
            </div>

            <v-card-text class="pa-2">
                <v-row v-if="compareStore.orientation === 'vertical'">
                    <v-col v-for="(panel, index) in panels" :key="panel" cols="6" style="position: relative;">
                        <v-card flat color="transparent">
                            <v-card-title>{{ getPanelLabel(panel) }}</v-card-title>
                            <v-card-text>
                                <div class="d-flex mb-1 mt-4 mx-2" style="align-items: center; column-gap: 5px;">
                                    <v-select
                                        :model-value="currentLayerStyles[panel].style"
                                        :items="availableStyles"
                                        item-value="id"
                                        :item-props="(item) => ({title: item.is_default ? item.name + ' (default)' : item.name})"
                                        label="Layer Style"
                                        density="compact"
                                        variant="outlined"
                                        no-data-text="No saved styles exist yet."
                                        return-object
                                        hide-details
                                        @update:model-value="selectStyle($event, panel)"
                                    ></v-select>
                                </div>
                                <table class="aligned-controls">
                                    <tbody>
                                        <tr>
                                            <td><v-label color="primary-text">Opacity</v-label></td>
                                            <td>
                                                <SliderNumericInput
                                                    :model="currentStyleSpecs[panel]?.opacity || 1"
                                                    :min="0.1"
                                                    :max="1"
                                                    :step="0.1"
                                                    @update="(v: number) => debouncedStyleSpecUpdated(panel, v)"
                                                />
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </v-card-text>
                        </v-card>
                        <v-divider v-if="index === 0" vertical style="position: absolute; right: 0; top: 0; bottom: 0; height: 100%;"></v-divider>
                    </v-col>
                </v-row>
                <template v-else>
                    <template v-for="(panel, index) in panels" :key="panel">
                        <v-row>
                            <v-card width="400" flat color="transparent">
                                <v-card-title>{{ getPanelLabel(panel) }}</v-card-title>
                                <v-card-text>
                                    <div class="d-flex mb-1 mt-4 mx-2" style="align-items: center; column-gap: 5px;">
                                        <v-select
                                            :model-value="currentLayerStyles[panel].style"
                                            :items="availableStyles"
                                            item-value="id"
                                            :item-props="(item) => ({title: item.is_default ? item.name + ' (default)' : item.name})"
                                            label="Layer Style"
                                            density="compact"
                                            variant="outlined"
                                            no-data-text="No saved styles exist yet."
                                            return-object
                                            hide-details
                                            @update:model-value="selectStyle($event, panel)"
                                        ></v-select>
                                    </div>
                                    <table class="aligned-controls">
                                        <tbody>
                                            <tr>
                                                <td><v-label color="primary-text">Opacity</v-label></td>
                                                <td>
                                                    <SliderNumericInput
                                                        :model="currentStyleSpecs[panel]?.opacity || 1"
                                                        :min="0.1"
                                                        :max="1"
                                                        :step="0.1"
                                                        @update="(v: number) => debouncedStyleSpecUpdated(panel, v)"
                                                    />
                                                </td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </v-card-text>
                            </v-card>
                        </v-row>
                        <v-divider v-if="index === 0" class="my-2"></v-divider>
                    </template>
                </template>
            </v-card-text>
        </v-card>
    </v-menu>
</template>

<style>
.layer-style-card  .v-label {
    font-size: 14px;
}
.aligned-controls {
    padding: 0 8px;
    width: 100%;
}
.aligned-controls td {
    padding-bottom: 4px;
}
.aligned-controls td:first-child {
    /* minimize width of first column (labels) */
    width: 1%;
    padding-right: 10px;
    vertical-align: middle;
    align-items: center;
}
.primary-control .v-icon:not(.mdi-checkbox-blank-outline) {
    color: rgb(var(--v-theme-primary)) !important
}
.tab-contents {
    background-color: rgb(var(--v-theme-surface-light));
}
.color-square {
    height: 25px;
    width: 25px;
    display: inline-block;
    margin: 5px 15px;
    border: 1px solid rgb(var(--v-theme-on-surface-variant));
}
.v-label {
    opacity: 1 !important;
}
.layer-style-card .v-btn:not(.v-btn--icon) {
    padding: 8px 16px !important;
}
.v-btn-group, .v-field {
    border: 1px solid #C9CBCE !important;
    border-radius: 4px;
}
.v-btn-group .v-btn {
    text-transform: none;
    border: none;
    color: rgb(var(--v-theme-secondary-text))
}
.v-btn-group:has(.v-btn--disabled) {
    border: 1px solid #C9CBCE44 !important;
}
.v-btn-group .v-btn--active {
    background-color: rgb(var(--v-theme-primary));
    color: rgb(var(--v-theme-button-text))
}
.v-btn-group .v-btn--active .v-btn__overlay {
    visibility: hidden;
}
.v-field__outline {
    visibility: hidden;
}
.layer-style-card .v-window__container {
    height: 400px!important;
    overflow-y: auto;
    overflow-x: hidden;
}
.filter-card {
    padding: 8px !important;
    margin-top: 8px;
    background-color: rgb(var(--v-theme-background)) !important;
    border: 1px solid rgb(var(--v-theme-border)) !important;
    box-shadow: none !important;
}
.filter-card.highlight {
    box-shadow: 0 0 1px 2px rgb(var(--v-theme-primary)) !important;
}
</style>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useStyleStore, useAppStore, useProjectStore } from '@/store';
import ColormapPreview from './ColormapPreview.vue';
import { THEMES } from '@/themes';
import { debounce } from 'lodash';
import { createColormap, updateColormap } from '@/api/rest';
import type { Colormap } from '@/types';

interface Marker {
    color: string,
    value: number,
}

interface MarkerBox {
    color: string,
    index: number,
    xRange: [number, number],
    yRange: [number, number],
}

const styleStore = useStyleStore();
const appStore = useAppStore();
const projectStore = useProjectStore();

const props = defineProps<{
  edit: Colormap | undefined
}>();

const emit = defineEmits(['close', 'submit'])

const name = ref()
const markers = ref([
    {color: '#000000', value: 0},
    {color: '#ffffff', value: 1},
])
const canvas = ref()
const draggingMarker = ref()
const hoverMarkerValue = ref()
const markerSize = 16
const outlineSize = 1

const markerBoxes = computed(() => markers.value.map((m: Marker, index: number) => {
    const {xRange, yRange} = getMarkerBoxRanges(m.value)
    return { color: m.color, xRange, yRange, index } as MarkerBox
}))

const markerOutlineColor = computed(() => {
    return THEMES[appStore.theme].colors['on-surface-variant']
})

const nameExistsRule = () => !styleStore.colormaps.filter(
    (c) => props.edit?.id !== c.id
).map(
    (c) => c.name
).includes(name.value) || `Colormap ''${name.value}'' already exists.`

const valid = computed(() => {
    return (
        name.value && name.value.length &&
        markers.value && markers.value.length &&
        nameExistsRule() === true &&
        markers.value.every((m: Marker) => !markerHasDuplicateValue(m))
    )
})

const currentColormap = computed(() => {
    return  {
        id: props.edit?.id,
        name: name.value,
        markers: markers.value,
        project: projectStore.currentProject?.id,
    }
})

function init() {
    if (props.edit?.markers) {
        name.value = props.edit.name
        markers.value = props.edit.markers
    }
    drawMarkers()
}

function submit() {
    if (valid.value) {
        if (props.edit) {
            updateColormap(currentColormap.value).then((result: Colormap) => {
                styleStore.colormaps = styleStore.colormaps.map((c) => {
                    if (c.id === props.edit?.id) return result
                    return c
                })
                emit('submit', result)
                emit('close')
            })
        } else {
            createColormap(currentColormap.value).then((result: Colormap) => {
                styleStore.colormaps.push(result)
                emit('submit', result)
                emit('close')
            })
        }
    }
}

function getMarkerBoxRanges(value: number) {
    const width = canvas.value.width
    const height = canvas.value.height
    const start = (width - markerSize - (outlineSize * 2)) * value + outlineSize
    const xRange: [number, number] = [start, start + markerSize]
    const yRange: [number, number] = [height - markerSize, height - outlineSize]
    return {xRange, yRange}
}

function drawMarkerPolygon(xRange: [number, number], yRange: [number, number], ctx: any) {
    const centerX = (xRange[1] - xRange[0]) / 2 + xRange[0]
    ctx.strokeStyle = markerOutlineColor.value
    ctx.moveTo(xRange[0], yRange[0])
    ctx.beginPath()
    ctx.lineTo(centerX, yRange[0] - (markerSize / 2))
    ctx.lineTo(xRange[1], yRange[0])
    ctx.lineTo(xRange[1], yRange[1])
    ctx.lineTo(xRange[0], yRange[1])
    ctx.lineTo(xRange[0], yRange[0])
    ctx.closePath()
    ctx.stroke()
}

function drawMarkerBox(mbox: MarkerBox, ctx: any) {
    const {color, xRange, yRange} = mbox
    ctx.fillStyle = color
    drawMarkerPolygon(xRange, yRange, ctx)
    ctx.fill()
}

function drawHoverMarker(value: number, ctx: any) {
    const {xRange, yRange} = getMarkerBoxRanges(value)
    drawMarkerPolygon(xRange, yRange, ctx)
    const centerX = (xRange[1] - xRange[0]) / 2 + xRange[0]
    const centerY = (yRange[1] - yRange[0]) / 2 + yRange[0] - outlineSize * 2
    const plusSignSize = markerSize - 6
    ctx.moveTo(centerX, centerY - plusSignSize / 2)
    ctx.lineTo(centerX, centerY + plusSignSize / 2)
    ctx.moveTo(centerX - plusSignSize / 2, centerY)
    ctx.lineTo(centerX + plusSignSize / 2, centerY)
    ctx.stroke()
}

function drawMarkers() {
    if (canvas.value) {
        // Update canvas drawing buffer dimensions to match CSS dimensions
        canvas.value.width = canvas.value.clientWidth;
        canvas.value.height = canvas.value.clientHeight;
        const rect = [0, 0, canvas.value.width, canvas.value.height]
        const ctx = canvas.value.getContext("2d")
        ctx.clearRect(...rect)
        markerBoxes.value.forEach((mbox) => drawMarkerBox(mbox, ctx))
        if (hoverMarkerValue.value) {
            drawHoverMarker(hoverMarkerValue.value, ctx)
        }
    }
}

function mouseDown(e: any) {
    const x = e.layerX
    const y = e. layerY
    draggingMarker.value = markerBoxes.value.find((mbox) => {
        const {xRange, yRange} = mbox
        return xRange[0] <= x && xRange[1] >= x && yRange[0] <= y && yRange[1] >= y
    })
    if (hoverMarkerValue.value) {
        addMarker(hoverMarkerValue.value)
        hoverMarkerValue.value = undefined
    }
}

function mouseMove(e: any) {
    const x = e.layerX
    const y = e. layerY
    const width = canvas.value.width
    let newValue = (x - markerSize / 2) / (width - markerSize - (outlineSize * 2))
    // Round to 2 significant figures
    newValue = parseFloat(newValue.toPrecision(2))
    hoverMarkerValue.value = undefined
    if (newValue >= 0 && newValue <= 1) {
        if (draggingMarker.value) {
            // dragging existing marker
            markers.value[draggingMarker.value.index].value = newValue
        } else if (y < 20) {
            // hovering over gradient while not dragging
            hoverMarkerValue.value = newValue
        }
    }
    drawMarkers()
}

function cancelDrag() {
    draggingMarker.value = undefined
}

function cancelHover() {
    hoverMarkerValue.value = undefined;
    drawMarkers()
}

function addMarker(value: number) {
    markers.value.push({
        color: '#000',
        value,
    })
    // immediately update order, don't wait for debounce
    updateMarkerOrder()
    drawMarkers()
}

function removeMarker(index: number) {
    markers.value.splice(index, 1)
    drawMarkers()
}

function markerHasDuplicateValue(marker: Marker) {
    const matches = markers.value.filter((m: Marker) => m.value === marker.value)
    return matches.length !== 1
}

function updateMarkerOrder() {
    markers.value = markers.value.toSorted((m1: Marker, m2: Marker) => m1.value - m2.value)
}

const debouncedUpdateMarkerOrder = debounce(updateMarkerOrder, 1000)

watch(markers, debouncedUpdateMarkerOrder, {deep: true})
onMounted(init)
</script>

<template>
    <v-card color="background" @mouseup="cancelDrag">
        <v-card-subtitle class="pa-2" style="background-color: rgb(var(--v-theme-surface))">
            New Colormap
            <v-icon
                icon="mdi-close"
                style="float:right"
                @click="emit('close')"
            />
        </v-card-subtitle>

        <v-card-text>
            <v-text-field
                label="Name"
                v-model="name"
                autofocus
                :rules="[nameExistsRule]"
                @keydown.enter="submit"
            />
            <div class="gradient-editor">
                <canvas
                    ref="canvas"
                    class="marker-canvas"
                    @mousedown="mouseDown"
                    @mousemove="mouseMove"
                    @mouseleave="cancelHover"
                />
                <div style="padding: 0px 8px">
                    <ColormapPreview
                        :colormap="currentColormap"
                        :discrete="false"
                        :nColors="-1"
                    />
                </div>
            </div>
            <div style="height: 200px; overflow-y: auto">
                <div v-for="marker, index in markers" class="py-2 marker-row">
                    <v-menu
                        :close-on-content-click="false"
                        open-on-hover
                        location="end"
                    >
                        <template v-slot:activator="{ props }">
                            <div
                                v-bind="props"
                                class="color-square"
                                style="margin: 0"
                                :style="{backgroundColor: marker.color}"
                            />
                        </template>
                        <v-card>
                            <v-color-picker
                                v-model:model-value="marker.color"
                                mode="hex"
                                @update:modelValue="drawMarkers"
                            />
                        </v-card>
                    </v-menu>
                    <v-number-input
                        v-model="marker.value"
                        :min="0"
                        :max="1"
                        :step="0.01"
                        :precision="2"
                        :style="{width: '80px'}"
                        variant="outlined"
                        controlVariant="stacked"
                        hide-details
                        @update:modelValue="drawMarkers"
                    />
                    <v-icon @click="removeMarker(index)">mdi-close</v-icon>
                    <v-icon
                        v-if="markerHasDuplicateValue(marker)"
                        v-tooltip="'Duplicate values found; colormap is invalid'"
                        color="error"
                    >
                        mdi-alert
                    </v-icon>
                </div>
                <div
                    class="py-2 marker-row"
                    style="color: rgb(var(--v-theme-primary)); cursor: pointer"
                    @click="addMarker(0.5)"
                >
                    + Add
                </div>
            </div>
        </v-card-text>

        <v-card-actions>
            <v-btn class="secondary-button" @click="emit('close')">
                <v-icon color="primary" class="mr-1">mdi-close-circle</v-icon>
                close
            </v-btn>
            <v-btn class="primary-button" variant="tonal" @click="submit" :disabled="!valid">
                <v-icon color="button-text" class="mr-1">mdi-plus-circle</v-icon>
                {{ props.edit ? 'Save' : 'Create' }} Colormap
            </v-btn>
        </v-card-actions>
    </v-card>
</template>

<style>
.marker-canvas {
    height: 45px;
    left: 0;
    right: 0;
    width: 100%;
    position: absolute;
}
.gradient-editor {
    width: 100%;
    margin-bottom: 24px;
    position: relative;
}
.marker-row {
    display: flex;
    align-items: center;
    column-gap: 10px;
}
.marker-row > * {
    flex-grow: 0;
}
</style>

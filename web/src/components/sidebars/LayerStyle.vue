<script setup lang="ts">
import { debounce, cloneDeep } from 'lodash'
import { computed, onMounted, ref, watch } from 'vue';
import type { AppliedColormap, Colormap, Layer, LayerStyle, StyleSpec } from '@/types';
import { createLayerStyle, deleteLayerStyle, getLayerStyles, updateLayerStyle, getVectorSummary, deleteColormap } from '@/api/rest';
import ColormapPreview from './ColormapPreview.vue';
import ColormapEditor from './ColormapEditor.vue';
import SliderNumericInput from '../SliderNumericInput.vue';

import { useStyleStore, useProjectStore, usePanelStore, useLayerStore, useAppStore } from '@/store';
const styleStore = useStyleStore();
const projectStore = useProjectStore();
const panelStore = usePanelStore();
const layerStore = useLayerStore();
const appStore = useAppStore();


const emit = defineEmits(["setLayerActive"]);
const props = defineProps<{
  layer: Layer;
  activeLayer: Layer | undefined;
}>();

const unsavedChanges = ref(true);
const showEditOptions = ref(false);
const showDeleteConfirmation = ref(false);
const showColormapEditor = ref(false);
const editColormapGroupName = ref();
const editColormap = ref<Colormap | undefined>();
const delColormap = ref<Colormap | undefined>();
const newNameMode = ref<'create' | 'update' | undefined>();
const newName = ref();
const tab = ref('color')
const availableStyles = ref<LayerStyle[]>();
const currentStyleSpec = ref<StyleSpec>();
const availableGroups = ref<string[]>([]);
const currentGroups = ref<Record<string, string | undefined>>({color: undefined, size: undefined});
const rasterBands = ref<Record<number, Record<string, number | string>>>();
const maxFilterId = ref<number>(1);
const focusedFilterId = ref<number | undefined>();
const highlightFilterId = ref<number | undefined>();

// for correct typing in template, assign to computed variable
const colormaps = computed(() => styleStore.colormaps);

const projectPermission = computed(() => {
    if (!projectStore.currentProject || !appStore.currentUser) return 'none'
    let user = appStore.currentUser
    let proj = projectStore.currentProject
    let perm = 'follower'
    if (proj.owner?.id === user.id || user.is_superuser ) {
        perm = "owner";
    } else if (proj.collaborators.map((u) => u.id).includes(user.id)) {
        perm = "collaborator";
    }
    return perm
})

const styleKey = computed(() => {
    return `${props.layer.id}.${props.layer.copy_id}`;
})

const currentLayerStyle = computed(() => {
    return styleStore.selectedLayerStyles[styleKey.value]
})

const setCurrentLayerStyle = (style: LayerStyle) => {
    styleStore.selectedLayerStyles[styleKey.value] = style
}

const appliedStyleName = computed(() => {
    if (currentLayerStyle.value.id) return currentLayerStyle.value.name
    else return undefined
})

const frames = computed(() => {
    return layerStore.layerFrames(props.layer)
})

const currentFrame = computed(() => {
    return frames.value.find(
        (f) => f.index === props.layer.current_frame_index
    )
})

const showRasterOptions = computed(() => {
    return frames.value.some((frame) => frame.raster)
})

const showVectorOptions = computed(() => {
    return frames.value.some((frame) => frame.vector)
})

const vectorProperties = computed(() => {
    const vector = currentFrame.value?.vector
    if (!vector) return undefined
    const summary = vector.summary
    if (!summary) {
        getVectorSummary(vector.id).then((result) => {
            vector.summary = result
        })
    } else return Object.entries(summary.properties).map(([k, v]) => ({...v, name: k}))
})

const dataRange = computed(() => {
    let absMin: number | undefined, absMax: number | undefined;
    const raster = currentFrame.value?.raster
    if (raster) {
        Object.values(raster.metadata.bands).forEach(({min, max}) => {
            if (!absMin || min < absMin) absMin = min;
            if (!absMax || max < absMax) absMax = max;
        })

    }
    if (absMin !== undefined && absMax !== undefined){
        return [Math.floor(absMin), Math.ceil(absMax)] as [number, number];
    }
    return undefined;
})

async function init() {
    if (props.activeLayer === props.layer) {
        getLayerStyles(props.layer.id).then((styles) => availableStyles.value = styles)
        resetCurrentStyle()
        fetchRasterBands()
        if (currentStyleSpec.value) setAvailableGroups()
    }
}

function resetCurrentStyle() {
    if (projectStore.currentViewState && !projectStore.currentViewStateLoaded) {
      // If styles are being applied from a view, don't overwrite them
      return
    }
    // When copying styles, use deep copies via cloneDeep
    // so that changes to the current style do not affect the original copy
    if (currentLayerStyle.value?.id) {
        // keep current style selected but discard any unsaved changes
        currentStyleSpec.value = cloneDeep(currentLayerStyle.value.style_spec)
    } else {
        // no current style selected, set one
        if (props.layer.default_style) {
            // apply layer's default style
            setCurrentLayerStyle(cloneDeep(props.layer.default_style))
            currentStyleSpec.value = cloneDeep(props.layer.default_style.style_spec)
        } else {
            // layer has no default style; apply None style
            setCurrentLayerStyle({name: 'None', is_default: true})
            currentStyleSpec.value = styleStore.getDefaultStyleSpec(currentFrame.value?.raster, props.layer.id);
        }
    }
}

function selectStyle(style: LayerStyle) {
    setCurrentLayerStyle(style)
    currentStyleSpec.value = style.style_spec
    currentGroups.value = {color: undefined, size: undefined}
}

function fetchRasterBands() {
    if (!currentStyleSpec.value) return
    if (showRasterOptions.value) {
        setGroupColorMode('all', 'none')
        if (frames.value.length) {
            if (currentFrame.value?.raster) {
                rasterBands.value = currentFrame.value.raster.metadata.bands;
            }
        }
    }
}

function setAvailableGroups() {
    if (showRasterOptions.value && rasterBands.value) {
        const bandNames = Object.keys(rasterBands.value).map((name) => `Band ${name}`)
        availableGroups.value = bandNames;
    } else if (showVectorOptions.value) {
        const vector = currentFrame.value?.vector
        if (!vector) return undefined
        const summary = vector.summary
        if (summary) {
            availableGroups.value = []
            if (summary.feature_types.includes('Point'))  availableGroups.value.push('points')
            if (summary.feature_types.includes('LineString'))  availableGroups.value.push('lines')
            if (summary.feature_types.includes('MultiPolygon') || summary.feature_types.includes('Polygon'))  availableGroups.value.push('polygons')
        } else {
            availableGroups.value = ['polygons', 'lines', 'points']
        }
    }
    if (availableGroups.value?.length) {
        const firstGroup = availableGroups.value[0]
        if (!currentGroups.value['color']) {
            const currentSpecGroups = currentStyleSpec.value?.colors.map((c) => c.name)
            currentGroups.value['color'] = currentSpecGroups?.length ? currentSpecGroups[0] : firstGroup
        }
        if (!currentGroups.value['size']) {
            const currentSpecGroups = currentStyleSpec.value?.sizes.map((c) => c.name)
            currentGroups.value['size'] = currentSpecGroups?.length ? currentSpecGroups[0] : firstGroup
        }
    }
}

function setCurrentColorGroups(different: boolean | null) {
    if (!currentStyleSpec.value) return
    const defaultStyle = styleStore.getDefaultStyleSpec(currentFrame.value?.raster, props.layer.id)
    let all = currentStyleSpec.value.colors.find((group) => group.name === 'all')
    if (!all) all = defaultStyle.colors.find((group) => group.name === 'all')
    if (different) {
        if (showRasterOptions.value && rasterBands.value) {
            currentStyleSpec.value.colors = availableGroups.value.map((name) => {
                return { ...all, visible: true, use_feature_props: true, name }
            })
            availableGroups.value.forEach((name) => setGroupColorMode(name, 'none'))
        } else if (showVectorOptions.value) {
            currentStyleSpec.value.colors = availableGroups.value.map((name) => {
                return { ...JSON.parse(JSON.stringify(all)), visible: true, name }
            })
        }
        if (availableGroups.value?.length) currentGroups.value['color'] = availableGroups.value[0]
    } else {
        if (currentGroups.value['color']) {
            const currentGroupOptions = currentStyleSpec.value.colors.find((c) => c.name === currentGroups.value['color'])
            currentStyleSpec.value.colors = [{
                ...currentGroupOptions,
                name: 'all',
                visible: true,
                use_feature_props: true,
            }]
        } else {
            currentStyleSpec.value.colors = [...defaultStyle.colors]
        }
        if (showRasterOptions.value) setGroupColorMode('all', 'none')
        currentGroups.value['color'] = 'all'
    }
}

function setGroupColorMode(groupName: string, colorMode: string) {
    if (!currentStyleSpec.value) return
    currentStyleSpec.value.colors = currentStyleSpec.value.colors.map(
        (c) => {
            if (c.name === groupName) {
                if (colorMode === 'colormap') {
                    if (!c.colormap) return {
                        ...c,
                        colormap: {
                            discrete: false,
                            n_colors: 5,
                            range: dataRange.value,
                            null_color: 'transparent',
                            color_by: showRasterOptions.value ? 'value' : undefined
                        },
                        single_color: undefined,
                    }
                } else if (colorMode === 'single_color' && !c.single_color) {
                    return {...c, colormap: undefined, single_color: styleStore.getDefaultColor(props.layer.id)}
                } else if (colorMode === 'none') {
                  return {...c, colormap: undefined, single_color: undefined}
                }
            }
            return c
        }
    )
}

function getColormap(appliedColormap: AppliedColormap | undefined) {
    if (!appliedColormap) return undefined
    return styleStore.colormaps.find((cmap) => cmap.id === appliedColormap.id)
}

function setGroupColormap(groupName: string, colormap: Colormap) {
    if (!currentStyleSpec.value) return
    currentStyleSpec.value.colors = currentStyleSpec.value.colors.map(
        (c) => {
            if (c.name === groupName) {
                return {
                    ...c,
                    colormap: {
                        ...c.colormap,
                        id: colormap.id,
                    },
                    single_color: undefined
                }
            }
            return c
        }
    )
}

function openColormapEditor(groupName: string, colormap: Colormap | undefined) {
    showColormapEditor.value = true
    editColormapGroupName.value = groupName
    editColormap.value = colormap
}

function confirmDeleteColormap() {
    if (delColormap.value?.id) {
        deleteColormap(delColormap.value.id).then(() => {
            delColormap.value = undefined
            styleStore.colormaps = styleStore.colormaps.filter((c) => c.id !== delColormap.value?.id)
            // update other styles in case colormap changed to default
            layerStore.selectedLayers.forEach((layer) => {
                const layerStyleKey = `${layer.id}.${layer.copy_id}`
                getLayerStyles(layer.id).then((styles) => {
                    const updated = styles.find((s) => s.id === styleStore.selectedLayerStyles[layerStyleKey].id)
                    if (updated) {
                        styleStore.selectedLayerStyles[layerStyleKey] = updated
                        if (layer.id === props.layer.id) {
                            availableStyles.value = styles;
                            currentStyleSpec.value = updated.style_spec;
                        }
                        styleStore.updateLayerStyles(layer)
                    }
                })
            })
        })
    }
}

function setSizeGroups(different: boolean | null) {
    if (!currentStyleSpec.value) return
    if (different) {
        if (showVectorOptions.value) {
            currentGroups.value['size'] = 'points'
            const all = currentStyleSpec.value.sizes.find((group) => group.name === 'all')
            if (all) {
                currentStyleSpec.value.sizes = availableGroups.value.map((name) => {
                    return {  ...JSON.parse(JSON.stringify(all)), name }
                })
            }
        }
    } else {
        if (currentGroups.value['size']) {
            const currentGroupOptions = currentStyleSpec.value.sizes.find((s) => s.name === currentGroups.value['size'])
            currentStyleSpec.value.sizes = [{
                zoom_scaling: true,
                ...currentGroupOptions,
                name: 'all',
            }]
        } else {
            currentStyleSpec.value.sizes = [...styleStore.getDefaultStyleSpec(
                currentFrame.value?.raster,
                props.layer.id,
            ).sizes]
        }
        currentGroups.value['size'] = 'all'
    }
}

function setGroupSizeMode(groupName: string, sizeMode: string) {
    if (!currentStyleSpec.value) return
    currentStyleSpec.value.sizes = currentStyleSpec.value.sizes.map(
        (s) => {
            if (s.name === groupName) {
                if (sizeMode === 'single_size') {
                    return {...s, single_size: 5, size_range: undefined}
                } else if (sizeMode === 'range') {
                    return { ...s, size_range: {
                        minimum: 1,
                        maximum: 10,
                        null_size: {
                            transparency: true,
                            size: 0
                        }
                    }, single_size: undefined}
                }
            }
            return s
        }
    )
}

function addFilter() {
    if (!currentStyleSpec.value) return;
    currentStyleSpec.value.filters = [
        {
            id: maxFilterId.value,
            include: true,
            transparency: true,
            apply: true
        },
        ...currentStyleSpec.value.filters.filter((f) => f.filter_by),
    ]
    focusedFilterId.value = maxFilterId.value
    highlightFilterId.value = maxFilterId.value
    maxFilterId.value += 1
    setTimeout(() => highlightFilterId.value = undefined, 1000)
}

function focusFilter(filterId: number | undefined) {
    if (!currentStyleSpec.value || !filterId) return;
    currentStyleSpec.value.filters = currentStyleSpec.value.filters.filter((f) => f.filter_by)
    focusedFilterId.value = filterId;
}

function removeFilter(filterId: number | undefined) {
    if (!currentStyleSpec.value || !filterId) return
    currentStyleSpec.value.filters = currentStyleSpec.value.filters.filter((f) => f.id !== filterId)
}

function updateFilterBy(filterId: number | undefined, propertyName: string) {
    if (!currentStyleSpec.value || !filterId || !vectorProperties.value) return
    const property = vectorProperties.value.find((p) => p.name === propertyName)
    currentStyleSpec.value.filters = currentStyleSpec.value.filters.map((f) => {
        if (f.id === filterId) {
            if (property?.range) {
                f.range = property.range
                f.list = undefined
            } else if (property?.value_set) {
                f.list = []
                f.range = undefined
            }
        }
        return f
    })
}

function cancel() {
    resetCurrentStyle()
    emit('setLayerActive', false)
}

function save() {
    if (!currentLayerStyle.value?.id || !currentStyleSpec.value) return;
    updateLayerStyle(
        currentLayerStyle.value.id,
        {
            name: newName.value || currentLayerStyle.value.name,
            is_default: currentLayerStyle.value.is_default,
            style_spec: currentStyleSpec.value,
        }
    ).then((style) => {
        if (style) {
            setCurrentLayerStyle(style);
            newName.value = undefined;
            newNameMode.value = undefined;
            // update other styles in case default overriden
            getLayerStyles(props.layer.id).then((styles) => availableStyles.value = styles)
            refreshLayer()
            unsavedChanges.value = false;
        }
    })
}

function saveAsNew() {
    if (!projectStore.currentProject || !currentStyleSpec.value) return;
    createLayerStyle({
        ...currentLayerStyle.value,
        name: newName.value,
        layer: props.layer.id,
        project: projectStore.currentProject.id,
        style_spec: currentStyleSpec.value,
    }).then((style: LayerStyle) => {
        if (style) {
            setCurrentLayerStyle(style);
            newName.value = undefined;
            newNameMode.value = undefined;
            // update other styles in case default overriden
            getLayerStyles(props.layer.id).then((styles) => availableStyles.value = styles)
            refreshLayer()
            unsavedChanges.value = false;
        }
    })
}

function deleteStyle() {
    if (!currentLayerStyle.value?.id) return;
    deleteLayerStyle(currentLayerStyle.value.id).then(() => {
        getLayerStyles(props.layer.id).then((styles) => {
            availableStyles.value = styles;
            const newDefault = styles.find((style) => style.is_default)
            if (newDefault) {
                setCurrentLayerStyle(newDefault);
                currentStyleSpec.value = newDefault.style_spec;
            } else {
                setCurrentLayerStyle({name: 'None', is_default: true});
                currentStyleSpec.value = {...styleStore.getDefaultStyleSpec(
                    currentFrame.value?.raster,
                    props.layer.id,
                )}
            }
            refreshLayer()
            showDeleteConfirmation.value = false;
        })
    })
}

function refreshLayer() {
    layerStore.fetchAvailableLayer(props.layer.id)
}

watch(() => panelStore.draggingPanel, () => {
    emit('setLayerActive', false)
})

const debouncedStyleSpecUpdated = debounce(() => {
    if (currentStyleSpec.value) {
        styleStore.selectedLayerStyles[styleKey.value] = {
            ...currentLayerStyle.value,
            style_spec: currentStyleSpec.value
        }
        styleStore.updateLayerStyles(props.layer)
        setAvailableGroups()
        unsavedChanges.value = true
    }
}, 100)
watch(currentStyleSpec, debouncedStyleSpecUpdated, {deep: true})

watch(() => props.activeLayer, init)
onMounted(resetCurrentStyle)
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
                v-tooltip="appliedStyleName ? 'Style: ' + appliedStyleName : 'Configure styling'"
            />
        </template>
        <v-card v-if="currentStyleSpec" class="layer-style-card mt-5" color="background" width="510">
            <div class="px-4 py-2" style="background-color: rgb(var(--v-theme-surface)); min-height: 40px">
                Edit Style
                <span class="secondary-text">(Layer: {{ layer.name }})</span>

                <v-icon
                    icon="mdi-close"
                    style="position: absolute; top: 10px; right: 5px;"
                    v-tooltip="'Warning: unsaved changes will be discarded'"
                    @click="cancel"
                />
            </div>

            <v-card-text class="pa-2">
                <div class="d-flex mb-1 mt-4 mx-2" style="align-items: center; column-gap: 5px;">
                    <v-select
                        :model-value="currentLayerStyle"
                        :items="availableStyles"
                        item-value="id"
                        :item-props="(item) => ({title: item.is_default ? item.name + ' (default)' : item.name})"
                        label="Layer Style"
                        density="compact"
                        variant="outlined"
                        no-data-text="No saved styles exist yet."
                        return-object
                        hide-details
                        @update:model-value="selectStyle"
                    ></v-select>
                    <v-menu v-model="showEditOptions" open-on-hover :close-on-content-click="false" location="start">
                        <template v-slot:activator="{ props }">
                            <v-icon v-bind="props" :disabled="!currentLayerStyle.id" icon="mdi-pencil"/>
                        </template>
                        <v-list v-if="currentLayerStyle.id">
                            <v-list-item @click="showEditOptions = false; newNameMode = 'update'">Rename</v-list-item>
                            <v-list-item @click="showEditOptions = false; showDeleteConfirmation = true">Delete</v-list-item>
                        </v-list>
                    </v-menu>
                </div>

                <div class="d-flex mx-2">
                    <v-checkbox
                        v-model="currentLayerStyle.is_default"
                        label="Set as default style"
                        class="primary-control"
                        density="compact"
                        hide-details
                    />
                </div>

                <table class="aligned-controls px-2">
                    <tbody>
                        <tr v-if="frames.length > 1">
                            <td><v-label>Default Frame</v-label></td>
                            <td>
                                <SliderNumericInput
                                    :model="currentStyleSpec.default_frame + 1"
                                    :max="frames.length"
                                    @update="(v: number) => {if (currentStyleSpec) currentStyleSpec.default_frame = v - 1}"
                                />
                            </td>
                        </tr>
                        <tr>
                            <td><v-label color="primary-text">Opacity</v-label></td>
                            <td>
                                <SliderNumericInput
                                    :model="currentStyleSpec.opacity"
                                    :min="0.1"
                                    :max="1"
                                    :step="0.1"
                                    @update="(v: number) => {if (currentStyleSpec) currentStyleSpec.opacity = v}"
                                />
                            </td>
                        </tr>
                    </tbody>
                </table>

                <v-tabs v-model="tab" align-tabs="center" fixed-tabs density="compact" color="primary" class="mt-2 mx-2">
                    <v-tab value="color">
                        <v-icon icon="mdi-palette" class="mr-1" :color="tab === 'color' ? 'primary' : 'secondary-text'"/>
                        Color
                    </v-tab>
                    <v-tab value="size">
                        <span class="material-symbols-outlined mr-1" :class="tab == 'size' ? 'text-primary' : 'text-secondary-text'">
                            straighten
                        </span>
                        Size
                    </v-tab>
                    <v-tab value="filters">
                        <v-icon icon="mdi-filter" class="mr-1" :color="tab === 'filters' ? 'primary' : 'secondary-text'"/>
                        Filters
                    </v-tab>
                </v-tabs>

                <v-window v-model="tab" class="tab-contents mx-2 px-2">
                    <v-window-item value="color" class="pa-2">
                        <div v-if="showRasterOptions">
                            <v-label class="secondary-text px-3">Raster Options</v-label>
                            <v-divider class="mt-1 mb-2"/>
                            <table class="aligned-controls">
                                <tbody>
                                    <tr>
                                        <td colspan="2">
                                            <v-checkbox
                                                v-if="availableGroups.length > 1"
                                                label="Different color per band (multi-band images)"
                                                :model-value="Array.from(currentStyleSpec.colors.keys()).length > 1"
                                                density="compact"
                                                class="primary-control"
                                                hide-details
                                                @update:model-value="setCurrentColorGroups"
                                            />
                                        </td>
                                    </tr>
                                    <template v-for="group in currentStyleSpec.colors.filter((c) => c.name === currentGroups['color'])">
                                        <tr v-if="currentGroups['color'] !== 'all'">
                                            <td><v-label>Band</v-label></td>
                                            <td class="d-flex" style="align-items: center; column-gap: 10px;">
                                                <v-select
                                                    v-model="currentGroups['color']"
                                                    :items="availableGroups"
                                                    density="compact"
                                                    variant="outlined"
                                                    hide-details
                                                ></v-select>
                                                <v-icon
                                                    :icon="group.visible ? 'mdi-eye-outline' : 'mdi-eye-off-outline'"
                                                    @click="group.visible = !group.visible"
                                                    size="large"
                                                />
                                            </td>
                                        </tr>
                                        <tr v-if="currentGroups['color'] !== 'all'">
                                            <td colspan="2">
                                                <v-label class="secondary-text py-2">Selected Band Options [{{ currentGroups['color'] }}]</v-label>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td><v-label :class="group.visible ? '' : 'helper-text'">Color scheme</v-label></td>
                                            <td>
                                                <div class="d-flex" style="align-items: center;">
                                                    <v-btn-toggle
                                                        :model-value="group.single_color ? 'single_color' : group.colormap ? 'colormap' : 'none'"
                                                        density="compact"
                                                        variant="outlined"
                                                        divided
                                                        mandatory
                                                        :disabled="!group.visible"
                                                        @update:model-value="(value: string) => setGroupColorMode(group.name, value)"
                                                    >
                                                        <v-btn :value="'none'">None</v-btn>
                                                        <v-btn :value="'single_color'">1 Color</v-btn>
                                                        <v-btn :value="'colormap'">Colormap</v-btn>
                                                    </v-btn-toggle>
                                                    <v-menu
                                                        v-if="group.single_color"
                                                        :disabled="!group.visible"
                                                        :close-on-content-click="false"
                                                        open-on-hover
                                                        location="end"
                                                    >
                                                        <template v-slot:activator="{ props }">
                                                            <div
                                                                v-bind="props"
                                                                class="color-square"
                                                                :style="{backgroundColor: group.single_color, opacity: group.visible ? 1 : 0.5}"
                                                            ></div>
                                                        </template>
                                                        <v-card>
                                                            <v-color-picker
                                                                v-model:model-value="group.single_color"
                                                                mode="rgb"
                                                            />
                                                        </v-card>
                                                    </v-menu>
                                                </div>
                                            </td>
                                        </tr>
                                        <tr v-if="group.colormap">
                                            <td><v-label :class="group.visible ? '' : 'helper-text'">Colormap</v-label></td>
                                            <td>
                                                <v-select
                                                    :model-value="getColormap(group.colormap)"
                                                    :items="colormaps"
                                                    item-title="name"
                                                    density="compact"
                                                    variant="outlined"
                                                    hide-details
                                                    return-object
                                                    :disabled="!group.visible"
                                                    @update:model-value="(v: Colormap) => setGroupColormap(group.name, v)"
                                                >
                                                    <template v-slot:item="{ props, internalItem }">
                                                        <v-list-item v-bind="props">
                                                            <template v-slot:append>
                                                                <v-icon
                                                                    v-if="internalItem.raw.project && ['owner', 'collaborator'].includes(projectPermission)"
                                                                    icon="mdi-pencil"
                                                                    class="ml-2"
                                                                    @click="openColormapEditor(group.name, internalItem.raw)"
                                                                />
                                                                <v-icon
                                                                    v-if="internalItem.raw.project && ['owner', 'collaborator'].includes(projectPermission)"
                                                                    icon="mdi-trash-can"
                                                                    class="ml-2"
                                                                    @click="delColormap = internalItem.raw"
                                                                />
                                                                <div style="width: 300px" class="ml-2">
                                                                    <colormap-preview
                                                                        :colormap="internalItem.raw"
                                                                        :discrete="group.colormap?.discrete || false"
                                                                        :nColors="group.colormap?.n_colors || -1"
                                                                    />
                                                                </div>
                                                            </template>
                                                        </v-list-item>
                                                    </template>
                                                    <template v-slot:selection="{ internalItem }">
                                                        <span class="pr-15" v-if="getColormap(group.colormap)?.markers">{{ internalItem.title }}</span>
                                                        <div style="width: 300px" class="ml-2" v-if="group.colormap && getColormap(group.colormap)?.markers">
                                                            <colormap-preview
                                                                :colormap="internalItem.raw"
                                                                :discrete="group.colormap.discrete || false"
                                                                :nColors="group.colormap.n_colors || -1"
                                                            />
                                                        </div>
                                                        <span v-else class="secondary-text">Select Colormap</span>
                                                    </template>
                                                    <template v-slot:prepend-item>
                                                        <v-list-item
                                                            v-if="['owner', 'collaborator'].includes(projectPermission)"
                                                            @click="openColormapEditor(group.name, undefined)"
                                                        >
                                                            <div style="color: rgb(var(--v-theme-primary)); align-items: center; display: flex">
                                                                <v-icon color="primary">mdi-plus</v-icon>
                                                                Create Custom Colormap
                                                            </div>
                                                        </v-list-item>
                                                    </template>
                                                </v-select>
                                            </td>
                                        </tr>
                                        <tr v-if="group.colormap">
                                            <td><v-label :class="group.visible && getColormap(group.colormap)?.markers ? '' : 'helper-text'">Colormap class</v-label></td>
                                            <td>
                                                <v-btn-toggle
                                                    :model-value="group.colormap?.discrete ? 'discrete' : 'continuous'"
                                                    density="compact"
                                                    variant="outlined"
                                                    divided
                                                    mandatory
                                                    :disabled="!group.visible || !getColormap(group.colormap)?.markers"
                                                    @update:model-value="(value: string) => {if (group.colormap) group.colormap.discrete = value === 'discrete'}"
                                                >
                                                    <v-btn :value="'discrete'">Discrete</v-btn>
                                                    <v-btn :value="'continuous'">Continuous</v-btn>
                                                </v-btn-toggle>
                                            </td>
                                        </tr>
                                        <tr v-if="group.colormap">
                                            <td><v-label :class="group.visible && getColormap(group.colormap)?.markers && group.colormap?.discrete ? '' : 'helper-text'">No. of colors</v-label></td>
                                            <td>
                                                <SliderNumericInput
                                                    :model="group.colormap?.n_colors"
                                                    :min="2"
                                                    :max="30"
                                                    :disabled="!group.visible || !getColormap(group.colormap)?.markers || !group.colormap?.discrete"
                                                    @update="(v: number) => {if (group.colormap) group.colormap.n_colors = v}"
                                                />
                                            </td>
                                        </tr>
                                        <tr v-if="group.colormap">
                                            <td><v-label :class="group.visible && getColormap(group.colormap)?.markers ? '' : 'helper-text'">Range</v-label></td>
                                            <td>
                                                <SliderNumericInput
                                                    v-if="dataRange"
                                                    :rangeModel="group.colormap?.range || dataRange"
                                                    :min="dataRange[0]"
                                                    :max="dataRange[1]"
                                                    :disabled="!group.visible || !getColormap(group.colormap)?.markers"
                                                    @update="(v: [number, number]) => {if (group.colormap) group.colormap.range = v}"
                                                />
                                            </td>
                                        </tr>
                                        <tr v-if="group.colormap">
                                            <td>
                                                <v-label :class="group.visible && getColormap(group.colormap)?.markers ? '' : 'helper-text'">Clamping</v-label>
                                                <v-icon
                                                    icon="mdi-information-outline"
                                                    color="primary"
                                                    size="small"
                                                    :class="group.visible && getColormap(group.colormap)?.markers ? 'ml-2' : 'helper-text ml-2'"
                                                    v-tooltip="'When enabled, values outside the selected range will be clamped to the ends of the colormap. When disabled, those values will appear transparent.'"
                                                />
                                            </td>
                                            <td>
                                                <v-btn-toggle
                                                    :model-value="group.colormap?.clamp === false ? 'disable' : 'enable'"
                                                    density="compact"
                                                    variant="outlined"
                                                    divided
                                                    mandatory
                                                    :disabled="!group.visible || !getColormap(group.colormap)?.markers"
                                                    @update:model-value="(value: string) => {if (group.colormap) group.colormap.clamp = value === 'enable'}"
                                                >
                                                    <v-btn :value="'disable'">Disable</v-btn>
                                                    <v-btn :value="'enable'">Enable</v-btn>
                                                </v-btn-toggle>
                                            </td>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                        <div v-if="showVectorOptions">
                            <v-label class="secondary-text px-3">Vector Options</v-label>
                            <v-divider class="mt-1 mb-2"/>
                            <table class="aligned-controls">
                                <tbody>
                                    <tr>
                                        <td colspan="2">
                                            <v-checkbox
                                                v-if="availableGroups.length > 1"
                                                label="Different color per feature type"
                                                :model-value="Array.from(currentStyleSpec.colors.keys()).length > 1"
                                                density="compact"
                                                class="primary-control"
                                                hide-details
                                                @update:model-value="setCurrentColorGroups"
                                            />
                                        </td>
                                    </tr>
                                    <template v-for="group in currentStyleSpec.colors.filter((c) => c.name === currentGroups['color'])">
                                        <tr v-if="currentGroups['color'] !== 'all'">
                                            <td><v-label>Feature Type</v-label></td>
                                            <td class="d-flex" style="align-items: center; column-gap: 10px;"   >
                                                <v-select
                                                    v-model="currentGroups['color']"
                                                    :items="availableGroups"
                                                    density="compact"
                                                    variant="outlined"
                                                    hide-details
                                                ></v-select>
                                                <v-icon
                                                    :icon="group.visible ? 'mdi-eye-outline' : 'mdi-eye-off-outline'"
                                                    @click="group.visible = !group.visible"
                                                    size="large"
                                                />
                                            </td>
                                        </tr>
                                        <tr v-if="currentGroups['color'] !== 'all'">
                                            <td colspan="2">
                                                <v-label class="secondary-text py-2">Selected Feature Type Options [{{ currentGroups['color'] }}]</v-label>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td colSpan="2">
                                                <v-checkbox
                                                    v-model="group.use_feature_props"
                                                    :disabled="!group.visible"
                                                    density="compact"
                                                    class="primary-control"
                                                    hide-details
                                                >
                                                    <template v-slot:label>
                                                        <span>
                                                            Prioritize feature color properties
                                                        </span>
                                                        <v-icon
                                                            icon="mdi-information-outline"
                                                            class="ml-2"
                                                            v-tooltip="'When enabled, features with fill and stroke properties will use those colors. Features without those properties will use the specified color configuration.'"
                                                        />
                                                    </template>
                                                </v-checkbox>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td><v-label :class="group.visible ? '' : 'helper-text'">Color scheme</v-label></td>
                                            <td>
                                                <div class="d-flex" style="align-items: center;">
                                                    <v-btn-toggle
                                                        :model-value="group.single_color ? 'single_color' : 'colormap'"
                                                        density="compact"
                                                        variant="outlined"
                                                        divided
                                                        mandatory
                                                        :disabled="!group.visible"
                                                        @update:model-value="(value: string) => setGroupColorMode(group.name, value)"
                                                    >
                                                        <v-btn :value="'single_color'">Single Color</v-btn>
                                                        <v-btn :value="'colormap'">Colormap</v-btn>
                                                    </v-btn-toggle>
                                                    <v-menu
                                                        v-if="group.single_color"
                                                        :disabled="!group.visible"
                                                        :close-on-content-click="false"
                                                        open-on-hover
                                                        location="end"
                                                    >
                                                        <template v-slot:activator="{ props }">
                                                            <div
                                                                v-bind="props"
                                                                class="color-square"
                                                                :style="{backgroundColor: group.single_color, opacity: group.visible ? 1 : 0.5}"
                                                            ></div>
                                                        </template>
                                                        <v-card>
                                                            <v-color-picker
                                                                v-model:model-value="group.single_color"
                                                                mode="rgb"
                                                            />
                                                        </v-card>
                                                    </v-menu>
                                                </div>
                                            </td>
                                        </tr>
                                        <template v-if="group.colormap">
                                            <tr>
                                                <td><v-label :class="group.visible ? '' : 'helper-text'">Color by property</v-label></td>
                                                <td>
                                                    <v-select
                                                        v-if="vectorProperties"
                                                        v-model="group.colormap.color_by"
                                                        :items="vectorProperties"
                                                        :disabled="!group.visible"
                                                        item-title="name"
                                                        item-value="name"
                                                        density="compact"
                                                        variant="outlined"
                                                        placeholder="Select property"
                                                        hide-details
                                                        @update:model-value="(v) => {if (group.colormap) {
                                                            if (!group.colormap.id) setGroupColormap(group.name, colormaps[0])
                                                            group.colormap.discrete = !vectorProperties?.find((p) => p.name === v)?.range;
                                                        }}"
                                                    >
                                                        <template v-slot:item="{ props, internalItem }">
                                                            <v-list-item v-bind="props">
                                                                <template v-slot:append>
                                                                    <v-chip size="small" v-if="(internalItem.raw as Record<string, any>).sample_label">{{ (internalItem.raw as Record<string, any>).sample_label }}</v-chip>
                                                                </template>
                                                            </v-list-item>
                                                        </template>
                                                    </v-select>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td><v-label :class="group.visible && group.colormap.color_by ? '' : 'helper-text'">Colormap</v-label></td>
                                                <td>
                                                    <v-select
                                                        :model-value="getColormap(group.colormap)"
                                                        :items="colormaps"
                                                        :disabled="!group.visible || !group.colormap.color_by"
                                                        item-title="name"
                                                        density="compact"
                                                        variant="outlined"
                                                        hide-details
                                                        return-object
                                                        @update:model-value="(v: Colormap) => setGroupColormap(group.name, v)"
                                                    >
                                                        <template v-slot:item="{ props, internalItem }">
                                                            <v-list-item v-bind="props">
                                                                <template v-slot:append>
                                                                    <v-icon
                                                                        v-if="internalItem.raw.project && ['owner', 'collaborator'].includes(projectPermission)"
                                                                        icon="mdi-pencil"
                                                                        class="ml-2"
                                                                        @click="openColormapEditor(group.name, internalItem.raw)"
                                                                    />
                                                                    <v-icon
                                                                        v-if="internalItem.raw.project && ['owner', 'collaborator'].includes(projectPermission)"
                                                                        icon="mdi-trash-can"
                                                                        class="ml-2"
                                                                        @click="delColormap = internalItem.raw"
                                                                    />
                                                                    <div style="width: 300px" class="ml-2">
                                                                        <colormap-preview
                                                                            :colormap="internalItem.raw"
                                                                            :discrete="group.colormap.discrete || false"
                                                                            :nColors="group.colormap.n_colors || -1"
                                                                        />
                                                                    </div>
                                                                </template>
                                                            </v-list-item>
                                                        </template>
                                                        <template v-slot:selection="{ internalItem }">
                                                            <span class="pr-15" v-if="getColormap(group.colormap)?.markers">{{ internalItem.title }}</span>
                                                            <div style="width: 300px" class="ml-2" v-if="getColormap(group.colormap)?.markers">
                                                                <colormap-preview
                                                                    :colormap="internalItem.raw"
                                                                    :discrete="group.colormap.discrete || false"
                                                                    :nColors="group.colormap.n_colors || -1"
                                                                />
                                                            </div>
                                                            <span v-else class="secondary-text">Select Colormap</span>
                                                        </template>
                                                        <template v-slot:prepend-item>
                                                            <v-list-item
                                                                v-if="['owner', 'collaborator'].includes(projectPermission)"
                                                                @click="openColormapEditor(group.name, undefined)"
                                                            >
                                                                <div style="color: rgb(var(--v-theme-primary)); align-items: center; display: flex">
                                                                    <v-icon color="primary">mdi-plus</v-icon>
                                                                    Create Custom Colormap
                                                                </div>
                                                            </v-list-item>
                                                        </template>
                                                    </v-select>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td>
                                                    <v-label :class="group.visible && getColormap(group.colormap)?.markers && vectorProperties?.find((p) => p.name === group.colormap?.color_by)?.range ? '' : 'helper-text'">
                                                        Colormap class
                                                    </v-label>
                                                </td>
                                                <td>
                                                    <v-btn-toggle
                                                        :model-value="group.colormap.discrete ? 'discrete' : 'continuous'"
                                                        density="compact"
                                                        variant="outlined"
                                                        divided
                                                        mandatory
                                                        :disabled="!group.visible || !getColormap(group.colormap)?.markers"
                                                        @update:model-value="(value: string) => {if (group.colormap) group.colormap.discrete = value === 'discrete'}"
                                                    >
                                                        <v-btn :value="'discrete'">Discrete</v-btn>
                                                        <v-btn :value="'continuous'">Continuous</v-btn>
                                                    </v-btn-toggle>
                                                </td>
                                            </tr>
                                            <tr>
                                                <td><v-label :class="group.visible && getColormap(group.colormap)?.markers && group.colormap.discrete ? '' : 'helper-text'">No. of colors</v-label></td>
                                                <td>
                                                    <SliderNumericInput
                                                        :model="group.colormap.n_colors"
                                                        :min="2"
                                                        :max="30"
                                                        :disabled="!group.visible || !getColormap(group.colormap)?.markers || !group.colormap?.discrete"
                                                        @update="(v: number) => {if (group.colormap) group.colormap.n_colors = v}"
                                                    />
                                                </td>
                                            </tr>
                                            <tr>
                                                <td><v-label :class="group.visible && group.colormap.color_by && getColormap(group.colormap)?.markers ? '' : 'helper-text'">Null values</v-label></td>
                                                <td>
                                                    <div
                                                        class="d-flex"
                                                        style="align-items: center;"
                                                    >
                                                        <v-btn-toggle
                                                            :model-value="group.colormap.null_color === 'transparent' ? 'transparent' : '#000000'"
                                                            density="compact"
                                                            variant="outlined"
                                                            divided
                                                            mandatory
                                                            :disabled="!group.visible || !group.colormap.color_by || !getColormap(group.colormap)?.markers"
                                                            @update:model-value="(value: string) => {if (group.colormap) group.colormap.null_color = value}"
                                                        >
                                                            <v-btn :value="'transparent'">Transparent</v-btn>
                                                            <v-btn :value="'#000000'">Single Color</v-btn>
                                                        </v-btn-toggle>
                                                        <v-menu
                                                            v-if="group.colormap.null_color !== 'transparent'"
                                                            :close-on-content-click="false"
                                                            open-on-hover
                                                            :disabled="!group.visible"
                                                            location="end"
                                                        >
                                                            <template v-slot:activator="{ props }">
                                                                <div
                                                                    v-bind="props"
                                                                    class="color-square"
                                                                    :style="{backgroundColor: group.colormap.null_color}"
                                                                ></div>
                                                            </template>
                                                            <v-card>
                                                                <v-color-picker
                                                                    v-model:model-value="group.colormap.null_color"
                                                                    mode="rgb"
                                                                />
                                                            </v-card>
                                                        </v-menu>
                                                    </div>
                                                </td>
                                            </tr>
                                        </template>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                    </v-window-item>
                    <v-window-item value="size" class="pa-2">
                        <div v-if="showRasterOptions">
                            <v-label class="secondary-text px-3">Raster Options</v-label>
                            <v-divider class="mt-1 mb-2"/>
                            <v-label class="secondary-text px-3">Size options do not apply to raster data.</v-label>
                        </div>
                        <div v-if="showVectorOptions">
                            <v-label class="secondary-text px-3">Vector Options</v-label>
                            <v-divider class="mt-1 mb-2"/>
                            <table class="aligned-controls">
                                <tbody>
                                    <tr>
                                        <td colspan="2">
                                            <v-checkbox
                                                v-if="availableGroups.length > 1"
                                                label="Different size per feature type"
                                                :model-value="Array.from(currentStyleSpec.sizes.keys()).length > 1"
                                                density="compact"
                                                class="primary-control"
                                                hide-details
                                                @update:model-value="setSizeGroups"
                                            />
                                        </td>
                                    </tr>
                                    <tr v-if="currentGroups['size'] !== 'all'">
                                        <td><v-label>Feature Type</v-label></td>
                                        <td>
                                            <v-select
                                                v-model="currentGroups['size']"
                                                :items="availableGroups"
                                                density="compact"
                                                variant="outlined"
                                                hide-details
                                            ></v-select>
                                        </td>
                                    </tr>
                                    <tr v-if="currentGroups['size'] !== 'all'">
                                        <td colspan="2">
                                            <v-label class="secondary-text py-2">Selected Feature Type Options [{{ currentGroups['size'] }}]</v-label>
                                        </td>
                                    </tr>
                                    <template v-for="group in currentStyleSpec.sizes.filter((c) => c.name === currentGroups['size'])">
                                        <tr>
                                            <td><v-label>Size Choice</v-label></td>
                                            <td>
                                                <v-btn-toggle
                                                :model-value="group.single_size !== undefined ? 'single_size' : 'range'"
                                                density="compact"
                                                variant="outlined"
                                                divided
                                                mandatory
                                                @update:model-value="(value: string) => setGroupSizeMode(group.name, value)"
                                            >
                                                <v-btn :value="'single_size'">Single Size</v-btn>
                                                <v-btn :value="'range'">Range of Sizes</v-btn>
                                            </v-btn-toggle>
                                            </td>
                                        </tr>
                                        <tr v-if="group.single_size !== undefined">
                                            <td>
                                                <v-label>Size</v-label>
                                                <v-icon
                                                    icon="mdi-information-outline"
                                                    color="primary"
                                                    size="small"
                                                    class="ml-2"
                                                    v-tooltip="group.name === 'all' ? 'Range: 1 to 10' : group.name === 'lines' ? 'Line thickness' : 'Point radius'"
                                                />
                                            </td>
                                            <td>
                                                <SliderNumericInput
                                                    :model="group.single_size"
                                                    @update="(v: number) => group.single_size = v"
                                                />
                                            </td>
                                        </tr>
                                        <tr v-if="group.size_range">
                                            <td :class="vectorProperties ? '' : 'helper-text'"><v-label>Size by Property</v-label></td>
                                            <td>
                                                <v-select
                                                    v-model="group.size_range.size_by"
                                                    :items="vectorProperties"
                                                    item-title="name"
                                                    item-value="name"
                                                    density="compact"
                                                    variant="outlined"
                                                    :disabled="!group.size_range || !vectorProperties"
                                                    placeholder="Select property"
                                                    hide-details
                                                >
                                                    <template v-slot:item="{ props, internalItem }">
                                                        <v-list-item v-bind="props" :disabled="!(internalItem.raw as Record<string, any>).range">
                                                            <template v-slot:append>
                                                                <v-chip size="small" v-if="(internalItem.raw as Record<string, any>).sample_label">{{ (internalItem.raw as Record<string, any>).sample_label }}</v-chip>
                                                            </template>
                                                        </v-list-item>
                                                    </template>
                                                </v-select>
                                            </td>
                                        </tr>
                                        <tr v-if="group.size_range">
                                            <td :class="group.size_range.size_by ? '' : 'helper-text'">
                                                <v-label>Size Range</v-label>
                                                <v-icon
                                                    v-if="group.name !== 'all'"
                                                    icon="mdi-information-outline"
                                                    color="primary"
                                                    size="small"
                                                    class="ml-2"
                                                    v-tooltip="group.name === 'lines' ? 'Line thickness' : 'Point radius'"
                                                />
                                            </td>
                                            <td>
                                                <SliderNumericInput
                                                    :rangeModel="[group.size_range.minimum, group.size_range.maximum]"
                                                    :disabled="!group.size_range.size_by"
                                                    @update="(v: [number, number]) => {if (group.size_range) {group.size_range.minimum = v[0]; group.size_range.maximum = v[1];}}"
                                                />
                                            </td>
                                        </tr>
                                        <tr v-if="group.size_range">
                                            <td :class="group.size_range.size_by ? '' : 'helper-text'"><v-label>Null Values</v-label></td>
                                            <td>
                                                <v-btn-toggle
                                                    :model-value="group.size_range.null_size?.transparency ? 'transparent' : 1"
                                                    density="compact"
                                                    variant="outlined"
                                                    divided
                                                    mandatory
                                                    :disabled="!group.size_range.size_by"
                                                    @update:model-value="(value: string | number) => {if (group.size_range) {
                                                        if (value === 'transparent') {group.size_range.null_size = {transparency: true, size: 0}}
                                                        else {group.size_range.null_size = {transparency: false, size: value as number}}
                                                    }}"
                                                >
                                                    <v-btn :value="'transparent'">Transparent</v-btn>
                                                    <v-btn :value="1">Size</v-btn>
                                                </v-btn-toggle>
                                                <SliderNumericInput
                                                    v-if="group.size_range.null_size && !group.size_range.null_size.transparency"
                                                    :model="group.size_range.null_size.size"
                                                    @update="(v: number) => {if (group.size_range?.null_size) group.size_range.null_size.size = v}"
                                                />
                                            </td>
                                        </tr>
                                        <tr>
                                            <td>
                                                <v-label>
                                                    Zoom Scaling
                                                    <v-icon
                                                        icon="mdi-information-outline"
                                                        color="primary"
                                                        size="small"
                                                        class="ml-2"
                                                        v-tooltip="'Size of features will change according to the current map zoom level, multiplied by a factor of the size value'"
                                                    />
                                                </v-label>
                                            </td>
                                            <td>
                                                <v-checkbox
                                                    v-model="group.zoom_scaling"
                                                    class="primary-control"
                                                    density="compact"
                                                    hide-details
                                                />
                                            </td>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                    </v-window-item>
                    <v-window-item value="filters" class="pa-2">
                        <div v-if="showRasterOptions">
                            <v-label class="secondary-text px-3">Raster Options</v-label>
                            <v-divider class="mt-1 mb-2"/>
                            <v-label class="secondary-text px-3">Filter options do not apply to raster data.</v-label>
                        </div>
                        <div v-if="showVectorOptions">
                            <v-card-subtitle>Vector Options</v-card-subtitle>
                            <v-divider class="mt-1 mb-2"/>
                            <div class="d-flex" style="justify-content: space-between; align-items: center;">
                                <v-card-subtitle>
                                    Filters ({{ currentStyleSpec.filters.length }})
                                </v-card-subtitle>
                                <v-btn color="primary" @click="addFilter" flat>
                                    <v-icon icon="mdi-plus"/>
                                    Add New Filter
                                </v-btn>
                            </div>
                            <v-card
                                v-for="filter in currentStyleSpec.filters"
                                :class="highlightFilterId === filter.id ? 'filter-card highlight' : 'filter-card'"
                                :key="filter.id"
                            >
                                <div class="d-flex" style="justify-content: space-between; align-items: center;">
                                    <v-select
                                        v-if="focusedFilterId === filter.id"
                                        v-model="filter.filter_by"
                                        :items="vectorProperties"
                                        :disabled="!filter.apply"
                                        placeholder="Select Property"
                                        item-title="name"
                                        item-value="name"
                                        density="compact"
                                        variant="outlined"
                                        hide-details
                                        @update:model-value="(v) => updateFilterBy(filter.id, v)"
                                    >
                                        <template v-slot:item="{ props, internalItem }">
                                            <v-list-item v-bind="props">
                                                <template v-slot:append>
                                                    <v-chip size="small" v-if="(internalItem.raw as Record<string, any>).sample_label">{{ (internalItem.raw as Record<string, any>).sample_label }}</v-chip>
                                                </template>
                                            </v-list-item>
                                        </template>
                                    </v-select>
                                    <span :class="filter.apply ? '' : 'helper-text'" style="white-space: wrap;" v-else>
                                        {{ filter.filter_by }}
                                        <span class="font-weight-bold">{{ filter.include ? ' [is] ' : ' [is not] ' }}</span>
                                        {{ filter.list }}
                                        {{ filter.range ? filter.range[0] + ' - ' + filter.range[1] : '' }}
                                    </span>
                                    <div>
                                        <v-icon v-if="focusedFilterId !== filter.id" @click="focusFilter(filter.id)" class="ml-2">mdi-pencil-outline</v-icon>
                                        <v-icon @click="filter.apply = !filter.apply" class="ml-2">
                                            {{ filter.apply ? 'mdi-eye' : 'mdi-eye-off' }}
                                        </v-icon>
                                        <v-icon @click="removeFilter(filter.id)" class="ml-2">mdi-delete-outline</v-icon>
                                    </div>
                                </div>
                                <table class="aligned-controls mt-2" v-if="focusedFilterId === filter.id">
                                    <tbody :class="filter.apply ? '' : 'helper-text'">
                                        <template v-if="filter.filter_by && vectorProperties" v-for="property in [vectorProperties.find((f: any) => f.name === filter.filter_by)]">
                                            <tr v-if="property?.range">
                                                <td>Value type</td>
                                                <td>
                                                    <v-btn-toggle
                                                        :model-value="filter.range ? 'range' : 'single'"
                                                        :disabled="!filter.apply"
                                                        density="compact"
                                                        variant="outlined"
                                                        divided
                                                        mandatory
                                                        @update:model-value="(value: string) => {
                                                            if (!property.range) return
                                                            if (value === 'range') {filter.range = property.range; filter.list = undefined}
                                                            else {filter.range = undefined; filter.list = [property.range[0]]}
                                                        }"
                                                    >
                                                        <v-btn :value="'single'">Single</v-btn>
                                                        <v-btn :value="'range'">Range</v-btn>
                                                    </v-btn-toggle>
                                                </td>
                                            </tr>
                                            <tr v-if="property">
                                                <td>Values</td>
                                                <td>
                                                    <template v-if="property.range">
                                                        <SliderNumericInput
                                                            v-if="filter.range"
                                                            :disabled="!filter.apply"
                                                            :rangeModel="filter.range"
                                                            :min="property.range[0]"
                                                            :max="property.range[1]"
                                                            @update="(v: [number, number]) => filter.range = v"
                                                        />
                                                        <SliderNumericInput
                                                            v-else-if="filter.list"
                                                            :disabled="!filter.apply"
                                                            :model="filter.list[0]"
                                                            :min="property.range[0]"
                                                            :max="property.range[1]"
                                                            @update="(v: number) => filter.list = [v]"
                                                        />
                                                    </template>
                                                    <v-select
                                                        v-else
                                                        v-model="filter.list"
                                                        :items="property.value_set"
                                                        :disabled="!filter.apply"
                                                        placeholder="Select values"
                                                        density="compact"
                                                        variant="outlined"
                                                        multiple
                                                        chips
                                                        closable-chips
                                                        hide-details
                                                    />
                                                </td>
                                            </tr>
                                        </template>
                                        <tr>
                                            <td>Filter Mode</td>
                                            <td>
                                                <v-btn-toggle
                                                    :model-value="filter.include ? 'include' : 'exclude'"
                                                    :disabled="!filter.apply"
                                                    density="compact"
                                                    variant="outlined"
                                                    divided
                                                    mandatory
                                                    @update:model-value="(value: string) => {filter.include = value === 'include'}"
                                                >
                                                    <v-btn :value="'include'">Include values</v-btn>
                                                    <v-btn :value="'exclude'">Exclude values</v-btn>
                                                </v-btn-toggle>
                                            </td>
                                        </tr>
                                    </tbody>
                                </table>
                            </v-card>
                        </div>
                    </v-window-item>
                </v-window>

            </v-card-text>

            <v-card-actions class="my-1" style="float: right;">
                <v-btn class="secondary-button" @click="cancel" v-tooltip="'Warning: unsaved changes will be discarded'">
                    <v-icon color="primary" class="mr-1">mdi-close-circle</v-icon>
                    Cancel
                </v-btn>
                <v-btn
                    class="primary-button"
                    :disabled="!currentLayerStyle.id || !unsavedChanges"
                    @click="save"
                >
                    <v-icon
                        class="mr-1"
                        color="button-text"
                        :icon="unsavedChanges ? 'mdi-content-save' : 'mdi-check'"
                    />
                    {{ unsavedChanges ? 'Save' : 'Saved' }}
                </v-btn>
                <v-btn class="primary-button" @click="newNameMode = 'create'">
                    <v-icon color="button-text" class="mr-1">mdi-plus-circle</v-icon>
                    Save As New
                </v-btn>
            </v-card-actions>

            <v-dialog
                contained
                :model-value="!!newNameMode"
                @update:model-value="(v) => {if (!v) {newNameMode = undefined; newName = undefined;}}"
            >
                <v-card color="background">
                    <v-card-subtitle class="pa-2" style="background-color: rgb(var(--v-theme-surface));">
                        {{ newNameMode === 'create' ? 'New' : 'Rename' }} Layer Style
                        <span v-if="newNameMode === 'update'" class="secondary-text">({{ currentLayerStyle.name }})</span>

                        <v-icon
                            icon="mdi-close"
                            style="float:right"
                            @click="newNameMode = undefined; newName = undefined"
                        />
                    </v-card-subtitle>

                    <v-card-text>
                        <v-text-field
                            label="Name"
                            v-model="newName"
                            autofocus
                            :placeholder="newNameMode === 'update' ? currentLayerStyle.name : ''"
                            :rules="[() => !availableStyles?.map((s) => s.name).includes(newName) || `Style ''${newName}'' already exists.`]"
                            @keydown.enter="() => {if (newName) {
                                if (newNameMode === 'update') {save()} else {saveAsNew()}
                            }}"
                            @keydown.escape="newNameMode = undefined; newName = undefined"
                        />
                    </v-card-text>

                    <v-card-actions style="float: right;">
                        <v-btn class="secondary-button" @click="newNameMode = undefined; newName = undefined">
                            <v-icon color="primary" class="mr-1">mdi-close-circle</v-icon>
                            Cancel
                        </v-btn>
                        <v-btn
                            class="primary-button"
                            :disabled="availableStyles?.map((s) => s.name).includes(newName)"
                            @click="() => {if (newNameMode === 'update') {save()} else {saveAsNew()}}"
                        >
                            <v-icon color="button-text" class="mr-1">
                                {{ newNameMode === 'update' ? 'mdi-content-save' : 'mdi-plus-circle' }}
                            </v-icon>
                            {{ newNameMode === 'update' ? 'Rename Style' : 'Create Style' }}
                        </v-btn>
                    </v-card-actions>
                </v-card>
            </v-dialog>

            <v-dialog v-model="showDeleteConfirmation" contained>
                <v-card color="background">
                    <v-card-subtitle class="pa-2" style="background-color: rgb(var(--v-theme-surface))">
                        Delete Layer Style
                        <span class="secondary-text">({{ currentLayerStyle.name }})</span>

                        <v-icon
                            icon="mdi-close"
                            style="float:right"
                            @click="showDeleteConfirmation = false"
                        />
                    </v-card-subtitle>

                    <v-card-text>
                        Are you sure you want to delete "{{ currentLayerStyle.name }}"?
                        <div class="pa-3 d-flex" style="align-items: center; column-gap: 10px">
                            <v-icon icon="mdi-alert" color="warning" />
                            <span class="secondary-text">
                                This action cannot be undone. Any layer using this style will revert to default settings.
                            </span>
                        </div>
                    </v-card-text>

                    <v-card-actions>
                        <v-btn class="secondary-button" @click="showDeleteConfirmation = false">
                            <v-icon color="primary" class="mr-1">mdi-close-circle</v-icon>
                            Cancel
                        </v-btn>
                        <v-btn color="error" variant="tonal" @click="deleteStyle">
                            <v-icon color="error" class="mr-1">mdi-delete</v-icon>
                            Delete
                        </v-btn>
                    </v-card-actions>
                </v-card>
            </v-dialog>

            <v-dialog :model-value="!!delColormap" contained peristent>
                <v-card v-if="delColormap" color="background">
                    <v-card-subtitle class="pa-2" style="background-color: rgb(var(--v-theme-surface))">
                        Delete Colormap
                        <span class="secondary-text">({{ delColormap.name }})</span>

                        <v-icon
                            icon="mdi-close"
                            style="float:right"
                            @click="delColormap = undefined"
                        />
                    </v-card-subtitle>

                    <v-card-text>
                        Are you sure you want to delete colormap "{{ delColormap.name }}"?
                        <div class="pa-3 d-flex" style="align-items: center; column-gap: 10px">
                            <v-icon icon="mdi-alert" color="warning" />
                            <span class="secondary-text">
                                This action cannot be undone. Any style using this colormap will revert to a default colormap.
                            </span>
                        </div>
                    </v-card-text>

                    <v-card-actions>
                        <v-btn class="secondary-button" @click="delColormap = undefined">
                            <v-icon color="primary" class="mr-1">mdi-close-circle</v-icon>
                            Cancel
                        </v-btn>
                        <v-btn color="error" variant="tonal" @click="confirmDeleteColormap">
                            <v-icon color="error" class="mr-1">mdi-delete</v-icon>
                            Delete
                        </v-btn>
                    </v-card-actions>
                </v-card>
            </v-dialog>

            <v-dialog v-model="showColormapEditor" contained>
                <ColormapEditor
                    :edit="editColormap"
                    @close="showColormapEditor = false; editColormapGroupName = undefined"
                    @submit="(cmap) => setGroupColormap(editColormapGroupName, cmap)"
                />
            </v-dialog>
        </v-card>
    </v-menu>
</template>

<style>
.layer-style-card  .v-label {
    font-size: 14px;
}
.aligned-controls {
    padding: 0px;
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

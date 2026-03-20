<script setup lang="ts">
import { createDataset, createFileItem, spawnDatasetConversion, uploadFile } from '@/api/rest';
import { Dataset } from '@/types';
import { computed, ref, watch } from 'vue';

import { VFileUpload, VFileUploadItem } from 'vuetify/labs/VFileUpload'

import JsonEditorVue from 'json-editor-vue'
import 'vanilla-jsoneditor/themes/jse-theme-dark.css'
import { Mode } from 'vanilla-jsoneditor'

import { useAppStore, useProjectStore } from '@/store';
const appStore = useAppStore();
const projectStore = useProjectStore()

interface LayerSpec {
    id: number;
    name: string | undefined;
    files: File[];
    frame_method: 'single' | 'multi';
    frame_property: string | undefined
}

const props = defineProps<{
    allDatasets: Dataset[];
    projectPermission: any;
}>();
const emit = defineEmits(['addToCurrentProject', 'uploaded']);


const open = ref<boolean>(false)
const name = ref<string>()
const description = ref<string>()
const category = ref<string>()
const tags = ref<string[]>([])
const metadata = ref<object>({})
const layers = ref<LayerSpec[]>([])
const maxLayerId = ref<number>(0)
const focusedLayerId = ref<number>(0)
const addToCurrentProject = ref<boolean>(false)
const submitting = ref<boolean>(false)
const mandatoryRule = [
    (v: any) => (v ? true : "Input required.")
];
const acceptTypes = '.json,.geojson,.tif,.tiff,.zip'
const maxFileSize = 2000000000
const fileUploadRules = [(fileset: File[]) => {
  if (fileset.some((f) => f.size > maxFileSize)) {
    return 'File Upload cannot be greater than 2 GB.'
  }
}]

const similarExisting = computed(() => {
    return props.allDatasets.filter((d) => {
        if (name.value && name.value.length > 2) return d.name?.toLowerCase().includes(name.value.toLowerCase())
        return false
    })
})
const categories = computed(() => {
    return [...new Set(props.allDatasets?.map((d) => d.category))]
})
const valid = computed(() => {
    return (
        name.value && description.value && category.value &&
        layers.value.length > 0 && layers.value.every((l) => {
            return l.name && l.files.length &&
            fileUploadRules.every((rule) => rule(l.files) === undefined) && (
                l.frame_method === 'single' || l.frame_property
            )
        })
    )
})
const canEditProject = computed(() => {
    return ['owner', 'collaborator'].includes(props.projectPermission)
})

function init() {
    addLayer()
    if (canEditProject) {
        addToCurrentProject.value = true
    }
}

function cancel() {
    open.value = false
    name.value = undefined
    description.value = undefined
    category.value = undefined
    tags.value = []
    metadata.value = {}
    layers.value = []
    maxLayerId.value = 0
    focusedLayerId.value = 0
    addToCurrentProject.value = false
    submitting.value = false
}

function addLayer() {
    maxLayerId.value += 1
    const id = maxLayerId.value
    layers.value.push({
        id,
        name: undefined,
        files: [],
        frame_method: 'single',
        frame_property: undefined,
    })
    focusedLayerId.value = id
}

function removeLayer(layer_id: number) {
    layers.value = layers.value.filter((l) => l.id !== layer_id)
    if (focusedLayerId.value === layer_id) {
        focusedLayerId.value = 0
    }
}

function isRasterFile(file: File) {
    return ['image/tiff'].includes(file.type)
}

function isVectorFile(file: File) {
    return ['application/json', 'application/geo+json'].includes(file.type)
}

function submit() {
    submitting.value = true
    createDataset({
        name: name.value,
        description: description.value,
        category: category.value,
        tags: tags.value,
        metadata: metadata.value,
    }).then(async (dataset) => {
        if (addToCurrentProject.value) {
            emit('addToCurrentProject', dataset)
        }
        const layerOptions = await Promise.all(
            layers.value.map(async (l) => {
                let fileValues = await Promise.all(
                    l.files.map(async (f) => await uploadFile(f))
                )
                let fileItems = await Promise.all(
                    l.files.map(async (f, i) => await createFileItem({
                        name: f.name,
                        file: fileValues[i],
                        file_type: f.type.substring(f.type.lastIndexOf('/') + 1).replaceAll('+', ''),
                        dataset: dataset.id,
                    }))
                )
                const layerInfo: any = {
                    name: l.name,
                    source_files: fileItems.map((f) => f.name)
                }
                if (l.frame_property) {
                    layerInfo.frame_property = l.frame_property
                }
                return layerInfo
            })
        )
        spawnDatasetConversion(dataset.id, { layer_options: layerOptions }).then((conversionTask) => {
            emit('uploaded', { dataset, conversionTask })
            cancel()
        })
    })
}

watch(open, () => {
    if (!open) cancel()
    else init()
})
</script>

<template>
    <v-btn color="primary" @click="open = true">
        <v-icon icon="mdi-upload" class="mr-2" />
        Upload New Dataset

        <v-dialog v-model="open" persistent width="700">
            <v-card color="background">
                <div class="px-4 py-2" style="background-color: rgb(var(--v-theme-surface)); height: 40px">
                    Upload Dataset

                    <v-icon icon="mdi-close" style="position: absolute; top: 10px; right: 5px;"
                        v-tooltip="'Warning: unsaved changes will be discarded'" @mousedown="cancel" />
                </div>
                <div class="pa-5 d-flex dataset-upload-form-content" style="flex-direction: column; row-gap: 10px">
                    <v-text-field autofocus label="Dataset Name" v-model="name" :rules="mandatoryRule"
                        hide-details="auto" />
                    <div v-if="similarExisting.length" class="bg-surface-light pa-2">
                        <span class="secondary-text">Similar Existing Datasets:</span>
                        <div v-for="dataset in similarExisting" style="font-size: 0.8rem; margin-left: 10px">
                            {{ dataset.name }}
                        </div>
                    </div>
                    <v-text-field label="Description" v-model="description" :rules="mandatoryRule"
                        hide-details="auto" />
                    <v-combobox label="Category" v-model="category" :items="categories" :rules="mandatoryRule"
                        hide-details="auto">
                        <template v-slot:append-inner>
                            <v-icon v-if="category && !categories.includes(category)" icon="mdi-information-outline"
                                class="ml-2" color="primary" v-tooltip="'You are creating a new category'" />
                        </template>
                    </v-combobox>
                    <v-combobox label="Tags" v-model="tags" :items="projectStore.availableDatasetTags"
                        hide-details="auto" multiple chips closable-chips>
                        <template v-slot:append-inner>
                            <v-icon
                                v-if="tags.length && tags.some((t) => !projectStore.availableDatasetTags.includes(t))"
                                icon="mdi-information-outline" class="ml-2" color="primary"
                                v-tooltip="'You are creating a new tag'" />
                        </template>
                    </v-combobox>

                    <v-expansion-panels>
                        <v-expansion-panel>
                            <v-expansion-panel-title class="px-4">Metadata</v-expansion-panel-title>
                            <v-expansion-panel-text>
                                <json-editor-vue v-model="metadata" :mode="Mode.text" :stringified="false"
                                    :main-menu-bar="false" :indentation="4"
                                    :class="appStore.theme === 'dark' ? 'jse-theme-dark' : ''" />
                            </v-expansion-panel-text>
                        </v-expansion-panel>
                    </v-expansion-panels>

                    <div class="layers-configuration">
                        <div class="px-4 py-2" style="background-color: rgb(var(--v-theme-surface)); height: 40px">
                            Layers Configuration
                        </div>
                        <div class="pa-2">
                            <v-card v-for="layer, index in layers" :key="layer.id" class="layer-card">
                                <div v-if="focusedLayerId === layer.id">
                                    <v-text-field label="Layer Name" v-model="layer.name" :rules="mandatoryRule"
                                        hide-details="auto" />
                                    <v-icon icon="mdi-information-outline" color="primary" class="upload-info-icon"
                                        v-tooltip="'Upload multiple files to create a sequence of frames, or upload a single file to optionally split into frames.'" />
                                    <v-file-upload v-model="layer.files" density="compact" class="mt-2" multiple
                                        clearable :accept="acceptTypes" show-size :rules="fileUploadRules"
                                        style="background-color: rgb(var(--v-theme-secondary)); padding: 10px"
                                        @update:model-value="() => { layer.frame_method = 'single'; layer.frame_property = undefined }">
                                        <template v-slot:icon>
                                            <v-icon size="xs" icon="mdi-upload" color="primary" />
                                        </template>
                                        <template v-slot:title>
                                            <div style="font-weight: normal; font-size: medium;">
                                                Drag & drop file(s) or
                                                <span style="text-decoration: underline;"
                                                    class="text-primary">Browse</span>
                                            </div>
                                        </template>
                                        <template v-slot:item="{ props: itemProps }">
                                            <v-file-upload-item v-bind="itemProps" lines="one" nav>
                                                <template v-slot:prepend>
                                                    <v-icon icon="mdi-file-outline" />
                                                </template>
                                                <template v-slot:title="{ title }">
                                                    <div class="text-primary">{{ title }}</div>
                                                </template>
                                                <template v-slot:clear="{ props: clearProps }">
                                                    <v-icon color="error" icon="mdi-close-circle" v-bind="clearProps" />
                                                </template>
                                            </v-file-upload-item>
                                        </template>
                                    </v-file-upload>
                                    <div v-if="layer.files.length > 1 || layer.files.some((f) => f.type === 'application/zip')"
                                        class="secondary-text" style="text-align: center; font-size: 0.8rem;">
                                        Each file will be treated as a frame in the layer's sequence.
                                    </div>
                                    <div v-else-if="layer.files.length === 1">
                                        <v-btn-toggle v-model="layer.frame_method" variant="outlined" density="compact"
                                            divided mandatory>
                                            <v-btn value="single">Add as single frame</v-btn>
                                            <v-btn value="multi">Add as multi-frame</v-btn>
                                        </v-btn-toggle>
                                        <div v-if="layer.frame_method === 'multi'" class="mt-2">
                                            <v-btn-toggle v-if="isRasterFile(layer.files[0])"
                                                v-model="layer.frame_property" variant="outlined" density="compact"
                                                divided mandatory>
                                                <v-btn value="frame">Split by raster frame</v-btn>
                                                <v-btn value="band">Split by raster band</v-btn>
                                            </v-btn-toggle>
                                            <v-text-field v-else-if="isVectorFile(layer.files[0])"
                                                v-model="layer.frame_property" label="Frame Property" density="compact"
                                                :rules="mandatoryRule" hide-details="auto">
                                                <template v-slot:append>
                                                    <v-icon icon="mdi-information-outline"
                                                        v-tooltip="'Enter the name of an ordered feature property that corresponds to frame'"
                                                        color="primary" />
                                                </template>
                                            </v-text-field>
                                        </div>
                                    </div>
                                </div>
                                <div v-else style="width: 100%; display: flex; justify-content: space-between;">
                                    {{ layer.name || ('Layer ' + (index + 1)) }}

                                    <div>
                                        <v-icon @click="focusedLayerId = layer.id"
                                            class="ml-2">mdi-pencil-outline</v-icon>
                                        <v-icon @click="removeLayer(layer.id)" class="ml-2">mdi-delete-outline</v-icon>
                                    </div>
                                </div>
                            </v-card>
                            <div style="text-align: center;" class="pt-2">
                                <v-btn color="background" class="text-primary" flat @click="addLayer">
                                    <v-icon icon="mdi-plus" color="primary" />
                                    Add Layer
                                </v-btn>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="d-flex px-3" style="justify-content: right;">
                    <v-checkbox v-if="canEditProject" v-model="addToCurrentProject"
                        label="Add dataset to current project" density="compact" color="primary" hide-details />
                </div>
                <v-card-actions style="float: right;">
                    <v-btn class="secondary-button" @click="cancel">
                        <v-icon color="primary" class="mr-1">mdi-close-circle</v-icon>
                        Cancel
                    </v-btn>
                    <v-btn class="primary-button" :disabled="!valid || submitting" @click="submit">
                        <v-progress-circular v-if="submitting" indeterminate size="20" class="mr-1" />
                        <v-icon v-else color="button-text" class="mr-1" icon="mdi-upload" />
                        Upload
                    </v-btn>
                </v-card-actions>
            </v-card>
        </v-dialog>
    </v-btn>
</template>

<style>
.dataset-upload-form-content {
    max-height: 70vh !important;
    overflow-y: auto;
    overflow-x: hidden;
}

.layers-configuration {
    border: 1px solid rgb(var(--v-theme-primary-text))
}

.layer-card {
    padding: 8px !important;
    margin-top: 8px;
    background-color: rgb(var(--v-theme-background)) !important;
    box-shadow: none !important;
    border-bottom: 1px solid rgb(var(--v-theme-surface))
}

.upload-info-icon {
    position: absolute;
    right: 15px;
    padding-top: 25px;
    z-index: 1;
}

.v-file-upload-items .v-list-item {
    border: none !important
}

.v-file-upload-items .v-list-item-title {
    font-size: 1rem !important;
}

.v-checkbox-btn .text-primary .v-icon {
    color: rgb(var(--v-theme-primary)) !important
}
</style>

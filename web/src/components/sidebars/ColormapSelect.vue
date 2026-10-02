<script setup lang="ts">
import { ref } from "vue";
import type { Colormap } from "@/types";
import ColormapPreview from "./ColormapPreview.vue";
import ColormapEditor from "./ColormapEditor.vue";
import { deleteColormap, getLayerStyles } from "@/api/rest.ts";

import { useStyleStore, useProjectStore, useLayerStore } from "@/store";
const styleStore = useStyleStore();
const projectStore = useProjectStore();
const layerStore = useLayerStore();

const emit = defineEmits(["update"]);
const props = defineProps<{
  modelValue: Colormap | undefined;
  disabled: boolean;
  discrete: boolean;
  nColors: number;
  editMode: boolean;
}>();

const showColormapEditor = ref(false);
const editColormap = ref<Colormap | undefined>();
const delColormap = ref<Colormap | undefined>();

function openColormapEditor(colormap: Colormap | undefined) {
  if (!props.editMode) return;
  showColormapEditor.value = true;
  editColormap.value = colormap;
}

function confirmDeleteColormap() {
  if (!props.editMode) return;
  if (delColormap.value?.id) {
    deleteColormap(delColormap.value.id).then(() => {
      delColormap.value = undefined;
      styleStore.colormaps = styleStore.colormaps.filter(
        (c) => c.id !== delColormap.value?.id,
      );
      // update other styles in case colormap changed to default
      layerStore.selectedLayers.forEach((layer) => {
        const key = styleStore.layerStyleKey(layer);
        getLayerStyles(layer.id, projectStore.currentProject?.id).then(
          (styles) => {
            const updated = styles.find(
              (s) => s.id === styleStore.selectedLayerStyles[key].id,
            );
            if (updated) {
              styleStore.selectedLayerStyles[key] = updated;
              styleStore.updateLayerStyles(layer);
            }
          },
        );
      });
    });
  }
}
</script>

<template>
  <v-select
    :model-value="props.modelValue"
    :items="styleStore.colormaps"
    item-title="name"
    density="compact"
    variant="outlined"
    hide-details
    return-object
    :disabled="props.disabled"
    @update:model-value="(v: Colormap) => emit('update', v)"
  >
    <template #item="{ props: itemProps, item }">
      <v-list-item v-bind="itemProps">
        <template #append>
          <v-icon
            v-if="
              item.project == projectStore.currentProject?.id && props.editMode
            "
            v-tooltip="'Edit Colormap'"
            icon="mdi-pencil"
            class="ml-2"
            @click="openColormapEditor(item)"
          />
          <v-icon
            v-if="item.project == projectStore.currentProject?.id && editMode"
            v-tooltip="'Delete Colormap'"
            icon="mdi-delete"
            class="ml-2"
            @click="delColormap = item"
          />
          <div style="width: 300px" class="ml-2">
            <colormap-preview
              :colormap="item"
              :discrete="props.discrete"
              :n-colors="props.nColors"
            />
          </div>
        </template>
      </v-list-item>
    </template>
    <template #selection="{ item }">
      <span v-if="item?.markers" class="pr-15">{{ item.name }}</span>
      <div v-if="item?.markers" style="width: 300px" class="ml-2">
        <colormap-preview
          :colormap="item"
          :discrete="props.discrete"
          :n-colors="props.nColors"
        />
      </div>
      <span v-else class="secondary-text">Select Colormap</span>
    </template>
    <template #prepend-item>
      <v-list-item v-if="editMode" @click="openColormapEditor(undefined)">
        <div
          style="
            color: rgb(var(--v-theme-primary));
            align-items: center;
            display: flex;
          "
        >
          <v-icon color="primary">mdi-plus</v-icon>
          Create Custom Colormap
        </div>
      </v-list-item>
    </template>
  </v-select>
  <v-dialog v-model="showColormapEditor" contained>
    <ColormapEditor
      :edit="editColormap"
      @close="showColormapEditor = false"
      @submit="(v: Colormap) => emit('update', v)"
    />
  </v-dialog>
  <v-dialog :model-value="!!delColormap" contained peristent>
    <v-card v-if="delColormap" color="background">
      <v-card-subtitle
        class="pa-2"
        style="background-color: rgb(var(--v-theme-surface))"
      >
        Delete Colormap
        <span class="secondary-text">({{ delColormap.name }})</span>

        <v-icon
          icon="mdi-close"
          style="float: right"
          @click="delColormap = undefined"
        />
      </v-card-subtitle>

      <v-card-text>
        Are you sure you want to delete colormap "{{ delColormap.name }}"?
        <div class="pa-3 d-flex" style="align-items: center; column-gap: 10px">
          <v-icon icon="mdi-alert" color="warning" />
          <span class="secondary-text">
            This action cannot be undone. Any style using this colormap will
            revert to a default colormap.
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
</template>

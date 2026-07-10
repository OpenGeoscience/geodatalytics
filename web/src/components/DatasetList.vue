<script setup lang="ts">
import { onMounted, ref, computed, watch } from "vue";
import type { Dataset } from "@/types";

import { useProjectStore } from "@/store";
const projectStore = useProjectStore();

const props = defineProps<{
  datasets: Dataset[] | undefined;
}>();

const searchText = ref<string | undefined>();
const selectedTags = ref<string[]>();
const showFilter = ref();
const filteredDatasets = computed(() => {
  return props.datasets?.filter((dataset: any) => {
    const searchMatch =
      !searchText.value ||
      dataset.name.toLowerCase().includes(searchText.value.toLowerCase());
    const tagMatch =
      !selectedTags.value?.length ||
      dataset.tags.some((t: string) => selectedTags.value?.includes(t));
    return searchMatch && tagMatch;
  });
});
const datasetGroups = computed(() => {
  const groupByKey = "category";
  const groups: Record<string, Dataset[]> = {};
  filteredDatasets.value?.forEach((dataset: any) => {
    const groupName = dataset[groupByKey];
    if (!groups[groupName]) {
      groups[groupName] = [];
    }
    groups[groupName].push(dataset);
  });
  return groups;
});
const expandedGroups = ref();

function init() {
  projectStore.fetchAvailableDatasetTags();
  expandAllGroups();
}

function expandAllGroups() {
  if (filteredDatasets.value) {
    expandedGroups.value = Object.keys(datasetGroups.value);
  }
}

onMounted(init);
watch(filteredDatasets, expandAllGroups);
</script>

<template>
  <div class="panel-content-outer with-search">
    <v-text-field
      v-model="searchText"
      label="Search Datasets"
      variant="outlined"
      density="compact"
      class="mb-2 dataset-search"
      append-inner-icon="mdi-magnify"
      hide-details
    />
    <v-expansion-panels v-if="props.datasets?.length" v-model="showFilter" flat>
      <v-expansion-panel value="true" class="mb-2 bg-transparent">
        <v-expansion-panel-title class="tag-filter-title">
          Filter by Tag
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-combobox
            v-model="selectedTags"
            :items="projectStore.availableDatasetTags"
            density="compact"
            multiple
            chips
            closable-chips
            hide-details
          />
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
    <v-card
      :class="
        props.datasets?.length
          ? showFilter
            ? 'panel-content-inner with-tag-filter-open'
            : 'panel-content-inner with-tag-filter-closed'
          : 'panel-content-inner'
      "
    >
      <v-expansion-panels
        v-if="props.datasets?.length"
        v-model="expandedGroups"
        variant="accordion"
        class="dataset-list"
        style="height: fit-content"
        multiple
        flat
      >
        <v-expansion-panel
          v-for="[groupName, groupDatasets] in Object.entries(datasetGroups)"
          :key="groupName"
          :value="groupName"
          bg-color="background"
        >
          <v-expansion-panel-title style="font-weight: bold">
            <span class="capitalize secondary-text pl-3">{{ groupName }}</span>
          </v-expansion-panel-title>
          <v-expansion-panel-text class="ml-3">
            <slot name="list" :data="groupDatasets"></slot>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
      <v-progress-linear
        v-else-if="projectStore.loadingDatasets"
        indeterminate
      ></v-progress-linear>
      <v-card-text v-else class="help-text">No available Datasets.</v-card-text>
    </v-card>
  </div>
</template>

<style>
.dataset-list {
  height: 100%;
  width: calc(100% - 20px) !important;
  overflow-y: auto;
  overflow-x: hidden;
}
.dataset-list .v-expansion-panel-title {
  min-height: 0 !important;
  display: flex;
  justify-content: space-between;
  padding: 12px 0px !important;
}
.dataset-list .v-selection-control__input,
.dataset-list .v-selection-control__wrapper {
  height: inherit;
}
.dataset-list .v-list-item--density-default {
  min-height: 0;
}
.dataset-search {
  position: sticky;
  top: 0;
  z-index: 2;
}
.v-selection-control--density-default {
  --v-selection-control-size: 20px;
}
.capitalize {
  text-transform: capitalize !important;
}
.secondary-text {
  color: rgb(var(--v-theme-secondary-text)) !important;
}
.helper-text {
  color: rgb(var(--v-theme-helper-text)) !important;
}
.item-title {
  display: flex;
  justify-content: space-between;
  font-size: 0.875rem;
  margin-left: 24px;
  width: 100%;
}
.item-title + .v-expansion-panel-title__icon {
  position: absolute !important;
  left: 0 !important;
}
.tag-filter-title {
  padding: 0px 0px 4px 0px !important;
  min-height: 0px !important;
  font-size: inherit !important;
}

.panel-content-inner.with-tag-filter-open {
  height: calc(100% - 120px);
}

.panel-content-inner.with-tag-filter-closed {
  height: calc(100% - 80px);
}

.v-list-item__prepend .v-checkbox-btn {
  margin-right: 5px;
}
</style>

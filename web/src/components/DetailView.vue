<script setup lang="ts">
import { ref, computed, watch } from "vue";
import RecursiveTable from "./RecursiveTable.vue";
import { getChartFiles, getDatasetFiles, getFileDataObjects } from "@/api/rest";
import type { RasterData, VectorData } from "@/types";

interface Details {
  metadata?: Record<string, any>;
  type: string;
  id: number;
  name?: string;
  download?: {
    url: string;
    size: number;
    type: string;
  };
  description?: string;
  created?: string;
  modified?: string;
  prependIcon?: string;
  related?: Details[];
}

const props = defineProps<{
  details: Details;
}>();

const showModal = ref(false);
const transitionName = ref("slide-in");
const detailStack = ref<Details[]>([props.details]);
const stackPoppable = computed(() => detailStack.value.length > 1);
const currentDetails = computed(
  () => detailStack.value[detailStack.value.length - 1],
);
const hasMetadata = computed(
  () =>
    currentDetails.value.metadata &&
    Object.keys(currentDetails.value.metadata).length > 0,
);
const related = ref<Details[]>();
const basicInfo = computed(() => {
  return Object.fromEntries(
    Object.entries(currentDetails.value).filter(([key]) =>
      ["description", "created", "modified", "category", "id"].includes(key),
    ),
  );
});

async function getRelated(target: Details): Promise<Details[]> {
  let results: Details[] = [];
  if (target.related) {
    results = target.related;
  } else if (target.type === "dataset") {
    const files = await getDatasetFiles(target.id);
    const fileDetails: Details[] = files.map((file) => ({
      ...file,
      type: "file",
      download: {
        url: file.file,
        size: file.file_size,
        type: file.file_type,
      },
      prependIcon: "mdi-file",
    }));
    results = (
      await Promise.all(
        fileDetails.map(async (fDetail) => {
          return (await getRelated(fDetail)).map((r) => ({
            ...r,
            related: [fDetail],
          }));
        }),
      )
    ).flat();
  } else if (target.type === "chart") {
    const files = await getChartFiles(target.id);
    results = files.map((file) => ({
      ...file,
      type: "file",
      download: {
        url: file.file,
        size: file.file_size,
        type: file.file_type,
      },
      prependIcon: "mdi-file",
    }));
  } else if (target.type === "file") {
    const dataObjects = await getFileDataObjects(target.id);
    results = dataObjects
      .map((data) => {
        const raster = data as RasterData;
        const vector = data as VectorData;
        if (raster.cloud_optimized_geotiff) {
          return {
            ...data,
            type: "rasterdata",
            download: {
              url: raster.cloud_optimized_geotiff,
              size: raster.file_size,
              type: "cog",
            },
            prependIcon: "mdi-checkerboard",
          };
        } else if (vector.geojson_data) {
          return {
            ...data,
            type: "vectordata",
            download: {
              url: vector.geojson_data,
              size: vector.file_size,
              type: "geojson",
            },
            prependIcon: "mdi-vector-square",
          };
        }
      })
      .filter((item) => !!item);
  }
  return results;
}

function fetchRelated() {
  if (!showModal.value) {
    detailStack.value = [props.details];
    return;
  }
  if (currentDetails.value) {
    getRelated(currentDetails.value).then((results) => {
      // ensure no object in the detailStack appears in the related list
      results = results.filter((r) => {
        return !detailStack.value.find(
          (d) => d.id === r.id && d.type === r.type,
        );
      });
      related.value = results;
    });
  }
}

function getFileSizeString(size: number) {
  // https://stackoverflow.com/a/20732091
  const i = size == 0 ? 0 : Math.floor(Math.log(size) / Math.log(1024));
  return (
    +(size / Math.pow(1024, i)).toFixed(2) * 1 +
    " " +
    ["B", "kB", "MB", "GB", "TB"][i]
  );
}

function addToStack(relatedId: number) {
  transitionName.value = "slide-in";
  const child = related.value?.find((r) => r.id === relatedId);
  if (child) {
    detailStack.value = [...detailStack.value, child];
  }
}

function popStack() {
  // Don't ever pop the stack completely, always leave the first item
  if (!stackPoppable.value) {
    return;
  }

  transitionName.value = "slide-out";
  if (detailStack.value.length) {
    detailStack.value = [...detailStack.value.slice(0, -1)];
  }
}

watch([showModal, currentDetails], fetchRelated);
</script>

<template>
  <v-icon
    v-tooltip="'View Details'"
    icon="mdi-dots-vertical"
    size="small"
    class="mx-1"
    @click.stop="showModal = true"
  ></v-icon>

  <v-dialog v-model="showModal" class="details-dialog">
    <v-card>
      <Transition :name="transitionName" mode="out-in">
        <div :key="currentDetails.type + '_' + currentDetails.id">
          <v-card-title
            class="d-flex"
            style="max-width: 90%; margin: 4px 4em 0 0; align-items: center"
          >
            <v-icon
              v-if="stackPoppable"
              icon="mdi-arrow-left"
              @click="popStack"
            />
            <v-icon
              v-if="currentDetails.prependIcon"
              :icon="currentDetails.prependIcon"
              class="mr-3"
            />
            <span class="mr-5 secondary-text font-weight-thin">{{
              currentDetails.type.toUpperCase()
            }}</span>
            {{ currentDetails.name }}
          </v-card-title>

          <div v-if="basicInfo">
            <v-card-subtitle>Basic Information</v-card-subtitle>
            <v-card-text><RecursiveTable :data="basicInfo" /></v-card-text>
          </div>

          <div v-if="related?.length" style="min-width: 500px">
            <v-card-subtitle>Related Objects </v-card-subtitle>
            <v-list
              :items="related"
              item-value="id"
              @click:select="({ id }) => addToStack(id as number)"
            >
              <template #prepend="{ item }">
                <v-icon
                  v-if="item.prependIcon"
                  :icon="item.prependIcon"
                  class="mr-3"
                />
                <span class="secondary-text font-weight-thin">{{
                  item.type.toUpperCase()
                }}</span>
              </template>
              <template #title="{ item }">
                <div v-if="item" v-tooltip="item.name">{{ item.name }}</div>
              </template>
              <template #append="{ item }">
                <a v-if="item?.download" :href="item.download.url" download>
                  <v-icon
                    v-tooltip="
                      'Download ' +
                      item.download.type.toUpperCase() +
                      ' (' +
                      getFileSizeString(item.download.size) +
                      ')'
                    "
                    icon="mdi-download"
                  ></v-icon>
                </a>
              </template>
            </v-list>
          </div>

          <v-card-subtitle>Metadata</v-card-subtitle>
          <v-card-text v-if="!hasMetadata"
            >This {{ currentDetails.type }} has no metadata.</v-card-text
          >
          <v-card-text v-else>
            <RecursiveTable :data="currentDetails.metadata" />
          </v-card-text>
        </div>
      </Transition>

      <v-btn
        class="close-button transparent"
        variant="flat"
        icon
        @click="showModal = false"
      >
        <v-icon>mdi-close</v-icon>
      </v-btn>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.details-dialog {
  max-width: 50vw;
  max-height: 70vh;
}

.slide-in-enter-active,
.slide-in-leave-active,
.slide-out-enter-active,
.slide-out-leave-active {
  transition: all 0.25s ease-out;
}

.slide-in-enter-from,
.slide-out-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

.slide-in-leave-to,
.slide-out-enter-from {
  opacity: 0;
  transform: translateX(-30px);
}
</style>

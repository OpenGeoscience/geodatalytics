<script setup lang="ts">
import { ref, computed } from "vue";
import DetailView from "../DetailView.vue";
import ColormapSelect from "./ColormapSelect.vue";
import ColormapPreview from "./ColormapPreview.vue";

import { useNetworkStore, usePanelStore } from "@/store";
const networkStore = useNetworkStore();
const panelStore = usePanelStore();

const searchText = ref<string | undefined>();
const currentMode = ref();
const ticker = ref();
const tickerClock = ref(0);
const tickerInterval = 0.5; // seconds

const numTicks = computed(() => {
  return networkStore.availableAnimationStates?.length - 1 || 0;
});

const filteredNetworks = computed(() => {
  return networkStore.availableNetworks?.filter((network) => {
    return (
      !searchText.value ||
      network.name.toLowerCase().includes(searchText.value.toLowerCase())
    );
  });
});

function pause() {
  clearInterval(ticker.value);
  currentMode.value = undefined;
  ticker.value = undefined;
}

function play() {
  pause();
  currentMode.value = "play";
  ticker.value = setInterval(() => {
    tickerClock.value += tickerInterval;
    if (
      networkStore.animationConfig?.interval &&
      tickerClock.value % networkStore.animationConfig.interval === 0
    ) {
      if (networkStore.currentAnimationTick < numTicks.value) {
        networkStore.currentAnimationTick += 1;
      } else {
        pause();
      }
    }
  }, tickerInterval * 1000);
}

function rewind() {
  pause();
  currentMode.value = "rewind";
  ticker.value = setInterval(() => {
    tickerClock.value += tickerInterval;
    if (
      networkStore.animationConfig?.interval &&
      tickerClock.value % networkStore.animationConfig.interval === 0
    ) {
      if (networkStore.currentAnimationTick > 0) {
        networkStore.currentAnimationTick -= 1;
      } else {
        pause();
      }
    }
  }, tickerInterval * 1000);
}
</script>

<template>
  <div
    :class="
      networkStore.currentNetwork
        ? 'panel-content-outer'
        : 'panel-content-outer with-search'
    "
  >
    <v-text-field
      v-if="!networkStore.currentNetwork"
      v-model="searchText"
      label="Search Networks"
      variant="outlined"
      density="compact"
      class="mb-2"
      append-inner-icon="mdi-magnify"
      hide-details
    />
    <v-card class="panel-content-inner">
      <div v-if="networkStore.currentNetwork">
        <v-card-title class="network-title">
          <span>{{ networkStore.currentNetwork.name }}</span>
          <v-icon
            v-tooltip="'Close'"
            icon="mdi-close"
            size="small"
            @click="networkStore.currentNetwork = undefined"
          />
        </v-card-title>
        <div class="d-flex mx-2 mb-2" style="column-gap: 4px">
          <v-chip size="x-small">{{
            networkStore.currentNetwork.category
          }}</v-chip>
          <v-chip size="x-small"
            >{{ networkStore.currentNetwork.counts.nodes }} nodes</v-chip
          >
          <v-chip size="x-small"
            >{{ networkStore.currentNetwork.counts.edges }} edges</v-chip
          >
        </div>
        <div v-if="networkStore.editAllowed" class="mx-2 pb-2">
          <v-btn
            color="primary"
            variant="text"
            density="compact"
            class="px-1"
            prepend-icon="mdi-plus"
            text="Create Network Animation"
            @click="networkStore.creatingAnimation = true"
          ></v-btn>
          <div v-if="networkStore.creatingAnimation" class="d-flex">
            <v-text-field
              v-model="networkStore.newAnimationName"
              label="Animation Name"
              density="compact"
              autofocus
              hide-details
              @keydown.enter="networkStore.createAnimation"
            />
            <v-btn
              color="primary"
              variant="flat"
              style="min-width: 40px; min-height: 40px"
              :disabled="!networkStore.newAnimationName"
              @click="networkStore.createAnimation"
            >
              <v-icon icon="mdi-arrow-right" />
            </v-btn>
          </div>
        </div>
        <v-select
          v-model="networkStore.currentAnimation"
          :items="networkStore.availableAnimations"
          label="Select Animation"
          item-title="name"
          class="mx-2"
          density="compact"
          hide-details
          clearable
          return-object
          no-data-text="No animations exist for this network."
        >
          <template #item="{ props, item }">
            <v-list-item v-bind="props">
              <template #append>
                <v-icon
                  v-if="networkStore.editAllowed"
                  v-tooltip="'Delete this Animation'"
                  icon="mdi-delete"
                  @click.stop="networkStore.animationToDelete = item"
                ></v-icon>
              </template>
            </v-list-item>
          </template>
          <template #append>
            <v-menu
              location="bottom end"
              :close-on-content-click="false"
              open-on-hover
            >
              <template #activator="{ props: activatorProps }">
                <v-icon
                  v-bind="activatorProps"
                  icon="mdi-palette"
                  style="opacity: 1"
                />
              </template>
              <v-card
                class="layer-style-card mt-5"
                color="background"
                width="300"
              >
                <div
                  class="px-4 py-2"
                  style="
                    background-color: rgb(var(--v-theme-surface));
                    min-height: 40px;
                  "
                >
                  Configure Animation Style
                </div>
                <v-card-text v-if="networkStore.animationConfig">
                  <div>Time Visualization Mode</div>
                  <v-btn-toggle
                    v-model="networkStore.animationConfig.time_mode"
                    density="compact"
                    variant="outlined"
                    divided
                    mandatory
                  >
                    <v-btn :value="'slider'">Slider</v-btn>
                    <v-btn :value="'colormap'">Colormap</v-btn>
                  </v-btn-toggle>
                  <div
                    v-if="networkStore.animationConfig.time_mode === 'slider'"
                    class="mt-2"
                  >
                    <div>
                      Animation Interval:
                      {{ networkStore.animationConfig.interval }}
                      second{{
                        networkStore.animationConfig.interval !== 1 ? "s" : ""
                      }}
                    </div>
                    <v-slider
                      v-model="networkStore.animationConfig.interval"
                      color="primary"
                      thumb-size="18"
                      track-size="8"
                      :min="0.5"
                      :step="0.5"
                      :max="5"
                      hide-details
                    />
                  </div>
                  <div>
                    {{
                      networkStore.animationConfig.time_mode === "slider"
                        ? "Component Colormap"
                        : "Time Colormap"
                    }}
                    <colormap-select
                      :model-value="networkStore.animationConfig.colormap"
                      :n-colors="
                        (networkStore.animationConfig.time_mode === 'slider'
                          ? networkStore.currentAnimationState?.components
                              .length
                          : networkStore.availableAnimationStates.length) || -1
                      "
                      discrete
                      :edit-mode="false"
                      :disabled="false"
                      @update="
                        (v) => {
                          if (networkStore.animationConfig)
                            networkStore.animationConfig.colormap = v;
                        }
                      "
                    />
                  </div>
                  <div
                    class="d-flex mt-2"
                    style="justify-content: space-between; align-items: center"
                  >
                    Highlighted Node Color
                    <v-menu
                      :close-on-content-click="false"
                      open-on-hover
                      location="end"
                    >
                      <template #activator="{ props: activatorProps }">
                        <div
                          v-bind="activatorProps"
                          class="color-square"
                          :style="{
                            backgroundColor:
                              networkStore.animationConfig.hover_color,
                          }"
                        ></div>
                      </template>
                      <v-card>
                        <v-color-picker
                          v-model:model-value="
                            networkStore.animationConfig.hover_color
                          "
                          mode="rgb"
                        />
                      </v-card>
                    </v-menu>
                  </div>
                  <div
                    v-if="networkStore.animationConfig.time_mode === 'slider'"
                    class="d-flex mt-2"
                    style="justify-content: space-between; align-items: center"
                  >
                    Deactivated Node Color
                    <v-menu
                      :close-on-content-click="false"
                      open-on-hover
                      location="end"
                    >
                      <template #activator="{ props: activatorProps }">
                        <div
                          v-bind="activatorProps"
                          class="color-square"
                          :style="{
                            backgroundColor:
                              networkStore.animationConfig.deactivated_color,
                          }"
                        ></div>
                      </template>
                      <v-card>
                        <v-color-picker
                          v-model:model-value="
                            networkStore.animationConfig.deactivated_color
                          "
                          mode="rgb"
                        />
                      </v-card>
                    </v-menu>
                  </div>
                  <div
                    v-if="networkStore.animationConfig.time_mode === 'slider'"
                    class="mt-2"
                  >
                    Deactivated Node Opacity:
                    {{ networkStore.animationConfig.deactivated_opacity }}
                    <v-slider
                      v-model="networkStore.animationConfig.deactivated_opacity"
                      color="primary"
                      thumb-size="18"
                      track-size="8"
                      :min="0"
                      :max="1"
                      :step="0.1"
                      hide-details
                    ></v-slider>
                  </div>
                </v-card-text>
              </v-card>
            </v-menu>
          </template>
        </v-select>
        <div class="px-2 mt-2">
          <colormap-preview
            v-if="networkStore.nodeGroupColorMarkers.length"
            :colormap="{ markers: networkStore.nodeGroupColorMarkers }"
            :n-colors="networkStore.nodeGroupColorMarkers.length"
            discrete
            proportional
            tooltip
            @hover="(v) => (networkStore.hoverNodeIds = v?.node_ids || [])"
          />
        </div>
        <div
          v-if="
            networkStore.currentAnimation &&
            networkStore.animationConfig?.time_mode === 'slider'
          "
          class="px-3"
        >
          <v-progress-linear
            v-if="networkStore.loadingStates"
            indeterminate
            class="mt-2"
          />
          <div v-else>
            <div
              v-if="
                networkStore.editAllowed &&
                networkStore.currentAnimationEditable
              "
              class="d-flex"
              style="justify-content: space-between"
            >
              <v-btn
                color="primary"
                variant="text"
                density="compact"
                class="px-1"
                prepend-icon="mdi-delete"
                text="Delete Current State"
                :disabled="!networkStore.currentAnimationState"
                @click="
                  networkStore.stateToDelete =
                    networkStore.currentAnimationState
                "
              ></v-btn>
              <v-btn
                color="primary"
                variant="text"
                density="compact"
                class="px-1"
                prepend-icon="mdi-plus"
                text="Add State"
                @click="networkStore.createAnimationState"
              ></v-btn>
            </div>
            <div
              v-if="!networkStore.availableAnimationStates?.length"
              class="animation-row"
            >
              This animation has no states to show.
            </div>
            <div
              v-else-if="networkStore.availableAnimationStates.length == 1"
              class="animation-row"
            >
              This animation only has one state.
            </div>
            <div v-else>
              <div class="animation-row">
                <v-slider
                  v-model="networkStore.currentAnimationTick"
                  color="primary"
                  thumb-size="18"
                  track-size="8"
                  min="0"
                  step="1"
                  :max="numTicks"
                  show-ticks="always"
                  tick-size="5"
                  hide-details
                  class="pr-2"
                />
                {{ networkStore.currentAnimationTick }}
              </div>
              <div class="animation-row">
                <v-btn
                  icon="mdi-play"
                  variant="text"
                  density="compact"
                  :disabled="networkStore.currentAnimationTick == numTicks"
                  @click="play"
                />
                <v-btn
                  icon="mdi-pause"
                  variant="text"
                  density="compact"
                  :disabled="!['play', 'rewind'].includes(currentMode)"
                  @click="pause"
                />
                <v-btn
                  icon="mdi-rewind"
                  variant="text"
                  density="compact"
                  :disabled="networkStore.currentAnimationTick < 1"
                  @click="rewind"
                />
              </div>
            </div>
          </div>
        </div>
        <v-expansion-panels
          v-if="networkStore.currentAnimation"
          flat
          bg-color="transparent"
          elevation="0"
          class="px-0 compact-expansion"
          variant="accordion"
        >
          <v-expansion-panel
            v-if="
              networkStore.currentAnimationSyncLayers?.length ||
              networkStore.currentAnimation.task_result?.id
            "
          >
            <v-expansion-panel-title>
              Related ({{
                (networkStore.currentAnimationSyncLayers?.length || 0) +
                (networkStore.currentAnimation.task_result?.id ? 1 : 0)
              }})
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <v-list density="compact">
                <v-list-item
                  v-if="networkStore.currentAnimation.task_result"
                  class="compact-list-item"
                >
                  <template #title>
                    <v-list-item-title class="capitalize">
                      {{
                        networkStore.currentAnimation.task_result.task_type.replaceAll(
                          "_",
                          " ",
                        )
                      }}
                      Result
                    </v-list-item-title>
                  </template>
                  <template #append>
                    <v-btn
                      color="primary"
                      density="compact"
                      style="display: block"
                      @click="
                        async () => {
                          await panelStore.setVisibility(
                            {
                              taskresult:
                                networkStore.currentAnimation?.task_result,
                            },
                            !panelStore.isVisible(
                              {
                                taskresult:
                                  networkStore.currentAnimation?.task_result,
                              },
                              false,
                            ),
                            undefined,
                            false,
                          );
                          networkStore.updateSyncLayers();
                        }
                      "
                    >
                      {{
                        panelStore.isVisible(
                          {
                            taskresult:
                              networkStore.currentAnimation?.task_result,
                          },
                          false,
                        )
                          ? "Hide"
                          : "Show"
                      }}
                    </v-btn>
                  </template>
                </v-list-item>
                <v-list-item
                  v-for="syncLayer in networkStore.currentAnimationSyncLayers"
                  :key="syncLayer.id"
                  :title="syncLayer.name"
                  class="compact-list-item"
                >
                  <template #append>
                    <v-btn
                      color="primary"
                      density="compact"
                      style="display: block"
                      @click="
                        async () => {
                          await panelStore.setVisibility(
                            { layer: syncLayer },
                            !panelStore.isVisible({ layer: syncLayer }),
                          );
                          networkStore.updateSyncLayers();
                        }
                      "
                    >
                      {{
                        panelStore.isVisible({ layer: syncLayer })
                          ? "Hide"
                          : "Show"
                      }}
                    </v-btn>
                  </template>
                </v-list-item>
              </v-list>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </div>
      <div v-else-if="filteredNetworks?.length">
        <v-list density="compact">
          <v-list-item
            v-for="network in filteredNetworks"
            :key="network.id"
            @click="networkStore.currentNetwork = network"
          >
            {{ network.name }}
            <template #append>
              <DetailView :details="{ ...network, type: 'network' }" />
            </template>
          </v-list-item>
        </v-list>
      </div>
      <v-progress-linear
        v-else-if="networkStore.loadingNetworks"
        indeterminate
      ></v-progress-linear>
      <v-card-text v-else class="help-text">No available Networks.</v-card-text>
    </v-card>
  </div>
  <v-dialog
    v-if="networkStore.editAllowed"
    :model-value="!!networkStore.animationToDelete"
    width="300"
  >
    <v-card v-if="networkStore.animationToDelete">
      <v-card-title class="pa-3">
        Delete animation
        <v-btn
          class="close-button transparent"
          variant="flat"
          icon
          @click="networkStore.animationToDelete = undefined"
        >
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-card-text>
        Are you sure you want to delete animation "{{
          networkStore.animationToDelete.name
        }}"?
      </v-card-text>
      <v-card-actions class="d-flex" style="justify-content: space-evenly">
        <v-btn
          color="red"
          :disabled="!networkStore.editAllowed"
          @click="networkStore.deleteAnimation"
        >
          Delete
        </v-btn>
        <v-btn
          color="primary"
          variant="tonal"
          @click="networkStore.animationToDelete = undefined"
        >
          Cancel
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
  <v-dialog
    v-if="networkStore.editAllowed && networkStore.currentAnimationEditable"
    :model-value="!!networkStore.stateToDelete"
    width="300"
  >
    <v-card v-if="networkStore.stateToDelete">
      <v-card-title class="pa-3">
        Delete animation state
        <v-btn
          class="close-button transparent"
          variant="flat"
          icon
          @click="networkStore.stateToDelete = undefined"
        >
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-card-text>
        Are you sure you want to delete state
        {{ networkStore.stateToDelete.index }}?
      </v-card-text>
      <v-card-actions class="d-flex" style="justify-content: space-evenly">
        <v-btn
          color="red"
          :disabled="
            !networkStore.editAllowed || !networkStore.currentAnimationEditable
          "
          @click="networkStore.deleteAnimationState"
        >
          Delete
        </v-btn>
        <v-btn
          color="primary"
          variant="tonal"
          @click="networkStore.stateToDelete = undefined"
        >
          Cancel
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style>
.network-title {
  display: flex;
  width: 100%;
  justify-content: space-between;
  align-items: center;
}
.network-title > span:first-child {
  flex-shrink: 1;
  min-width: 100px;
  overflow-x: hidden;
  text-overflow: ellipsis;
  font-size: 1rem;
}
.animation-row {
  display: flex;
  align-items: center;
  width: calc(100% - 10px);
  justify-content: space-around;
}
.animation-row .v-expansion-panel-title {
  min-height: 0 !important;
  padding: 12px 0px !important;
}
.compact-expansion .v-expansion-panel-title {
  min-height: 0px;
  padding: 8px 16px;
}
.compact-list-item {
  padding: 2px 16px;
  min-height: 0px;
}
.compact-list-item .v-list-item-title {
  font-size: 0.9rem;
}
</style>

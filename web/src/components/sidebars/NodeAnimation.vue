<script setup lang="ts">
import type { Layer, Network } from "@/types";
import { ref, watch, computed } from "vue";

import { useLayerStore, useNetworkStore } from "@/store";
const networkStore = useNetworkStore();
const layerStore = useLayerStore();

const props = defineProps<{
  nodeFailures?: Record<number, number[]>;
  nodeRecoveries?: Record<number, number[]>;
  network: Network;
  additionalAnimationLayers: Layer[] | undefined;
}>();

const currentMode = ref();
const currentTick = ref(0);
const ticker = ref();
const tickerClock = ref(0);
const animationInterval = ref(1); // seconds
const tickerInterval = 0.5; // seconds

const nodeChanges = computed(() => {
  const changes = props.nodeRecoveries || props.nodeFailures || {};
  return Object.fromEntries(
    Object.entries(changes).filter(
      ([key]) => !["id", "name", "type", "visible", "showable"].includes(key),
    ),
  );
});

const numTicks = computed(() => {
  return Object.keys(nodeChanges.value).length - 1;
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
    if (tickerClock.value % animationInterval.value === 0) {
      if (nodeChanges.value && currentTick.value < numTicks.value) {
        currentTick.value += 1;
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
    if (tickerClock.value % animationInterval.value === 0) {
      if (currentTick.value > 0) {
        currentTick.value -= 1;
      } else {
        pause();
      }
    }
  }, tickerInterval * 1000);
}

watch(currentTick, async () => {
  if (nodeChanges.value) {
    const deactivated = nodeChanges.value[currentTick.value];
    if (props.network)
      networkStore.setNetworkDeactivatedNodes(
        props.network,
        deactivated || [],
        true,
      );
    if (props.additionalAnimationLayers) {
      props.additionalAnimationLayers.forEach((layer) => {
        layerStore.selectedLayers = layerStore.selectedLayers.map((l) => {
          if (l.id === layer.id && l.visible)
            l.current_frame_index = currentTick.value;
          return l;
        });
      });
    }
  }
});
</script>

<template>
  <div v-if="nodeChanges">
    <div class="animation-row">
      <v-icon
        :icon="
          currentMode === 'play'
            ? 'mdi-play'
            : currentMode === 'rewind'
              ? 'mdi-rewind'
              : 'mdi-pause'
        "
      />
      <v-slider
        v-model="currentTick"
        color="primary"
        class="ml-5"
        thumb-size="18"
        track-size="8"
        min="0"
        step="1"
        :max="numTicks"
        hide-details
      />
      {{ currentTick + 1 }}
    </div>
    <div class="animation-row">
      <v-btn icon="mdi-play" variant="text" density="compact" @click="play" />
      <v-btn icon="mdi-pause" variant="text" density="compact" @click="pause" />
      <v-btn
        icon="mdi-rewind"
        variant="text"
        density="compact"
        @click="rewind"
      />
    </div>
    <v-expansion-panels
      flat
      bg-color="transparent"
      elevation="0"
      class="animation-row"
    >
      <v-expansion-panel>
        <v-expansion-panel-title class="pa-1">
          Animation Interval: {{ animationInterval }} second{{
            animationInterval !== 1 ? "s" : ""
          }}
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <v-slider
            v-model="animationInterval"
            color="primary"
            class="ml-5"
            thumb-size="18"
            track-size="8"
            :min="tickerInterval"
            :step="tickerInterval"
            :max="5"
            hide-details
          />
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </div>
</template>

<style>
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
</style>

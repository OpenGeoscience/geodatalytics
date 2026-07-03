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
const seconds = computed(() => {
  const nNodes = props.network.nodes.length;
  const ordersOfMagnitude = nNodes.toString().length;
  return Math.max(ordersOfMagnitude, 4);
});

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
    if (nodeChanges.value && currentTick.value < numTicks.value) {
      currentTick.value += 1;
    } else {
      pause();
    }
  }, seconds.value * 1000);
}

function rewind() {
  pause();
  currentMode.value = "rewind";
  ticker.value = setInterval(() => {
    if (currentTick.value > 0) {
      currentTick.value -= 1;
    } else {
      pause();
    }
  }, seconds.value * 1000);
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
        show-ticks="always"
        color="primary"
        class="ml-5"
        tick-size="6"
        thumb-size="15"
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
  </div>
</template>

<style>
.animation-row {
  display: flex;
  align-items: center;
  width: calc(100% - 10px);
  justify-content: space-around;
}
</style>

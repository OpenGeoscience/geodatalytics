<script setup lang="ts">
import type { Colormap } from "@/types";
import { watch, ref, onMounted } from "vue";
import { useStyleStore } from "@/store";

const styleStore = useStyleStore();

const canvas = ref();
const props = defineProps<{
  colormap: Colormap;
  discrete: boolean;
  nColors: number;
  range?: [number | undefined, number | undefined];
}>();

function draw() {
  let markers = props.colormap.markers;
  if (!markers) return;
  const ctx = canvas.value.getContext("2d");
  const rect = [0, 0, canvas.value.width, canvas.value.height];
  ctx.clearRect(...rect);
  if (props.discrete) {
    if (props.nColors > 0) {
      markers = styleStore.colormapMarkersSubsample(
        {
          id: -1,
          name: "colormap",
          markers,
          project: null,
        },
        {
          discrete: props.discrete,
          n_colors: props.nColors,
        },
      );
    }
    if (markers)
      markers.forEach((marker, index) => {
        if (markers) {
          ctx.fillStyle = marker.color;
          const start = (canvas.value.width / markers.length) * index;
          const end = (canvas.value.width / markers.length) * (index + 1);
          ctx.fillRect(start, 0, end, canvas.value.height);
        }
      });
  } else {
    const gradient = ctx.createLinearGradient(0, 0, canvas.value.width, 0);
    markers.forEach((marker) => {
      gradient.addColorStop(marker.value, marker.color);
    });
    ctx.fillStyle = gradient;
    ctx.fillRect(...rect);
  }
}
onMounted(draw);
watch(
  [
    () => props.colormap,
    () => props.discrete,
    () => props.nColors,
    () => props.colormap.markers,
  ],
  draw,
  { deep: true },
);
</script>

<template>
  <div class="d-flex" style="column-gap: 5px; width: 100%">
    <span v-if="props.range">{{ props.range[0]?.toPrecision(3) }}</span>
    <canvas ref="canvas" class="colormap-canvas"></canvas>
    <span v-if="props.range">{{ props.range[1]?.toPrecision(3) }}</span>
  </div>
</template>

<style scoped>
.colormap-canvas {
  border: 1px solid rgb(var(--v-theme-on-surface-variant));
  height: 20px;
  width: 100%;
}
</style>

<script setup lang="ts">
import { computed } from "vue";

const emit = defineEmits(["update"]);
const props = withDefaults(
  defineProps<{
    model?: number;
    rangeModel?: number[];
    min?: number;
    max?: number;
    step?: number;
    disabled?: boolean;
  }>(),
  {
    model: undefined,
    rangeModel: undefined,
    min: 1,
    max: 10,
    step: 1,
    disabled: false,
  },
);

const precision = computed(() => {
  if (!isFinite(props.step)) return 0;
  let e = 1;
  let p = 0;
  while (Math.round(props.step * e) / e !== props.step) {
    e *= 10;
    p++;
  }
  return p;
});

function blur() {
  const activeElement = document.activeElement as HTMLElement;
  if (activeElement) activeElement.blur();
}

function getInputWidth() {
  let width = 50;
  width += props.max.toPrecision(precision.value + 1).length * 6;
  width += precision.value * 6;
  return width + "px";
}

function updateValue(value: number) {
  if (Number.isInteger(props.step)) value = Math.round(value);
  if (value < props.min) value = props.min;
  if (value > props.max) value = props.max;
  emit("update", value);
}

function updateRange(lower: number, upper: number) {
  if (Number.isInteger(props.step)) {
    lower = Math.round(lower);
    upper = Math.round(upper);
  }
  if (lower < props.min) lower = props.min;
  if (upper > props.max) upper = props.max;
  if (lower > upper) lower = upper;
  emit("update", [lower, upper]);
}
</script>

<template>
  <v-slider
    v-if="props.model !== undefined"
    :model-value="props.model"
    :min="props.min"
    :max="props.max"
    :step="props.step"
    :disabled="props.disabled"
    color="primary"
    track-size="6"
    hide-details
    @update:model-value="(v: number) => updateValue(v)"
  >
    <template #append>
      <v-number-input
        :model-value="props.model"
        :min="props.min"
        :max="props.max"
        :step="props.step"
        :precision="precision"
        :style="{ width: getInputWidth() }"
        variant="outlined"
        control-variant="stacked"
        hide-details
        @update:model-value="updateValue"
        @keydown.enter="blur()"
      />
    </template>
  </v-slider>
  <v-range-slider
    v-else-if="props.rangeModel !== undefined"
    :model-value="props.rangeModel"
    :min="props.min"
    :max="props.max"
    :step="props.step"
    :disabled="props.disabled"
    color="primary"
    strict
    hide-details
    @update:model-value="([lower, upper]) => updateRange(lower, upper)"
  >
    <template #prepend>
      <v-number-input
        :model-value="props.rangeModel[0]"
        :min="props.min"
        :max="props.rangeModel[1]"
        :step="props.step"
        :precision="precision"
        :style="{ width: getInputWidth() }"
        variant="outlined"
        control-variant="stacked"
        hide-details
        @update:model-value="
          (v) => {
            if (props.rangeModel) updateRange(v, props.rangeModel[1]);
          }
        "
        @keydown.enter="blur()"
      />
    </template>
    <template #append>
      <v-number-input
        :model-value="props.rangeModel[1]"
        :min="props.rangeModel[0]"
        :max="props.max"
        :step="props.step"
        :precision="precision"
        :style="{ width: getInputWidth() }"
        variant="outlined"
        control-variant="stacked"
        hide-details
        @update:model-value="
          (v) => {
            if (props.rangeModel) updateRange(props.rangeModel[0], v);
          }
        "
        @keydown.enter="blur()"
      />
    </template>
  </v-range-slider>
</template>

<style>
.v-number-input input {
  padding: 8px !important;
  min-height: 0 !important;
  max-height: 32px !important;
}
.v-number-input__control .v-btn {
  background-color: rgb(var(--v-theme-primary)) !important;
  padding: 0px !important;
  width: 25px !important;
  max-height: 16px !important;
}
.v-number-input__control .v-btn i {
  color: rgb(var(--v-theme-button-text)) !important;
}
.v-slider.v-input--horizontal {
  margin-inline: 0 !important;
}
</style>

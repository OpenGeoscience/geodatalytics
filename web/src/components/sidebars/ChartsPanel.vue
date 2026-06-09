<script setup lang="ts">
import { computed, ref } from "vue";
import { Line } from "vue-chartjs";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import type { ChartOptions } from "@/types";
import DetailView from "../DetailView.vue";

import { useAnalysisStore } from "@/store";
const analysisStore = useAnalysisStore();

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
);

const searchText = ref<string | undefined>();
const filteredCharts = computed(() => {
  return analysisStore.availableCharts?.filter((chart) => {
    return (
      !searchText.value ||
      chart.name.toLowerCase().includes(searchText.value.toLowerCase())
    );
  });
});
const defaultChartData = {
  labels: [],
  datasets: [
    {
      label: "No Data",
      data: [],
    },
  ],
};
const defaultOptions = {
  responsive: true,
  maintainAspectRatio: false,
};
const currentXStart = ref(0);
const currentXRange = ref(500);
const downloadButton = ref();

const options = computed(() => {
  if (!analysisStore.currentChart) {
    return defaultOptions;
  }

  const customOptions: ChartOptions = {
    plugins: {},
    scales: {},
  };
  const savedOptions = analysisStore.currentChart.chart_options;
  if (savedOptions.chart_title) {
    customOptions.plugins.title = {
      display: true,
      text: savedOptions.chart_title,
    };
  }
  if (savedOptions.x_title) {
    if (!customOptions.scales.x) {
      customOptions.scales.x = {};
    }
    customOptions.scales.x.title = {
      display: true,
      text: savedOptions.x_title,
    };
  }
  if (savedOptions.x_range) {
    if (!customOptions.scales.x) {
      customOptions.scales.x = {};
    }
    customOptions.scales.x.min = savedOptions.x_range[0];
    customOptions.scales.x.max = savedOptions.x_range[1];
  }
  if (savedOptions.y_title) {
    if (!customOptions.scales.y) {
      customOptions.scales.y = {};
    }
    customOptions.scales.y.title = {
      display: true,
      text: savedOptions.y_title,
    };
  }
  if (savedOptions.y_range) {
    if (!customOptions.scales.y) {
      customOptions.scales.y = {};
    }
    customOptions.scales.y.min = savedOptions.y_range[0];
    customOptions.scales.y.max = savedOptions.y_range[1];
  }
  return Object.assign({}, defaultOptions, customOptions);
});

const showXRange = computed(() => {
  return (
    analysisStore.currentChart?.chart_data?.labels &&
    analysisStore.currentChart.chart_data.labels.length > 500
  );
});

const maxX = computed(() => {
  return analysisStore.currentChart?.chart_data?.labels && showXRange.value
    ? analysisStore.currentChart.chart_data.labels.length
    : 0;
});

const data = computed(() => {
  let currentData = analysisStore.currentChart?.chart_data;

  if (!currentData || Object.keys(currentData).length === 0) {
    currentData = defaultChartData;
  }

  // clip to current x range
  if (showXRange.value) {
    const slice = [
      currentXStart.value,
      currentXStart.value + currentXRange.value,
    ];
    currentData = {
      labels: currentData.labels.slice(...slice),
      datasets: currentData.datasets.map((d) =>
        Object.assign({}, d, {
          data: d.data.slice(...slice),
        }),
      ),
    };
  }
  return currentData;
});

const downloadReady = computed(() => {
  if (downloadButton.value && analysisStore.currentChart) {
    const filename = `${analysisStore.currentChart.name}.json`;
    const contents = data.value;
    downloadButton.value.setAttribute(
      "href",
      "data:text/json;charset=utf-8," +
        encodeURIComponent(JSON.stringify(contents)),
    );
    downloadButton.value.setAttribute("download", filename);
  }
  return true;
});
</script>

<template>
  <div
    :class="
      analysisStore.currentChart
        ? 'panel-content-outer'
        : 'panel-content-outer with-search'
    "
  >
    <v-text-field
      v-if="!analysisStore.currentChart"
      v-model="searchText"
      label="Search Charts"
      variant="outlined"
      density="compact"
      class="mb-2"
      append-inner-icon="mdi-magnify"
      hide-details
    />
    <v-card class="panel-content-inner">
      <div v-if="analysisStore.currentChart" class="pa-2" style="height: 100%">
        <div style="position: absolute; right: 10px">
          <a ref="downloadButton">
            <v-icon
              v-show="downloadReady"
              v-tooltip="'Download'"
              icon="mdi-download"
              variant="plain"
            />
          </a>
          <v-icon
            v-tooltip="'Close'"
            icon="mdi-close"
            variant="plain"
            @click="analysisStore.currentChart = undefined"
          />
        </div>
        <Line :data="data" :options="options" />
        <div v-if="showXRange" class="pt-3">
          Current X Axis Slice (From {{ maxX }} values)
          <div style="display: flex">
            <v-text-field
              v-model.number="currentXRange"
              type="number"
              label="Number of values"
              density="compact"
              :max="maxX"
              min="0"
            />
            <v-text-field
              v-model.number="currentXStart"
              type="number"
              label="Starting from"
              density="compact"
              :max="maxX"
              min="0"
            />
          </div>
        </div>
      </div>
      <v-list v-else-if="filteredCharts?.length" density="compact">
        <v-list-item
          v-for="chart in filteredCharts"
          :key="chart.id"
          @click="analysisStore.currentChart = chart"
        >
          {{ chart.name }}
          <template #append>
            <v-icon
              v-tooltip="chart.description"
              icon="mdi-information-outline"
              size="small"
            ></v-icon>
            <v-icon icon="mdi-poll" size="small" class="ml-2"></v-icon>
            <DetailView :details="{ ...chart, type: 'chart' }" />
          </template>
        </v-list-item>
      </v-list>
      <v-progress-linear
        v-else-if="analysisStore.loadingCharts"
        indeterminate
      ></v-progress-linear>
      <v-card-text v-else class="help-text">No available Charts.</v-card-text>
    </v-card>
  </div>
</template>

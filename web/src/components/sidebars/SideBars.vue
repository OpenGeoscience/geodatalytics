<script setup lang="ts">
import { ref } from "vue";
import type { Ref } from "vue";
import { logout } from "@/api/auth";
import draggable from "vuedraggable";

// @ts-ignore: this library lacks types
import draggableResizable from "vue-draggable-resizable";

import ProjectConfig from "@/components/projects/ProjectConfig.vue";
import FloatingPanel from "@/components/sidebars/FloatingPanel.vue";
import ChartsPanel from "@/components/sidebars/ChartsPanel.vue";
import AnalyticsPanel from "@/components/sidebars/AnalyticsPanel.vue";
import DatasetsPanel from "@/components/sidebars/DatasetsPanel.vue";
import LayersPanel from "@/components/sidebars/LayersPanel.vue";
import NetworksPanel from "@/components/sidebars/NetworksPanel.vue";
import LegendPanel from "./LegendPanel.vue";

import { useAppStore, usePanelStore, useProjectStore } from "@/store";
import KitwareLogo from "@/assets/Kitware.png";

const appStore = useAppStore();
const panelStore = usePanelStore();
const projectStore = useProjectStore();

const version = import.meta.env.VITE_VERSION;
const copied: Ref<string | undefined> = ref();

function copyToClipboard(content: string) {
  navigator.clipboard.writeText(content).then(() => {
    copied.value = content;
  });
}

function toggleSidebar(sidebar: "left" | "right") {
  if (appStore.openSidebars.includes(sidebar)) {
    appStore.openSidebars = appStore.openSidebars.filter((s) => s !== sidebar);
  } else {
    appStore.openSidebars = [...appStore.openSidebars, sidebar];
  }
}
</script>

<template>
  <div>
    <v-navigation-drawer
      floating
      width="300"
      location="left"
      color="background"
      :class="
        appStore.openSidebars.includes('left')
          ? 'sidebar left'
          : 'sidebar left closed'
      "
    >
      <v-toolbar class="toolbar px-5" color="background">
        <v-toolbar-title>
          <img width="15px" class="mr-1" :src="KitwareLogo" />
          <span class="secondary-text">GeoDatalytics</span>
          <v-menu
            activator="parent"
            :open-on-hover="true"
            :close-on-content-click="false"
            @update:model-value="copied = undefined"
          >
            <v-card class="pa-3" style="width: fit-content">
              <v-card-subtitle>
                <a
                  href="https://github.com/OpenGeoscience/geodatalytics"
                  target="_blank"
                  style="text-decoration: none"
                >
                  <v-icon icon="mdi-github" />
                  Source
                </a>
              </v-card-subtitle>
              <v-card-subtitle>
                <v-icon
                  :icon="copied === version ? 'mdi-check' : 'mdi-content-copy'"
                  :color="copied === version ? 'success' : 'primary'"
                  @click="copyToClipboard(version)"
                />
                Version: {{ version }}
              </v-card-subtitle>
            </v-card>
          </v-menu>
        </v-toolbar-title>
        <v-icon
          v-tooltip="'Toggle Sidebar'"
          icon="mdi-dock-left"
          class="ml-5"
          @click="toggleSidebar('left')"
        ></v-icon>
      </v-toolbar>
      <ProjectConfig />
      <div class="panel-set pt-2">
        <draggable
          v-model="panelStore.leftPanels"
          item-key="id"
          group="panels"
          class="panel-container"
          handle=".panel-title"
          @start="
            (e: any) =>
              (panelStore.dragPoint = {
                x: e.originalEvent.layerX,
                y: e.originalEvent.layerY,
              })
          "
          @end="panelStore.dragEnd"
        >
          <template #item="{ element }">
            <FloatingPanel :id="element.id">
              <DatasetsPanel
                v-if="element.id === 'datasets'"
                :datasets="projectStore.availableDatasets"
              />
              <LayersPanel v-else-if="element.id === 'layers'" />
              <LegendPanel v-else-if="element.id === 'legend'" />
              <ChartsPanel v-else-if="element.id === 'charts'" />
              <NetworksPanel v-else-if="element.id === 'networks'" />
              <AnalyticsPanel v-else-if="element.id === 'analytics'" />
            </FloatingPanel>
          </template>
        </draggable>
      </div>
    </v-navigation-drawer>

    <v-navigation-drawer
      floating
      width="300"
      location="right"
      color="background"
      :class="
        appStore.openSidebars.includes('right')
          ? 'sidebar right'
          : 'sidebar right closed'
      "
    >
      <v-toolbar
        :class="
          appStore.openSidebars.includes('right')
            ? 'toolbar px-5'
            : 'toolbar px-5 right'
        "
        color="background"
      >
        <v-icon
          v-tooltip="'Toggle Sidebar'"
          icon="mdi-dock-right"
          class="mr-5"
          @click="toggleSidebar('right')"
        ></v-icon>
        <div v-if="appStore.currentUser?.id">
          {{ appStore.currentUser.first_name }}
          <v-icon
            v-tooltip="'Log Out'"
            icon="mdi-logout"
            @click="logout"
          ></v-icon>
        </div>
      </v-toolbar>

      <div class="panel-set pt-2">
        <draggable
          v-model="panelStore.rightPanels"
          item-key="id"
          group="panels"
          class="panel-container"
          handle=".panel-title"
          @start="
            (e: any) =>
              (panelStore.dragPoint = {
                x: e.originalEvent.layerX,
                y: e.originalEvent.layerY,
              })
          "
          @end="panelStore.dragEnd"
        >
          <template #item="{ element }">
            <FloatingPanel :id="element.id">
              <DatasetsPanel
                v-if="element.id === 'datasets'"
                :datasets="projectStore.availableDatasets"
              />
              <LayersPanel v-else-if="element.id === 'layers'" />
              <LegendPanel v-else-if="element.id === 'legend'" />
              <ChartsPanel v-else-if="element.id === 'charts'" />
              <NetworksPanel v-else-if="element.id === 'networks'" />
              <AnalyticsPanel v-else-if="element.id === 'analytics'" />
            </FloatingPanel>
          </template>
        </draggable>
      </div>
    </v-navigation-drawer>

    <draggable
      id="floating-panel-set"
      v-model="panelStore.floatingPanels"
      item-key="id"
      group="panels"
      handle=".panel-title"
      filter=".vdr"
      :prevent-on-filter="false"
      :style="{
        left: appStore.openSidebars.includes('left') ? '360px' : '0px',
        right: appStore.openSidebars.includes('right') ? '360px' : '0px',
      }"
    >
      <template #item="{ element }">
        <div>
          <draggable-resizable
            class="floating-panel"
            active
            prevent-deactivation
            drag-handle=".panel-title"
            :handles="
              element.collapsed
                ? ['ml', 'mr']
                : ['tl', 'tm', 'tr', 'ml', 'mr', 'bl', 'bm', 'br']
            "
            class-name-handle="panel-border"
            :x="element.position?.x || 0"
            :y="element.position?.y || 0"
            :w="element.width || 300"
            :h="element.height || (element.collapsed ? 50 : 200)"
            :min-width="300"
            :min-height="200"
            :on-drag-start="
              (e: any) => (panelStore.dragPoint = { x: e.layerX, y: e.layerY })
            "
            :on-drag-end="panelStore.dragEnd"
            @dragging="
              (x: number, y: number) =>
                panelStore.dragFloating(x, y, element.id)
            "
          >
            <FloatingPanel :id="element.id">
              <DatasetsPanel
                v-if="element.id === 'datasets'"
                :datasets="projectStore.availableDatasets"
              />
              <LayersPanel v-else-if="element.id === 'layers'" />
              <LegendPanel v-else-if="element.id === 'legend'" />
              <ChartsPanel v-else-if="element.id === 'charts'" />
              <NetworksPanel v-else-if="element.id === 'networks'" />
              <AnalyticsPanel v-else-if="element.id === 'analytics'" />
            </FloatingPanel>
          </draggable-resizable>
        </div>
      </template>
    </draggable>
  </div>
</template>

<style>
.sidebar {
  margin: 10px;
  border: 1px solid rgb(var(--v-theme-border));
  border-radius: 10px;
  width: 350px !important;
  max-height: calc(100% - 20px);
  z-index: 2 !important;
}

.sidebar > .v-navigation-drawer__content {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar.closed {
  max-height: 0;
  border: none;
  /* Must be above floating panels */
  z-index: 5 !important;
}

.toolbar {
  border-radius: 10px 10px 0px 0px !important;
  border-bottom: 1px solid rgb(var(--v-theme-border)) !important;
}

.toolbar > .v-toolbar__content {
  display: flex;
  height: 50px !important;
  justify-content: space-between;
}

.sidebar.closed .toolbar {
  border-radius: 10px !important;
  width: fit-content !important;
  position: absolute !important;
  border: 1px solid rgb(var(--v-theme-border));
}

.sidebar.closed
  > .v-navigation-drawer__content
  > .toolbar
  > .v-toolbar__content {
  height: 3rem !important;
}

.right {
  position: absolute !important;
  right: 0;
}

.v-toolbar__content {
  height: 4rem !important;
}

.v-toolbar__content > .v-toolbar-title {
  margin-inline-start: 0px !important;
}

.panel-set {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  min-height: 0;
}

.v-text-field {
  background-color: rgb(var(--v-theme-background));
}

.v-checkbox-btn .v-label {
  margin-left: 5px;
}

#floating-panel-set {
  position: absolute;
  top: 0;
  height: 100vh !important;
  z-index: 2 !important;
}

.floating-panel {
  position: absolute;
  z-index: 2 !important;
}

.sortable-drag {
  max-width: 300px;
  max-height: 200px;
  visibility: visible;
}

#floating-panel-set .sortable-ghost {
  visibility: hidden;
}

.v-tooltip {
  /* on top of floating panels */
  z-index: 5 !important;
}
</style>

<script setup lang="ts">
import { ref, Ref, watch } from "vue";
import { useTheme } from "vuetify/lib/framework.mjs";

import { logout } from "@/api/auth";

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

const version = import.meta.env.VITE_APP_VERSION;
const copied: Ref<string | undefined> = ref();

const themeManager = useTheme();
const darkMode = ref<boolean>(appStore.theme === "dark");

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

function togglePanelVisibility(id: string) {
  panelStore.panelArrangement = panelStore.panelArrangement.map((p) => {
    if (p.id == id) p.visible = !p.visible;
    return p;
  });
}

watch(darkMode, () => {
  appStore.theme = darkMode.value ? "dark" : "light";
  themeManager.change(appStore.theme);
});
</script>

<template>
  <div>
    <v-navigation-drawer floating width="300" location="left" color="background" :class="appStore.openSidebars.includes('left') ? 'sidebar left' : 'sidebar left closed'
      ">
      <v-toolbar class="toolbar px-5" color="background">
        <v-toolbar-title>
          <img width="15px" class="mr-1" :src="KitwareLogo" />
          <span class="secondary-text">GeoDatalytics</span>
          <v-menu activator="parent" :open-on-hover="true" :close-on-content-click="false"
            @update:model-value="copied = undefined">
            <v-card class="pa-3" style="width: fit-content">
              <v-card-subtitle>
                <a href="https://github.com/OpenGeoscience/geodatalytics" target="_blank" style="text-decoration: none">
                  <v-icon icon="mdi-github" />
                  Source
                </a>
              </v-card-subtitle>
              <v-card-subtitle>
                <v-icon :icon="copied === version ? 'mdi-check' : 'mdi-content-copy'"
                  :color="copied === version ? 'success' : 'primary'" @click="copyToClipboard(version)" />
                Version: {{ version }}
              </v-card-subtitle>
            </v-card>
          </v-menu>
        </v-toolbar-title>
        <v-icon icon="mdi-dock-left" class="ml-5" v-tooltip="'Toggle Sidebar'" @click="toggleSidebar('left')"></v-icon>
      </v-toolbar>
      <ProjectConfig />
      <div class="panel-set">
        <FloatingPanel v-for="panel, index in panelStore.panelArrangement.filter((p) => p.dock == 'left')"
          :id="panel.id" :bottom="index == panelStore.panelArrangement.filter((p) => p.dock == 'left').length - 1">
          <DatasetsPanel v-if="panel.id === 'datasets'" :datasets="projectStore.availableDatasets" />
          <LayersPanel v-else-if="panel.id === 'layers'" />
          <LegendPanel v-else-if="panel.id === 'legend'" />
          <ChartsPanel v-else-if="panel.id === 'charts'" />
          <NetworksPanel v-else-if="panel.id === 'networks'" />
          <AnalyticsPanel v-else-if="panel.id === 'analytics'" />
        </FloatingPanel>
      </div>
    </v-navigation-drawer>

    <v-navigation-drawer floating width="300" location="right" color="background" :class="appStore.openSidebars.includes('right')
      ? 'sidebar right'
      : 'sidebar right closed'
      ">
      <v-toolbar :class="appStore.openSidebars.includes('right') ? 'toolbar px-5' : 'toolbar px-5 right'
        " color="background">
        <v-icon icon="mdi-dock-right" class="mr-5" v-tooltip="'Toggle Sidebar'"
          @click="toggleSidebar('right')"></v-icon>
        <div v-if="appStore.currentUser">
          {{ appStore.currentUser.first_name }}

          <v-menu :close-on-content-click="false">
            <template v-slot:activator="{ props }">
              <v-icon v-bind="props" icon="mdi-cog" class="px-3"></v-icon>
            </template>
            <v-list>
              <v-list-item density="compact" @click="logout">
                Logout
                <template v-slot:append>
                  <v-icon icon="mdi-logout"></v-icon>
                </template>
              </v-list-item>
              <v-list-item density="compact">
                Dark Mode
                <template v-slot:append>
                  <v-switch v-model="darkMode" color="primary" class="ml-5" hide-details></v-switch>
                </template>
              </v-list-item>
            </v-list>
          </v-menu>
        </div>
      </v-toolbar>
      <div :style="{ height: '30px', 'text-align': 'right' }">
        <v-menu :close-on-content-click="false">
          <template v-slot:activator="{ props }">
            <v-icon v-bind="props" icon="mdi-menu" class="mr-3 mt-1" v-tooltip="'Panel Visibility'"></v-icon>
          </template>
          <v-list :items="panelStore.panelArrangement.filter((p) => p.closeable)" item-title="label" item-value="id"
            selectable :selected="panelStore.panelArrangement.filter((p) => p.visible)"
            @click:select="(item) => togglePanelVisibility(item.id as string)" select-strategy="leaf" return-object>
            <template v-slot:prepend="{ item, isSelected }">
              <v-list-item-action start>
                <v-checkbox-btn :model-value="isSelected" @change="togglePanelVisibility(item.id)"></v-checkbox-btn>
              </v-list-item-action>
            </template>
          </v-list>
        </v-menu>
      </div>
      <div class="panel-set">
        <FloatingPanel v-for="panel, index in panelStore.panelArrangement.filter((p) => p.dock == 'right')"
          :id="panel.id" :bottom="index == panelStore.panelArrangement.filter((p) => p.dock == 'right').length - 1">
          <DatasetsPanel v-if="panel.id === 'datasets'" :datasets="projectStore.availableDatasets" />
          <LayersPanel v-else-if="panel.id === 'layers'" />
          <LegendPanel v-else-if="panel.id === 'legend'" />
          <ChartsPanel v-else-if="panel.id === 'charts'" />
          <NetworksPanel v-else-if="panel.id === 'networks'" />
          <AnalyticsPanel v-else-if="panel.id === 'analytics'" />
        </FloatingPanel>
      </div>
    </v-navigation-drawer>
  </div>
</template>

<style>
.sidebar {
  margin: 10px;
  border-radius: 10px;
  width: 350px !important;
  max-height: calc(100% - 20px);
}

.sidebar>.v-navigation-drawer__content {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.sidebar.closed {
  visibility: hidden;
  transition: max-height 0.15s ease-out;
}

.toolbar {
  visibility: visible;
  border-radius: 10px 10px 0px 0px !important;
  border-bottom: 1px solid rgb(var(--v-theme-border)) !important;
}

.toolbar>.v-toolbar__content {
  display: flex;
  height: 50px !important;
  justify-content: space-between;
}

.sidebar.closed .toolbar {
  border-radius: 10px !important;
  width: fit-content !important;
}

.sidebar.closed>.v-navigation-drawer__content>.toolbar>.v-toolbar__content {
  height: 3rem !important;
}

.right {
  position: absolute !important;
  right: 0;
}

.v-toolbar__content {
  height: 4rem !important;
}

.v-toolbar__content>.v-toolbar-title {
  margin-inline-start: 0px !important;
}

.panel-set {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  max-height: calc(100% - 175px);
}

.right .panel-set {
  max-height: calc(100% - 100px);
}

.v-icon {
  color: rgb(var(--v-theme-secondary-text)) !important;
}

.v-btn.bg-primary .v-icon {
  color: rgb(var(--v-theme-button-text)) !important;
}

.v-text-field {
  background-color: rgb(var(--v-theme-background))
}
</style>

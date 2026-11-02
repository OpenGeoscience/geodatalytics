<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { useAppStore, usePanelStore, useProjectStore } from "@/store";
import { useMapCompareStore } from "@/store/compare";
const appStore = useAppStore();
const panelStore = usePanelStore();
const projectStore = useProjectStore();
const compareStore = useMapCompareStore();

const props = defineProps<{
  id: string;
}>();

const panel = computed(() => panelStore.getPanel(props.id));

const element = ref();

function togglePanelCollapsed() {
  if (panel.value) {
    panelStore.updatePanel({
      id: props.id,
      collapsed: !panel.value.collapsed,
    });
  }
}

function closePanel() {
  if (panel.value) {
    panelStore.updatePanel({
      id: props.id,
      visible: false,
    });
  }
}

function updatePanelElement() {
  panelStore.updatePanel({
    id: props.id,
    element: element.value,
  });
}

onMounted(updatePanelElement);
</script>

<template>
  <div
    v-if="panel && panel.visible"
    class="panel-container"
    :style="{
      height: panel.collapsed ? '50px' : '100%',
      flex: panel.collapsed ? 'unset' : 1,
    }"
  >
    <div ref="element" class="panel">
      <v-card class="fill-height">
        <div class="panel-title">
          <v-card-text class="pa-3" style="font-size: 18px">{{
            panel.label
          }}</v-card-text>
          <div class="mr-3">
            <v-icon
              v-if="
                panel.id === 'datasets' &&
                projectStore.currentProject &&
                appStore.authenticated
              "
              v-tooltip="'Add Dataset'"
              icon="mdi-plus"
              color="primary"
              class="pointer"
              @mousedown="projectStore.projectConfigMode = 'existing'"
            />
            <v-menu
              v-if="
                panel.id === 'layers' &&
                projectStore.currentProject &&
                compareStore.isComparing
              "
              :open-on-hover="true"
              location="bottom"
              :close-on-content-click="true"
            >
              <template #activator="{ props: menuProps }">
                <div
                  v-bind="menuProps"
                  style="position: relative; display: inline-block"
                >
                  <v-icon
                    v-tooltip="'Compare Layers'"
                    icon="mdi-compare"
                    color="primary"
                    @click="
                      compareStore.isComparing = !compareStore.isComparing
                    "
                  />
                  <v-icon
                    :icon="
                      compareStore.orientation === 'vertical'
                        ? 'mdi-arrow-split-vertical'
                        : 'mdi-arrow-split-horizontal'
                    "
                    size="small"
                    style="
                      position: absolute;
                      bottom: -10px;
                      right: -10px;
                      background-color: rgb(var(--v-theme-background));
                      border-radius: 50%;
                      padding: 1px;
                    "
                  />
                </div>
              </template>
              <v-list>
                <v-list-item
                  :prepend-icon="'mdi-arrow-split-horizontal'"
                  title="Horizontal"
                  :active="compareStore.orientation === 'horizontal'"
                  @click="compareStore.setOrientation('horizontal')"
                />
                <v-list-item
                  :prepend-icon="'mdi-arrow-split-vertical'"
                  title="Vertical"
                  :active="compareStore.orientation === 'vertical'"
                  @click="compareStore.setOrientation('vertical')"
                />
              </v-list>
            </v-menu>
            <v-icon
              v-else-if="panel.id === 'layers' && projectStore.currentProject"
              v-tooltip="'Compare Layers'"
              icon="mdi-compare"
              :color="compareStore.isComparing ? 'primary' : 'secondary-text'"
              @click="compareStore.isComparing = !compareStore.isComparing"
            />

            <v-icon
              v-tooltip="panel.collapsed ? 'Expand' : 'Collapse'"
              :icon="panel.collapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'"
              class="pointer"
              @mousedown="togglePanelCollapsed"
            ></v-icon>
            <v-icon
              v-if="panel.closeable"
              v-tooltip="'Close Panel'"
              icon="mdi-close"
              class="pointer"
              @mousedown="closePanel"
            ></v-icon>
          </div>
        </div>
        <v-card-text v-if="!panel.collapsed" class="pa-2 panel-content">
          <slot></slot>
        </v-card-text>
      </v-card>
    </div>
  </div>
</template>

<style>
.panel-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  margin-bottom: 10px;
}
.panel {
  position: relative;
  margin: 0px 6px;
  flex: 1;
  min-height: 50px;
  height: 100%;
  overflow: auto;
  border: 1px solid rgb(var(--v-theme-border));
  border-radius: 10px;
}
.panel.closed {
  flex: 0;
}
.panel-title {
  display: flex;
  align-items: center;
  cursor: move;
  user-select: none;
}
.panel-border {
  position: absolute;
  user-select: none;
  z-index: 1;
}
.panel-border-tl,
.panel-border-tr,
.panel-border-bl,
.panel-border-br {
  height: 10px;
  width: 10px;
  z-index: 2;
}
.panel-border-tl {
  top: 0;
  left: 0;
  cursor: nwse-resize;
}
.panel-border-tr {
  top: 0;
  right: 0;
  cursor: nesw-resize;
}
.panel-border-bl {
  bottom: 0;
  left: 0;
  cursor: nesw-resize;
}
.panel-border-br {
  bottom: 0;
  right: 0;
  cursor: nwse-resize;
}
.panel-border-tm,
.panel-border-bm {
  height: 10px;
  width: 100%;
  cursor: ns-resize;
}
.panel-border-tm {
  top: 0;
}
.panel-border-bm {
  bottom: 0;
}
.panel-border-ml,
.panel-border-mr {
  height: 100%;
  width: 10px;
  cursor: ew-resize;
}
.panel-border-ml {
  left: 0;
}
.panel-border-mr {
  right: 0;
}
.panel-content {
  overflow: auto;
  height: calc(100% - 12px);
}
.pointer {
  cursor: pointer;
}
.draggable-divider {
  display: flex;
  align-items: center;
  cursor: n-resize;
  height: 5px;
}
.draggable-corner {
  bottom: 5px;
  cursor: nw-resize;
}
.panel-content-outer {
  height: 100%;
}
.panel-content-outer.with-search {
  height: calc(100% - 40px);
}
.panel-content-inner {
  padding: 0px !important;
  overflow: auto !important;
  height: calc(100% - 45px);
  background-color: rgb(var(--v-theme-background)) !important;
  border: 1px solid rgb(var(--v-theme-border));
  box-shadow: none;
}
.help-text {
  color: rgb(var(--v-theme-helper-text));
}
.primary-button {
  vertical-align: inherit;
  background-color: rgb(var(--v-theme-primary)) !important;
  color: rgb(var(--v-theme-button-text)) !important;
  border-radius: 5px;
}
.secondary-button {
  vertical-align: inherit;
  background-color: rgb(var(--v-theme-secondary)) !important;
  color: rgb(var(--v-theme-primary)) !important;
  border-radius: 5px;
}
</style>

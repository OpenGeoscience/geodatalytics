<script setup lang="ts">
import { computed, ref } from "vue";

import { usePanelStore, useProjectStore } from "@/store";
import { useMapCompareStore } from "@/store/compare";
const panelStore = usePanelStore();
const projectStore = useProjectStore();
const compareStore = useMapCompareStore();

const props = defineProps<{
  id: string;
  bottom?: boolean;
}>();

const startDrag = panelStore.startDrag;
const panel = computed(() =>
  panelStore.panelArrangement.find((p) => p.id === props.id),
);

const element = ref();

function getPanelContainerClass() {
  let classString = "";
  if (panel.value?.collapsed) classString += " closed";
  if (!panel.value?.position) classString += "panel-container";
  return classString;
}

function getPanelContainerStyle() {
  const styleObj: Record<string, string> = {};
  styleObj.order = panel.value?.order.toString() || "0";
  if (!panel.value?.position) {
    if (panel.value?.height && !panel.value.collapsed) {
      styleObj.height = panel.value?.height + "px";
      styleObj.flex = "unset";
    }
  }
  return styleObj;
}

function getPanelStyle() {
  const styleObj: Record<string, string> = {};
  if (panel.value?.position) {
    styleObj["z-index"] = "2"; // above vuetify navigation drawer
    styleObj.visibility = "visible"; // prevent hiding when sidebar closes
    styleObj.position = "absolute";
    styleObj.top = panel.value.position.y + "px";
    styleObj.left = panel.value.position.x + "px";
    if (panel.value?.width) {
      styleObj.width = panel.value?.width + "px";
    }
  }
  if (panel.value?.height && !panel.value.collapsed) {
    styleObj.height = panel.value?.height + "px";
  }
  return styleObj;
}

function togglePanelCollapsed() {
  if (panel.value) {
    panel.value.collapsed = !panel.value.collapsed;
    panelUpdated();
  }
}

function closePanel() {
  if (panel.value) {
    panel.value.visible = false;
    panelUpdated();
  }
}

function updatePanelElement() {
  if (panel.value) {
    panel.value.element = element.value;
    panelUpdated();
  }
}

function panelUpdated() {
  if (panel.value) {
    panelStore.panelArrangement = [
      panel.value,
      ...panelStore.panelArrangement.filter((p) => p.id !== props.id),
    ];
  }
}
</script>

<template>
  <div
    v-if="panel && panel.visible"
    :class="getPanelContainerClass()"
    :style="getPanelContainerStyle()"
  >
    <div ref="element" class="panel" :style="getPanelStyle()">
      <v-card class="fill-height">
        <div style="display: flex; align-items: center">
          <v-card-text class="pa-3" style="font-size: 18px">{{
            panel.label
          }}</v-card-text>
          <div class="mr-3">
            <v-icon
              v-if="panel.id === 'datasets' && projectStore.currentProject"
              v-tooltip="'Add Dataset'"
              icon="mdi-plus"
              color="primary"
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
              :color="compareStore.isComparing ? 'primary' : ''"
              @click="compareStore.isComparing = !compareStore.isComparing"
            />

            <v-icon
              v-tooltip="panel.collapsed ? 'Expand' : 'Collapse'"
              :icon="panel.collapsed ? 'mdi-chevron-down' : 'mdi-chevron-up'"
              @mousedown="togglePanelCollapsed"
            ></v-icon>
            <v-icon
              icon="mdi-drag"
              class="draggable"
              @mousedown="
                (e: any) => {
                  updatePanelElement();
                  startDrag(e, panel, ['position']);
                }
              "
            ></v-icon>
            <v-icon
              v-if="panel.closeable"
              v-tooltip="'Close Panel'"
              icon="mdi-close"
              @mousedown="closePanel"
            ></v-icon>
          </div>
        </div>
        <v-card-text v-if="!panel.collapsed" class="pa-2 panel-content">
          <slot></slot>
          <v-icon
            v-if="panel.position"
            icon="mdi-resize-bottom-right"
            class="right mr-2 draggable-corner"
            @mousedown="
              (e: any) => {
                updatePanelElement();
                startDrag(e, panel, ['width', 'height']);
              }
            "
          ></v-icon>
        </v-card-text>
      </v-card>
    </div>
    <div
      v-if="!panel.position && !props.bottom"
      class="draggable-divider"
      @mousedown="
        (e) => {
          updatePanelElement();
          startDrag(e, panel, ['height']);
        }
      "
    >
      <v-divider></v-divider>
      <v-icon
        icon="mdi-drag-horizontal-variant"
        size="x-small"
        class="mx-2"
      ></v-icon>
      <v-divider></v-divider>
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
}
.panel {
  position: relative;
  margin: 6px;
  border-radius: 10px;
  flex: 1;
  min-height: 50px;
  overflow: auto;
}
.panel.closed {
  flex: 0;
}
.panel-content {
  overflow: auto;
  height: calc(100% - 12px);
}
.draggable {
  cursor: move;
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

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import type { Ref } from "vue";
import DatasetSelect from "@/components/projects/DatasetSelect.vue";
import DatasetUpload from "@/components/projects/DatasetUpload.vue";
import AccessControl from "@/components/projects/AccessControl.vue";
import {
  getProjectDatasets,
  createProject,
  deleteProject,
  patchProject,
} from "@/api/rest";
import type { Project, Dataset } from "@/types";

import { useMapStore, useProjectStore, useAppStore } from "@/store";
const projectStore = useProjectStore();
const mapStore = useMapStore();
const appStore = useAppStore();

const currentTab = ref();
const searchText = ref<string | undefined>();
const filteredProjects = computed(() => {
  return projectStore.availableProjects.filter((proj) => {
    return (
      !searchText.value ||
      proj.name.toLowerCase().includes(searchText.value.toLowerCase())
    );
  });
});
const selectedProject: Ref<Project | undefined> = ref();
const projDatasets: Ref<Dataset[] | undefined> = ref();

const saving = ref<"waiting" | "done">();
const savingId = ref<number | undefined>();
const newProjectName = ref();
const projectToEdit: Ref<Project | undefined> = ref();
const projectToDelete: Ref<Project | undefined> = ref();
const editMode = computed(() => {
  if (selectedProject.value) {
    return ["owner", "collaborator"].includes(
      projectStore.permissions[selectedProject.value.id],
    );
  }
  return false;
});
const deleteAllowed = computed(() => {
  if (selectedProject.value) {
    return projectStore.permissions[selectedProject.value.id] === "owner";
  }
  return false;
});

function openProjectConfig(create = false) {
  if (appStore.authenticated)
    projectStore.projectConfigMode = create ? "new" : "existing";
}

function create() {
  if (!appStore.authenticated) return;
  const { center, zoom } = mapStore.getCurrentMapPosition();
  createProject(newProjectName.value, center, zoom).then((project) => {
    newProjectName.value = undefined;
    projectStore.projectConfigMode = "existing";
    projectStore.loadProjects();
    selectProject(project);
  });
}

function del() {
  if (projectToDelete.value && deleteAllowed.value) {
    deleteProject(projectToDelete.value.id).then(() => {
      projectStore.loadProjects();
      if (selectedProject.value?.id === projectToDelete.value?.id) {
        selectedProject.value = undefined;
      }
      projectToDelete.value = undefined;
    });
  }
}

function saveProjectName() {
  if (!editMode.value) return;
  if (!newProjectName.value) {
    projectToEdit.value = undefined;
    return;
  }
  saving.value = "waiting";
  if (projectToEdit.value) {
    patchProject(projectToEdit.value.id, {
      name: newProjectName.value,
    }).then(() => {
      projectToEdit.value = undefined;
      newProjectName.value = undefined;
      saving.value = "done";
      projectStore.loadProjects();
      setTimeout(() => {
        saving.value = undefined;
      }, 2000);
    });
  }
}

function saveProjectMapLocation(project: Project | undefined) {
  if (
    !projectStore.currentProject ||
    !["owner", "collaborator"].includes(
      projectStore.permissions[projectStore.currentProject.id],
    )
  )
    return;
  if (project) {
    saving.value = "waiting";
    const { center, zoom } = mapStore.getCurrentMapPosition();
    patchProject(project.id, {
      default_map_center: center,
      default_map_zoom: zoom,
    }).then((project) => {
      projectStore.availableProjects = projectStore.availableProjects.map(
        (p) => {
          if (p.id === project.id) {
            p.default_map_center = project.default_map_center;
            p.default_map_zoom = project.default_map_zoom;
          }
          return p;
        },
      );
      if (projectStore.currentProject) {
        projectStore.currentProject.default_map_center =
          project.default_map_center;
        projectStore.currentProject.default_map_zoom = project.default_map_zoom;
      }
      mapStore.resetMapPosition(project);
      saving.value = "done";
      setTimeout(() => {
        saving.value = undefined;
      }, 2000);
    });
  }
}

function selectProject(project: Project) {
  if (selectedProject.value?.id !== project.id) {
    selectedProject.value = project;
    projectStore.refreshAllDatasets();
    refreshProjectDatasets(null);
  }
}

function loadSelectedProject() {
  projectStore.currentProject = selectedProject.value;
  projectStore.projectConfigMode = undefined;
}

function addDatasetToProject(dataset: Dataset) {
  savingId.value = dataset.id;
  const projDatasetIds = projDatasets.value?.map((d) => d.id);
  if (!projDatasetIds?.includes(dataset.id)) {
    projDatasetIds?.push(dataset.id);
  }
  if (projDatasetIds) {
    saveDatasetsToProject(projDatasetIds);
  }
}

function removeDatasetFromProject(dataset: Dataset) {
  savingId.value = dataset.id;
  let projDatasetIds = projDatasets.value?.map((d) => d.id);
  if (projDatasetIds?.includes(dataset.id)) {
    projDatasetIds = projDatasetIds.filter((id) => id !== dataset.id);
  }
  if (projDatasetIds) {
    saveDatasetsToProject(projDatasetIds);
  }
}

function saveDatasetsToProject(ids: number[]) {
  if (!editMode.value) return;
  if (selectedProject.value) {
    patchProject(selectedProject.value.id, {
      datasets: ids,
    }).then(() => {
      refreshProjectDatasets(() => {
        savingId.value = undefined;
      });
    });
  }
}

function updateSelectedProject(newProjectData: Project) {
  projectStore.loadProjects();
  selectedProject.value = newProjectData;
}

function refreshProjectDatasets(callback: (() => void) | null) {
  if (selectedProject.value) {
    getProjectDatasets(selectedProject.value.id).then(async (datasets) => {
      projDatasets.value = datasets;
      if (callback) callback();
    });
  }
}

function resetProjectEdit() {
  projectStore.projectConfigMode = "existing";
  newProjectName.value = undefined;
  projectToDelete.value = undefined;
  projectToEdit.value = undefined;
}

function handleEditFocus(focused: boolean) {
  if (!focused && !newProjectName.value) {
    resetProjectEdit();
  }
}

function datasetUploaded() {
  projectStore.refreshAllDatasets();
  refreshProjectDatasets(null);
}

onMounted(() => {
  window.addEventListener("keydown", (e) => {
    if (e.key == "Escape" && projectStore.projectConfigMode) {
      projectStore.projectConfigMode = undefined;
    }
  });
});

watch(selectedProject, resetProjectEdit);

watch(
  () => projectStore.projectConfigMode,
  () => {
    if (projectStore.currentProject && !projectStore.projectConfigMode) {
      projectStore.currentProject = projectStore.availableProjects.find(
        (p) => p.id === projectStore.currentProject?.id,
      ); // trigger project reload
    }
  },
);
</script>

<template>
  <div>
    <div class="project-row">
      <v-select
        v-model="projectStore.currentProject"
        placeholder="Select a Project"
        no-data-text="No available projects."
        :items="projectStore.availableProjects"
        :autofocus="!projectStore.currentProject"
        item-title="name"
        item-value="id"
        density="compact"
        variant="outlined"
        hide-details
        return-object
      ></v-select>
      <v-btn
        v-if="appStore.authenticated"
        color="primary"
        variant="flat"
        style="min-width: 30px; height: 30px"
        class="px-0 ml-2"
        @click="() => openProjectConfig(true)"
      >
        <v-icon icon="mdi-plus" size="large" />
        <v-tooltip activator="parent" location="end">
          Create New Project
        </v-tooltip>
      </v-btn>
      <v-btn
        v-if="appStore.authenticated"
        color="secondary"
        variant="flat"
        style="min-width: 30px; height: 30px"
        class="px-0 ml-2"
        @click="() => openProjectConfig(false)"
      >
        <v-icon icon="mdi-cog" size="large" color="primary" />
        <v-tooltip activator="parent" location="end">
          Configure Projects
        </v-tooltip>
      </v-btn>
    </div>
    <v-card
      v-if="
        !projectStore.loadingProjects &&
        projectStore.availableProjects.length === 0
      "
      class="tutorial-popup"
    >
      <v-card-text v-if="appStore.authenticated">
        To get started, create a project and add datasets to it.
      </v-card-text>
      <v-card-text v-else>
        There are currently no projects that allow unauthenticated access.
      </v-card-text>
    </v-card>
    <div v-if="projectStore.currentProject" class="project-row text-body-small">
      <v-btn
        size="sm"
        flat
        variant="text"
        prepend-icon="mdi-map-marker"
        class="px-0"
        color="primary"
        @click="() => mapStore.resetMapPosition(projectStore.currentProject)"
      >
        Project default map position
      </v-btn>
      <v-btn
        v-if="
          ['owner', 'collaborator'].includes(
            projectStore.permissions[projectStore.currentProject?.id],
          )
        "
        size="sm"
        class="px-1"
        flat
        @click="() => saveProjectMapLocation(projectStore.currentProject)"
      >
        Save current position
        <v-icon
          v-if="saving === 'done'"
          icon="mdi-check"
          color="green"
          class="ml-1"
        />
        <v-progress-circular
          v-else-if="saving"
          size="15"
          indeterminate
          class="ml-1"
        />
      </v-btn>
    </div>
    <v-card
      v-if="appStore.authenticated && projectStore.projectConfigMode"
      flat
      class="config"
      color="background"
    >
      <v-card-title class="pa-3">
        Projects Configuration
        <v-btn
          class="close-button transparent"
          variant="flat"
          icon
          @click="projectStore.projectConfigMode = undefined"
        >
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-card-text class="d-flex pa-0" style="height: 100%">
        <div class="sidebar">
          <v-card
            flat
            class="position-sticky top-0 pa-3"
            style="z-index: 2"
            color="background"
          >
            <v-text-field
              v-model="searchText"
              label="Search Projects"
              variant="outlined"
              density="compact"
              append-inner-icon="mdi-magnify"
              hide-details
            />
          </v-card>
          <v-list class="transparent" color="primary" selectable>
            <v-list-item
              v-for="project in filteredProjects"
              :key="project.id"
              :title="project.name"
              :active="project.id === selectedProject?.id"
              @click="() => selectProject(project)"
            >
              <template #title="{ title }">
                <v-text-field
                  v-if="projectToEdit?.id === project.id"
                  v-model="newProjectName"
                  :placeholder="project.name"
                  label="Project Name"
                  density="compact"
                  hide-details
                  autofocus
                  @keydown.stop
                  @keydown.esc="resetProjectEdit"
                  @keydown.enter="saveProjectName"
                  @update:focused="handleEditFocus"
                />
                <span v-else>{{ title }}</span>
              </template>
              <template #append>
                <div
                  v-if="
                    ['owner', 'collaborator'].includes(
                      projectStore.permissions[project.id],
                    )
                  "
                >
                  <v-icon
                    v-if="!projectToEdit && !projectToDelete"
                    icon="mdi-pencil"
                    @click.stop="projectToEdit = project"
                  />
                  <v-btn
                    v-else-if="projectToEdit?.id === project.id"
                    color="primary"
                    variant="flat"
                    style="min-width: 40px; min-height: 40px"
                    :disabled="!newProjectName"
                    @click="saveProjectName"
                  >
                    <v-icon icon="mdi-content-save" />
                  </v-btn>
                </div>
                <div
                  v-if="
                    ['owner'].includes(projectStore.permissions[project.id])
                  "
                >
                  <v-icon
                    v-if="!projectToEdit && !projectToDelete"
                    icon="mdi-trash-can"
                    @click.stop="projectToDelete = project"
                  />
                </div>
              </template>
            </v-list-item>
          </v-list>
          <div
            v-if="projectStore.projectConfigMode === 'new'"
            class="pa-2 d-flex"
          >
            <v-text-field
              v-model="newProjectName"
              label="Project Name"
              density="compact"
              autofocus
              @keydown.enter="create"
              @keydown.esc="resetProjectEdit"
              @update:focused="handleEditFocus"
            />
            <v-btn
              color="primary"
              variant="flat"
              style="min-width: 40px; min-height: 40px"
              :disabled="!newProjectName"
              @click="create"
            >
              <v-icon icon="mdi-arrow-right" />
            </v-btn>
          </div>
          <v-btn
            v-else
            variant="tonal"
            width="100%"
            @click="projectStore.projectConfigMode = 'new'"
            >+ New</v-btn
          >
          <v-btn
            v-if="selectedProject"
            class="options"
            color="primary"
            @click="loadSelectedProject"
          >
            Load Project
          </v-btn>
        </div>
        <div v-if="selectedProject" class="tab-content">
          <v-alert v-if="selectedProject.allow_unauthenticated" class="mr-16">
            <v-icon icon="mdi-alert-box-outline" color="error"></v-icon>
            This project allows unauthenticated view access.
          </v-alert>
          <v-tabs v-model="currentTab" color="primary">
            <v-tab value="datasets">Dataset Selection</v-tab>
            <v-tab value="users">Access Control</v-tab>
          </v-tabs>
          <div v-if="currentTab === 'datasets'">
            <v-progress-linear
              v-if="
                projectStore.loadingDatasets ||
                projectStore.allDatasets === undefined
              "
              indeterminate
            ></v-progress-linear>
            <div v-else class="py-3 px-6 d-flex">
              <div style="width: 45%">
                <v-card-text>Project Datasets</v-card-text>
                <div class="dataset-card">
                  <DatasetSelect
                    :datasets="projDatasets"
                    :saving-id="savingId"
                    :show-delete="false"
                    button-icon="mdi-close"
                    :edit-mode="editMode"
                    @button-click="removeDatasetFromProject"
                    @on-delete="refreshProjectDatasets"
                  />
                </div>
              </div>
              <v-divider class="mx-5" vertical></v-divider>
              <div v-if="editMode" style="width: 45%">
                <div class="d-flex">
                  <v-card-text>All Datasets</v-card-text>
                  <DatasetUpload
                    :all-datasets="projectStore.allDatasets"
                    :edit-mode="editMode"
                    @add-to-current-project="addDatasetToProject"
                    @uploaded="datasetUploaded"
                  />
                </div>
                <div class="dataset-card">
                  <DatasetSelect
                    :datasets="projectStore.allDatasets"
                    :saving-id="savingId"
                    :added-ids="projDatasets?.map((d) => d.id)"
                    :show-delete="true"
                    button-icon="mdi-plus"
                    :edit-mode="editMode"
                    @button-click="addDatasetToProject"
                    @on-delete="refreshProjectDatasets"
                  />
                </div>
              </div>
            </div>
          </div>
          <div v-if="currentTab === 'users'" class="py-3 px-6">
            <AccessControl
              :project="selectedProject"
              @update-selected-project="updateSelectedProject"
            />
          </div>
        </div>
      </v-card-text>
      <v-dialog :model-value="!!projectToDelete" width="300">
        <v-card v-if="projectToDelete">
          <v-card-title class="pa-3">
            Delete project
            <v-btn
              class="close-button transparent"
              variant="flat"
              icon
              @click="projectToDelete = undefined"
            >
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-card-title>
          <v-card-text>
            Are you sure you want to delete "{{ projectToDelete.name }}"?
          </v-card-text>
          <v-card-actions class="d-flex" style="justify-content: space-evenly">
            <v-btn color="red" :disabled="!deleteAllowed" @click="del"
              >Delete</v-btn
            >
            <v-btn
              color="primary"
              variant="tonal"
              @click="projectToDelete = undefined"
            >
              Cancel
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </v-card>
  </div>
</template>

<style>
.project-row {
  display: flex;
  margin: 4px 8px;
  align-items: center;
  justify-content: space-between;
}
.item-counts {
  display: flex;
  align-items: baseline;
  column-gap: 4px;
}
.tutorial-popup {
  position: absolute !important;
  z-index: 1 !important;
  left: 275px;
  top: 110px;
  width: 250px;
  background-color: rgba(1, 1, 1, 0.8) !important;
  color: white !important;
}
.config {
  top: 0px;
  margin: 0px;
  height: calc(100vh - 20px);
  width: calc(100vw - 20px);
  position: absolute !important;
  z-index: 10001 !important;
}
.transparent {
  background-color: transparent !important;
}
.close-button {
  position: absolute !important;
  top: 5px;
  right: 5px;
}
.sidebar {
  width: 300px;
  height: 100%;
}
.options {
  position: absolute !important;
  bottom: 0px;
  left: 0px;
  width: inherit;
}
.tab-content {
  width: calc(100% - 300px);
  height: inherit;
}
.dataset-card {
  max-height: calc(100vh - 300px);
  overflow: auto !important;
  position: relative;
}
</style>

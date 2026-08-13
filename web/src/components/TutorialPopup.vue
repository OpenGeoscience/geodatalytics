<script setup lang="ts">
import { useAppStore, useTutorialStore, useProjectStore } from "@/store";

const appStore = useAppStore();
const tutorialStore = useTutorialStore();
const projectStore = useProjectStore();
</script>

<template>
  <div>
    <v-dialog
      v-if="!appStore.authenticated"
      v-model="tutorialStore.showWelcomeMessage"
      width="400"
    >
      <v-card>
        <v-card-title class="pa-3"> Welcome to GeoDatalytics </v-card-title>
        <v-card-text>
          <div>
            While not logged in, you can use a limited version of the
            application to explore the available features.
          </div>
          <div class="py-2">
            You can view any projects that allow unauthenticated access, but you
            cannot make changes or create new objects.
          </div>
          <div>
            To access the full version of the application, you must log in.
          </div>
        </v-card-text>
        <v-card-actions
          class="px-4 d-flex"
          style="justify-content: space-between"
        >
          <v-btn
            color="primary"
            @click="
              tutorialStore.showTutorialStep = 1;
              tutorialStore.showWelcomeMessage = false;
            "
            >Show me a tutorial</v-btn
          >
          <v-btn
            color="primary"
            @click="
              tutorialStore.showWelcomeMessage = false;
              projectStore.loadViewStateFromURL();
            "
          >
            Explore without tutorial
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <div
      v-if="tutorialStore.currentTutorialStep"
      class="tutorial-message"
      :style="{
        top: tutorialStore.currentTutorialStep.position[0],
        left: tutorialStore.currentTutorialStep.position[1],
      }"
    >
      <div class="d-flex" style="width: 100%; justify-content: space-between">
        Step {{ tutorialStore.showTutorialStep }} of
        {{ tutorialStore.numTutorialSteps }}
        <v-btn
          v-if="tutorialStore.showTutorialStep < tutorialStore.numTutorialSteps"
          variant="text"
          icon="mdi-arrow-right"
          size="sm"
          @click="tutorialStore.tutorialProceed"
        ></v-btn>
      </div>
      {{ tutorialStore.currentTutorialStep?.message }}
      <v-btn
        v-if="tutorialStore.showTutorialStep == tutorialStore.numTutorialSteps"
        color="primary"
        @click="
          tutorialStore.showTutorialStep = 0;
          projectStore.loadViewStateFromURL();
        "
      >
        Exit Tutorial
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { oauthClient } from "@/api/auth";
import KitwareLogo from "@/assets/Kitware.png";
import SplashBG from "@/assets/splash_bg.png";

const login = () => {
  oauthClient.redirectToLogin();
};
</script>

<template>
  <v-img :src="SplashBG" width="100vw" height="100vh" cover></v-img>
  <div class="splash-page-content">
    <div class="d-flex" style="justify-content: space-between; flex-wrap: wrap">
      <div class="d-flex" style="align-items: center">
        <v-img width="20px" class="mr-1" :src="KitwareLogo"></v-img>
        <span class="mr-4 bold" style="font-size: 1.2rem">GeoDatalytics</span>
        <span
          class="pl-4"
          style="border-left: 1px solid rgb(var(--v-theme-on-background))"
          >by Kitware</span
        >
      </div>
      <div class="d-flex">
        <v-btn
          variant="text"
          color="primary"
          prepend-icon="mdi-github"
          target="_blank"
          href="https://github.com/OpenGeoscience/geodatalytics"
        >
          View on Github
        </v-btn>
        <v-btn
          variant="text"
          color="primary"
          prepend-icon="mdi-email-outline"
          target="_blank"
          href="https://www.kitware.com/contact/"
        >
          Contact Kitware
        </v-btn>
      </div>
    </div>
    <div style="text-align: center; align-content: center; flex: 1">
      <div class="text-primary bold" style="font-size: 1.2rem">
        Open-source Urban Analytics Platform
      </div>
      <div class="mt-6" style="font-weight: 800; font-size: 3rem">
        Model urban systems.
      </div>
      <div class="mb-6" style="font-weight: 800; font-size: 3rem">
        Gain new insights.
      </div>
      <div>
        GeoDatalytics bridges the gap between urban datasets, AI modeling, and
        interactive visual analytics.
      </div>
      <div>
        Ingest, explore, simulate, and visualize complex geospatial data all in
        one platform.
      </div>
      <div class="pt-12">
        <v-btn color="primary" prepend-icon="mdi-login" @click="login">
          Log in to GeoDatalytics
        </v-btn>
      </div>
    </div>
    <div>
      <v-expansion-panels
        variant="accordion"
        bg-color="background"
        gap="2px"
        model-value="0"
      >
        <v-expansion-panel>
          <v-expansion-panel-title class="bold">
            What can I do with GeoDatalytics?
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="grid-container">
              <div>
                <v-icon
                  icon="mdi-city-variant"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Scenario-based analytics</div>
                  Explore what-if scenarios of cascading failures across
                  interconnected urban systems.
                </div>
              </div>
              <div>
                <v-icon
                  icon="mdi-auto-mode"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">AI & simulation workflows</div>
                  Run pretrained models on geospatial and network data to
                  generate actionable insights.
                </div>
              </div>
              <div>
                <v-icon
                  icon="mdi-map-search"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Interactive visualization</div>
                  Explore multiscale results through the interactive map with
                  custom layer styling and side-by-side comparison.
                </div>
              </div>
              <div>
                <v-icon
                  icon="mdi-hubspot"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Multisource data integration</div>
                  Ingest vector, raster, and tabular data representing roads,
                  utilities, amenities, satellite imagery, sensor data, etc.
                </div>
              </div>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
        <v-expansion-panel>
          <v-expansion-panel-title class="bold">
            Who is this built for?
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="grid-container">
              <div>
                <v-icon
                  icon="mdi-account-group"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Local Governments</div>
                  Municipalities planning resilient infrastructure
                </div>
              </div>
              <div>
                <v-icon
                  icon="mdi-account-tie-hat"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Urban Planners</div>
                  Analysts assessing infrastructure risk and climate impacts
                </div>
              </div>
              <div>
                <v-icon
                  icon="mdi-account-hard-hat"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Service Providers</div>
                  Utilities and emergency management teams
                </div>
              </div>
              <div>
                <v-icon
                  icon="mdi-account-cog"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Data Scientists</div>
                  AI/ML developers building geospatial models
                </div>
              </div>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
        <v-expansion-panel>
          <v-expansion-panel-title class="bold">
            How do I turn my data into insights?
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="grid-container">
              <div>
                <v-icon
                  icon="mdi-numeric-1"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Create a project</div>
                  Set up a workspace, configure datasets, and assign permissions
                </div>
              </div>
              <div>
                <v-icon
                  icon="mdi-numeric-2"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Ingest your data</div>
                  Upload vector, raster, or tabular datasets which will be
                  converted to standardized formats
                </div>
              </div>
              <div>
                <v-icon
                  icon="mdi-numeric-3"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Run Models & Simulations</div>
                  Run analytics tasks with pretrained AI models or custom
                  simulation logic
                </div>
              </div>
              <div>
                <v-icon
                  icon="mdi-numeric-4"
                  size="large"
                  color="primary"
                  class="bg-secondary pa-4 rounded"
                ></v-icon>
                <div>
                  <div class="bold">Visualize & Share</div>
                  Explore results on the interactive map and share saved views
                  with your team
                </div>
              </div>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </div>
  </div>
</template>

<style scoped>
.splash-page-content {
  width: 100vw;
  height: 100vh;
  display: flex;
  flex-direction: column;
  position: absolute;
  background: linear-gradient(
    to right,
    rgba(var(--v-theme-surface-bright), 0.7) 0%,
    rgba(var(--v-theme-surface-bright), 0.95) 35%,
    rgba(var(--v-theme-surface-bright), 0.95) 65%,
    rgba(var(--v-theme-surface-bright), 0.7) 100%
  );
  padding: 20px 60px;
  overflow-y: auto;
}

.bold {
  font-weight: bold;
}

.grid-container {
  margin: 12px;
  background-color: rgb(var(--v-theme-border));
  display: grid;
  grid-template-columns: repeat(1, 1fr);
  gap: 2px;
}

.grid-container > div {
  background-color: rgb(var(--v-theme-background));
  padding: 12px;
  display: flex;
  gap: 16px;
  align-items: top;
}

@media (min-width: 1000px) {
  .grid-container {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (min-width: 1500px) {
  .grid-container {
    grid-template-columns: repeat(4, 1fr);
  }
}
</style>

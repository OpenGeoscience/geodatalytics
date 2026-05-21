// Plugins
import Vue from "@vitejs/plugin-vue";
import Vuetify, { transformAssetUrls } from "vite-plugin-vuetify";
import { sentryVitePlugin } from "@sentry/vite-plugin";

// Utilities
import { defineConfig } from "vite";
import process from "node:process";
import { fileURLToPath, URL } from "node:url";

import packageJson from "./package.json";

process.env.VITE_APP_VERSION = packageJson.version;

export default defineConfig({
  plugins: [
    Vue({
      template: { transformAssetUrls },
    }),
    Vuetify({
      autoImport: true,
    }),
    sentryVitePlugin({
      org: "kitware-data",
      project: "geodatalytics-client",
      authToken: process.env.SENTRY_AUTH_TOKEN,
      release: {
        // Defined by: https://developers.cloudflare.com/pages/configuration/build-configuration/#environment-variables
        name: process.env.CF_PAGES_COMMIT_SHA,
      },
    }),
  ],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 8080,
    strictPort: true,
  },
  preview: {
    port: 8080,
    strictPort: true,
  },
  build: {
    sourcemap: true,
  },
});

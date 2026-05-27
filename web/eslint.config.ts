import { globalIgnores } from "eslint/config";
import pluginVue from "eslint-plugin-vue";
import {
  defineConfigWithVueTs,
  vueTsConfigs,
} from "@vue/eslint-config-typescript";
import skipFormatting from "eslint-config-prettier/flat";

export default defineConfigWithVueTs(
  {
    name: "app/files-to-lint",
    files: ["**/*.{vue,ts,mts,tsx}"],
  },
  globalIgnores(["**/dist/**", "**/dist-ssr/**", "**/coverage/**"]),
  ...pluginVue.configs["flat/essential"],
  vueTsConfigs.recommended,
  {
    rules: {
      // allowModifiers: Vuetify uses dot notation for column slots (v-slot:item.columnName)
      "vue/valid-v-slot": ["error", { allowModifiers: true }],
      // `any` is used everywhere and will be difficult to eliminate
      "@typescript-eslint/no-explicit-any": "off",
      // Temporary ignores until rules can be fixed
      "vue/require-v-for-key": "off",
      "vue/valid-v-for": "off",
      "vue/return-in-computed-property": "off",
      "vue/no-use-v-if-with-v-for": "off",
    },
  },
  skipFormatting,
);

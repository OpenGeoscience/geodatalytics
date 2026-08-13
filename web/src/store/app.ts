import type { User } from "@/types";
import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";

export const useAppStore = defineStore("app", () => {
  const theme = ref<"dark" | "light">("light");
  const openSidebars = ref<("left" | "right")[]>(["left", "right"]);
  const currentUser = ref<User>();
  const currentError = ref<string>();
  const themeManager = ref();

  const authenticated = computed(() => {
    return currentUser.value?.id !== undefined;
  });

  function setDefaultTheme() {
    const darkThemeMatch =
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches;
    theme.value = darkThemeMatch ? "dark" : "light";
    return theme.value;
  }

  watch(theme, () => {
    if (themeManager.value) {
      themeManager.value.change(theme.value);
    }
  });

  return {
    theme,
    themeManager,
    openSidebars,
    currentUser,
    currentError,
    authenticated,
    setDefaultTheme,
  };
});

<script setup lang="ts">
import type { User } from "@/types";
import { computed } from "vue";

const props = defineProps<{
  user: User | undefined;
}>();
const names = computed(() => {
  return [props.user?.first_name, props.user?.last_name].filter(
    (s) => s?.length,
  ) as string[];
});
const nameLabel = computed(() => {
  return names.value.length ? names.value.join(" ") : "Unnamed User";
});
const initials = computed(() => {
  return names.value.length
    ? names.value.map((name) => name[0]).join("")
    : undefined;
});
</script>

<template>
  <v-list-item v-if="props.user" :subtitle="props.user.username">
    <template #title>
      <span style="text-transform: capitalize">{{ nameLabel }}</span>
    </template>
    <template #prepend>
      <v-btn
        flat
        icon
        color="primary"
        size="small"
        class="mx-3 user-circle"
        :ripple="false"
      >
        <span v-if="initials" style="text-transform: uppercase">
          {{ initials }}
          <v-tooltip activator="parent" location="end">
            {{ nameLabel }}
          </v-tooltip>
        </span>
        <v-icon v-else icon="mdi-account"></v-icon>
      </v-btn>
    </template>
    <template #append>
      <slot name="append"></slot>
    </template>
  </v-list-item>
</template>

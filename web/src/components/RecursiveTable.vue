<script setup lang="ts">
import dayjs from "dayjs";

const props = defineProps<{
  data: any;
}>();

function formatIfDate(key: string, value: string) {
  // Check if key contains a time-related field
  if (/(date|time|create|publish|modified|completed|uploaded)/i.test(key)) {
    const date = dayjs(value);
    return date.isValid() ? date.format("YYYY-MM-DD HH:mm:ss") : value;
  }
  return value;
}
</script>

<template>
  <v-table>
    <tbody v-if="props.data">
      <tr
        v-for="[key, value] in Object.entries(props.data)"
        :key="key"
        style="vertical-align: top"
      >
        <td class="font-weight-bold">{{ key.replaceAll("_", " ") }}</td>
        <td v-if="!value">NULL</td>
        <td
          v-else-if="
            Array.isArray(value) &&
            typeof value.filter((v) => v)[0] === 'object'
          "
        >
          <v-card v-for="item in value" :key="item" class="mb-3">
            <RecursiveTable :data="item" />
          </v-card>
        </td>
        <td v-else-if="Array.isArray(value)">
          {{ value.filter((v) => v).join(", ") }}
        </td>
        <td v-else-if="!Array.isArray(value) && typeof value === 'object'">
          <v-card class="mb-3">
            <RecursiveTable :data="value" />
          </v-card>
        </td>
        <td v-else-if="typeof value === 'string'">
          {{ formatIfDate(key, value) }}
        </td>
        <td v-else>{{ value }}</td>
      </tr>
    </tbody>
  </v-table>
</template>

<style>
.v-expansion-panel-text__wrapper {
  padding: 0px !important;
}
.v-table--density-default {
  --v-table-row-height: 24px !important;
  word-break: keep-all;
}
</style>

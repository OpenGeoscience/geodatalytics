<script setup lang="ts">
import { onMounted, computed, ref } from "vue";
import type { Ref } from "vue";
import type { Project, ProjectPermissions, User } from "@/types";
import { getUsers, updateProjectPermissions } from "@/api/rest";

import { useProjectStore } from "@/store";
import UserProfile from "./UserProfile.vue";
const projectStore = useProjectStore();

const props = defineProps<{
  project: Project;
}>();
const emit = defineEmits(["updateSelectedProject"]);
const allUsers: Ref<User[]> = ref([]);
const showUserSelectDialog: Ref<boolean> = ref(false);
const userSelectDialogMode: Ref<"add" | "transfer"> = ref("add");
const selectedUsers: Ref<User[]> = ref([]);
type PermissionLevel = "follower" | "collaborator";
const permissionLevels: PermissionLevel[] = ["follower", "collaborator"];
const selectedPermissionLevel: Ref<PermissionLevel> = ref("follower");
const userToRemove: Ref<User | undefined> = ref();
const editMode = computed(
  () => projectStore.permissions[props.project.id] === "owner",
);

function savePermissions() {
  if (!editMode.value || props.project.owner.id === undefined) return;
  let owner: number = props.project.owner.id;
  const collaborators = new Set(
    props.project.collaborators.map((u: User) => u.id),
  );
  const followers = new Set(props.project.followers.map((u: User) => u.id));
  if (userToRemove.value) {
    collaborators.delete(userToRemove.value.id);
    followers.delete(userToRemove.value.id);
  } else if (
    userSelectDialogMode.value === "transfer" &&
    selectedUsers.value.length === 1
  ) {
    // Transfer ownership to new owner, demoting current owner to collaborator
    const newOwner = selectedUsers.value[0].id;
    if (newOwner) {
      followers.delete(newOwner);
      collaborators.delete(newOwner);
      collaborators.add(owner);
      owner = newOwner;
    }
  } else if (selectedPermissionLevel.value == "collaborator") {
    selectedUsers.value.forEach((u: User) => collaborators.add(u.id));
    selectedUsers.value.forEach((u: User) => followers.delete(u.id));
  } else if (selectedPermissionLevel.value == "follower") {
    selectedUsers.value.forEach((u: User) => followers.add(u.id));
    selectedUsers.value.forEach((u: User) => collaborators.delete(u.id));
  }
  const newPermissions: ProjectPermissions = {
    owner_id: owner,
    collaborator_ids: Array.from(collaborators).filter(
      (id) => id !== undefined,
    ),
    follower_ids: Array.from(followers).filter((id) => id !== undefined),
  };
  updateProjectPermissions(props.project.id, newPermissions).then((project) => {
    if (project) {
      emit("updateSelectedProject", project);
      selectedUsers.value = [];
      selectedPermissionLevel.value = "follower";
      showUserSelectDialog.value = false;
      userToRemove.value = undefined;
      getUsers().then((data) => {
        allUsers.value = data.filter((user) => user.id !== project.owner.id);
      });
    }
  });
}

onMounted(() => {
  getUsers().then((data) => {
    allUsers.value = data.filter((user) => user.id !== props.project.owner.id);
  });
});
</script>

<template>
  <div style="max-width: 500px">
    <v-list>
      <v-list-subheader>
        Owner
        <v-icon
          v-tooltip="'Permissions: Read, Write, Delete, Access Control'"
          icon="mdi-information-outline"
        />
      </v-list-subheader>
      <user-profile :user="project.owner">
        <template #append>
          <v-icon
            v-if="editMode"
            icon="mdi-pencil"
            @click="
              showUserSelectDialog = true;
              userSelectDialogMode = 'transfer';
            "
          />
        </template>
      </user-profile>
      <v-list-subheader>
        Collaborators
        <v-icon
          v-tooltip="'Permissions: Read & Write'"
          icon="mdi-information-outline"
        />
      </v-list-subheader>
      <user-profile
        v-for="collaborator in project.collaborators"
        :key="collaborator.id"
        :user="collaborator"
      >
        <template #append>
          <v-icon
            v-if="editMode"
            icon="mdi-trash-can"
            @click="userToRemove = collaborator"
          />
        </template>
      </user-profile>
      <v-list-item
        v-if="!project.collaborators.length"
        subtitle="No collaborators"
        class="mx-4"
      />
      <v-list-subheader>
        Followers
        <v-icon
          v-tooltip="'Permissions: Read Only'"
          icon="mdi-information-outline"
        />
      </v-list-subheader>
      <user-profile
        v-for="follower in project.followers"
        :key="follower.id"
        :user="follower"
      >
        <template #append>
          <v-icon
            v-if="editMode"
            icon="mdi-trash-can"
            @click="userToRemove = follower"
          />
        </template>
      </user-profile>
      <v-list-item
        v-if="!project.followers.length"
        subtitle="No followers"
        class="mx-4"
      />
    </v-list>
    <v-btn
      v-if="editMode"
      color="primary"
      @click="
        showUserSelectDialog = true;
        userSelectDialogMode = 'add';
      "
    >
      Add Users
    </v-btn>
    <v-dialog v-model="showUserSelectDialog" width="500">
      <v-card color="background">
        <v-card-title class="pa-3">
          {{
            userSelectDialogMode === "add" ? "Add Users" : "Select New Owner"
          }}
          <v-btn
            class="close-button transparent"
            variant="flat"
            icon
            @click="showUserSelectDialog = false"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-messages
          color="red"
          :active="userSelectDialogMode === 'transfer'"
          :messages="[
            'Warning: After transferring ownership to another user, you will no \
            longer be able to make changes to permissions or delete the project. \
            You will be added as a collaborator with read/write permissions.',
          ]"
          class="pa-3"
        />
        <v-card-text>
          <v-combobox
            v-model="selectedUsers"
            :items="allUsers"
            :label="
              userSelectDialogMode === 'add'
                ? 'Users to add'
                : 'New project owner'
            "
            item-title="username"
            return-object
            :multiple="userSelectDialogMode === 'add'"
            :clearable="userSelectDialogMode === 'add'"
            :chips="userSelectDialogMode === 'add'"
            :closable-chips="userSelectDialogMode === 'add'"
            @update:model-value="
              (v: User | User[]) => {
                if (Array.isArray(v)) selectedUsers = v;
                else selectedUsers = [v];
              }
            "
          >
            <template #item="{ props: itemProps, item }">
              <user-profile v-bind="itemProps" :user="item" />
            </template>
          </v-combobox>
          <v-select
            v-if="userSelectDialogMode === 'add'"
            v-model="selectedPermissionLevel"
            :items="permissionLevels"
            label="Permission Level"
          />
          <v-card-actions>
            <v-btn
              color="primary"
              :disabled="!selectedUsers.length"
              @click="savePermissions"
            >
              Submit
            </v-btn>
          </v-card-actions>
        </v-card-text>
      </v-card>
    </v-dialog>
    <v-dialog :model-value="!!userToRemove" width="500">
      <v-card>
        <v-card-title class="pa-3">
          Remove User
          <v-btn
            class="close-button transparent"
            variant="flat"
            icon
            @click="userToRemove = undefined"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text v-if="userToRemove">
          Are you sure you want to remove {{ userToRemove.username }} from this
          project?
        </v-card-text>
        <v-card-actions class="d-flex" style="justify-content: space-evenly">
          <v-btn color="red" @click="savePermissions">Delete</v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            @click="userToRemove = undefined"
          >
            Cancel
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.user-circle {
  letter-spacing: -2px;
  font-weight: bold;
  font-size: 14px;
}
</style>

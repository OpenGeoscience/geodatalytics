import axios from "axios";
import OauthClient from "@resonant/oauth-client";
import S3FileFieldClient from 'django-s3-file-field';
import { useAppStore } from "@/store";

const OAUTH2_CLIENT_ID = 'cBmD6D6F2YAmMWHNQZFPUr4OpaXVpW5w4Thod6Kj';

export const baseURL = `${import.meta.env.VITE_APP_API_ROOT}api/v1/`;

export const apiClient = axios.create({
  baseURL,
});
export const oauthClient = new OauthClient(
  new URL(`${import.meta.env.VITE_APP_API_ROOT}oauth/`),
  OAUTH2_CLIENT_ID,
  { redirectUrl: window.location.origin }
);

let s3ffClient = undefined;

export function getS3ffClient() {
  return s3ffClient
}

export async function restoreLogin() {
  if (!oauthClient) {
    return;
  }
  await oauthClient.maybeRestoreLogin();
  if (oauthClient.isLoggedIn) {
    apiClient.get("/users/me/").then((response) => {
      if (response.data) {
        useAppStore().currentUser = response.data;
      }
    });
    s3ffClient = new S3FileFieldClient({
      baseUrl: baseURL + 's3-upload/',
      apiConfig: {
        headers: oauthClient.authHeaders
      }
    })
  }
}

apiClient.interceptors.request.use((config) => ({
  ...config,
  headers: {
    ...oauthClient?.authHeaders,
    ...config.headers,
  },
}));

apiClient.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    const appStore = useAppStore();
    if (error.response?.status === 500) {
      appStore.currentError = "Server error; see server logs for details.";
    } else if (error.response?.status === 404) {
      appStore.currentError = "Not found.";
    } else if (error.response?.status === 401) {
      appStore.currentError = "Not authenticated.";
    } else if (error.response) {
      appStore.currentError = error.response?.data;
    } else {
      appStore.currentError = "An error occurred.";
    }
    return { data: undefined };
  }
);

export const logout = async () => {
  await oauthClient.logout();
  window.location.href = `${import.meta.env.VITE_APP_API_ROOT}accounts/logout/`
};

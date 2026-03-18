import { BRIDGE_LAST_URL_KEY } from './config.js';

export const loadPersistedSiteUrl = () => {
  try {
    return localStorage.getItem(BRIDGE_LAST_URL_KEY) || "";
  } catch (storageError) {
    console.warn("Falha ao ler URL persistida:", storageError);
    return "";
  }
};

export const persistSiteUrl = (siteUrl) => {
  if (!siteUrl) return;
  try {
    localStorage.setItem(BRIDGE_LAST_URL_KEY, siteUrl);
  } catch (storageError) {
    console.warn("Falha ao persistir URL:", storageError);
  }
};

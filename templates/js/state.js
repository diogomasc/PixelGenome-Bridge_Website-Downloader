import { loadPersistedSiteUrl } from './storage.js';

export const state = {
  siteUrl: loadPersistedSiteUrl(),
  indexHtml: "",
  downloadJobId: "",
  downloadDone: false,
  expectedZipFilename: "",
  designerHtml: "",
  eventSource: null,
};

import { state } from './state.js';
import { els, appendLog } from './ui.js';
import { validateUrlAndStartDownload } from './downloader.js';
import { 
  onIndexFileSelected, 
  validateAndGenerateDesignerSystem, 
  applyManualResult, 
  copyDesignerHtml, 
  downloadDesignerHtml, 
  copyManualPrompt 
} from './generator.js';

const bindEvents = () => {
  els.processUrlBtn.addEventListener("click", (event) => {
    event.preventDefault();
    validateUrlAndStartDownload();
  });

  els.indexFileInput.addEventListener("change", onIndexFileSelected);

  els.validateAndGenerateBtn.addEventListener("click", (event) => {
    event.preventDefault();
    validateAndGenerateDesignerSystem();
  });

  els.applyManualResultBtn.addEventListener("click", applyManualResult);
  els.copyDesignerBtn.addEventListener("click", copyDesignerHtml);
  els.downloadDesignerBtn.addEventListener("click", downloadDesignerHtml);
  els.copyManualPromptBtn.addEventListener("click", copyManualPrompt);

  els.siteUrlInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      validateUrlAndStartDownload();
    }
  });
};

const init = () => {
  if (state.siteUrl) {
    els.siteUrlInput.value = state.siteUrl;
  }
  bindEvents();
  appendLog("Logs aguardando inicio do download...");
};

document.addEventListener("DOMContentLoaded", init);

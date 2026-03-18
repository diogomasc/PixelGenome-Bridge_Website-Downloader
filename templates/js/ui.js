export const stepEls = {
  step1: document.getElementById("step1"),
  step2: document.getElementById("step2"),
};

export const els = {
  siteUrlInput: document.getElementById("siteUrlInput"),
  processUrlBtn: document.getElementById("processUrlBtn"),
  zipDownloadLink: document.getElementById("zipDownloadLink"),
  downloadStatus: document.getElementById("downloadStatus"),
  downloadLogs: document.getElementById("downloadLogs"),

  indexFileInput: document.getElementById("indexFileInput"),
  indexHtmlInput: document.getElementById("indexHtmlInput"),
  indexStats: document.getElementById("indexStats"),
  validateAndGenerateBtn: document.getElementById("validateAndGenerateBtn"),
  generationStatus: document.getElementById("generationStatus"),

  copyDesignerBtn: document.getElementById("copyDesignerBtn"),
  downloadDesignerBtn: document.getElementById("downloadDesignerBtn"),

  manualFallbackPanel: document.getElementById("manualFallbackPanel"),
  manualPromptText: document.getElementById("manualPromptText"),
  copyManualPromptBtn: document.getElementById("copyManualPromptBtn"),
  providerAttempts: document.getElementById("providerAttempts"),
  manualResultInput: document.getElementById("manualResultInput"),
  applyManualResultBtn: document.getElementById("applyManualResultBtn"),

  resultZone: document.getElementById("resultZone"),
  resultSource: document.getElementById("resultSource"),
  designerPreview: document.getElementById("designerPreview"),
};

export const setStatus = (element, message, type) => {
  element.textContent = message;
  element.className = "status";
  if (type) element.classList.add(type);
};

export const setStepComplete = (stepElement, complete) => {
  stepElement.classList.toggle("is-complete", complete);
};

export const setBusy = (button, busy, idleText, busyText) => {
  button.disabled = busy;
  button.textContent = busy ? busyText : idleText;
};

export const appendLog = (message) => {
  const line = document.createElement("div");
  line.className = "log-line";
  line.textContent = message;
  els.downloadLogs.appendChild(line);
  els.downloadLogs.scrollTop = els.downloadLogs.scrollHeight;
};

export const clearLogs = () => {
  els.downloadLogs.innerHTML = "";
};

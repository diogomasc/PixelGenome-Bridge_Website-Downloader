import { state } from './state.js';
import { apiUrl } from './config.js';
import { postJson } from './api.js';
import { els, stepEls, setStatus, setStepComplete, setBusy, appendLog, clearLogs } from './ui.js';
import { zipFilenameFromSiteUrl } from './utils.js';
import { persistSiteUrl } from './storage.js';

export const closeEventSource = () => {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
};

const onDownloadComplete = (jobId, filename) => {
  if (state.downloadDone) return;
  state.downloadDone = true;
  closeEventSource();

  const resolvedFilename = filename || state.expectedZipFilename || zipFilenameFromSiteUrl(state.siteUrl, jobId);

  setStatus(els.downloadStatus, "Extração concluída. Clique para baixar o pacote.", "success");
  setStepComplete(stepEls.step1, true);
  setBusy(els.processUrlBtn, false, "Iniciar Extração", "Processando...");

  const href = apiUrl("/api/download-zip/" + jobId);
  els.zipDownloadLink.href = href;
  els.zipDownloadLink.download = resolvedFilename;
  els.zipDownloadLink.textContent = "Baixar " + resolvedFilename;
  els.zipDownloadLink.classList.remove("hidden");
};

export const pollDownloadStatus = async (jobId) => {
  for (let attempt = 0; attempt < 240; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 2500));
    try {
      const response = await fetch(apiUrl("/api/download-status/" + jobId));
      if (!response.ok) continue;

      const data = await response.json();
      if (data.status === "complete") {
        onDownloadComplete(jobId, data.filename);
        return;
      }
      if (data.status === "error") {
        setStatus(els.downloadStatus, data.error || "Erro na extração.", "error");
        setBusy(els.processUrlBtn, false, "Iniciar Extração", "Processando...");
        return;
      }
    } catch (pollError) {
      appendLog("Falha ao consultar status: " + pollError.message);
    }
  }

  if (!state.downloadDone) {
    setStatus(els.downloadStatus, "Extração em andamento. Aguarde um momento.", "warning");
    setBusy(els.processUrlBtn, false, "Iniciar Extração", "Processando...");
  }
};

export const bindDownloadStream = (jobId) => {
  closeEventSource();
  const eventSource = new EventSource(apiUrl("/api/download-events/" + jobId));
  state.eventSource = eventSource;

  eventSource.onmessage = (event) => appendLog(event.data);
  eventSource.addEventListener("done", async (event) => {
    if (event.data === "complete") {
      appendLog("Download concluido. Preparando liberacao do ZIP...");
      try {
        const response = await fetch(apiUrl("/api/download-status/" + jobId));
        if (response.ok) {
          const data = await response.json();
          onDownloadComplete(jobId, data.filename);
          return;
        }
      } catch (statusError) {
        appendLog("Nao foi possivel ler status final: " + statusError.message);
      }
      onDownloadComplete(jobId);
    } else {
      setStatus(els.downloadStatus, "Erro na extração. Verifique os logs.", "error");
      setBusy(els.processUrlBtn, false, "Iniciar Extração", "Processando...");
    }
  });

  eventSource.onerror = () => {
    appendLog("Conexao de logs interrompida. Tentando status de backup...");
    closeEventSource();
    pollDownloadStatus(jobId);
  };
};

export const validateUrlAndStartDownload = async () => {
  const typedUrl = els.siteUrlInput.value.trim();
  if (!typedUrl) {
    setStatus(els.downloadStatus, "Informe uma URL válida.", "warning");
    return;
  }

  setBusy(els.processUrlBtn, true, "Iniciar Extração", "Validando...");
  setStatus(els.downloadStatus, "Validando URL...", "");
  clearLogs();
  state.downloadDone = false;
  state.expectedZipFilename = "";
  els.zipDownloadLink.classList.add("hidden");

  try {
    const urlData = await postJson("/api/validate-url", { site_url: typedUrl });
    state.siteUrl = urlData.normalized_url;
    persistSiteUrl(state.siteUrl);
    els.siteUrlInput.value = state.siteUrl;
    appendLog("URL validada: " + state.siteUrl);

    setBusy(els.processUrlBtn, true, "Iniciar Extração", "Extraindo...");
    setStatus(els.downloadStatus, "Iniciando extração do DNA...", "");

    const data = await postJson("/api/download-site", { site_url: state.siteUrl });
    state.downloadJobId = data.job_id;
    state.expectedZipFilename = data.filename || zipFilenameFromSiteUrl(state.siteUrl, data.job_id);

    appendLog("Job " + data.job_id + " iniciado.");
    bindDownloadStream(data.job_id);
    pollDownloadStatus(data.job_id);
  } catch (error) {
    setStatus(els.downloadStatus, error.message, "error");
    setBusy(els.processUrlBtn, false, "Iniciar Extração", "Processando...");
    setStepComplete(stepEls.step1, false);
  }
};

import { state } from './state.js';
import { postJson } from './api.js';
import { els, stepEls, setStatus, setStepComplete, setBusy } from './ui.js';
import { extractSiteUrlFromIndexHtml, readFileContent, copyToClipboard } from './utils.js';
import { persistSiteUrl, loadPersistedSiteUrl } from './storage.js';

const hideManualFallbackPanel = () => {
  els.manualFallbackPanel.classList.add("hidden");
  els.providerAttempts.innerHTML = "";
};

const showManualFallbackPanel = (prompt, attempts) => {
  els.manualFallbackPanel.classList.remove("hidden");
  els.manualPromptText.value = prompt || "";
  els.providerAttempts.innerHTML = "";
  (attempts || []).forEach((item) => {
    const line = document.createElement("li");
    line.textContent = item;
    els.providerAttempts.appendChild(line);
  });
};

const renderDesignerResult = (html, sourceLabel) => {
  state.designerHtml = html;
  els.resultZone.classList.add("active");
  els.designerPreview.srcdoc = html;
  els.resultSource.textContent = "Fonte: " + sourceLabel;
  els.copyDesignerBtn.classList.remove("hidden");
  els.downloadDesignerBtn.classList.remove("hidden");
  setStepComplete(stepEls.step2, true);
};

export const onIndexFileSelected = async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;

  if (file.size > 2 * 1024 * 1024) {
    setStatus(els.generationStatus, "Arquivo excede o limite de 2MB.", "error");
    event.target.value = "";
    return;
  }

  try {
    const content = await readFileContent(file);
    els.indexHtmlInput.value = content;
    state.indexHtml = content;
    els.indexStats.textContent = `Ativo carregado: ${file.name} | ${content.length} caracteres`;
    setStatus(els.generationStatus, "Pronto para gerar o Design System.", "");
  } catch (error) {
    setStatus(els.generationStatus, error.message, "error");
  }
};

export const validateAndGenerateDesignerSystem = async () => {
  const typedUrl = els.siteUrlInput.value.trim();
  const indexHtmlToUse = els.indexHtmlInput.value.trim();
  const extractedUrl = extractSiteUrlFromIndexHtml(indexHtmlToUse);
  const siteUrlToUse = typedUrl || state.siteUrl || loadPersistedSiteUrl() || extractedUrl;

  if (siteUrlToUse && !typedUrl) els.siteUrlInput.value = siteUrlToUse;

  if (!siteUrlToUse) {
    setStatus(els.generationStatus, "Informe a URL de referência.", "warning");
    return;
  }
  if (!indexHtmlToUse) {
    setStatus(els.generationStatus, "Forneça o INDEX_HTML para processar.", "warning");
    return;
  }

  setBusy(els.validateAndGenerateBtn, true, "Gerar Design System", "Validando...");
  hideManualFallbackPanel();

  try {
    setStatus(els.generationStatus, "Validando URL...", "");
    const urlData = await postJson("/api/validate-url", { site_url: siteUrlToUse });
    state.siteUrl = urlData.normalized_url;
    persistSiteUrl(state.siteUrl);
    els.siteUrlInput.value = state.siteUrl;

    setStatus(els.generationStatus, "Validando INDEX_HTML...", "");
    const validation = await postJson("/api/validate-index", { index_html: indexHtmlToUse });
    state.indexHtml = indexHtmlToUse;
    const count = validation.metadata?.char_count ?? indexHtmlToUse.length;
    els.indexStats.textContent = `INDEX_HTML processado: ${count} caracteres.`;

    setStatus(els.generationStatus, "Gerando Design System...", "");
    const data = await postJson("/api/generate-designer-system", {
      site_url: state.siteUrl,
      index_html: state.indexHtml,
    });

    if (data.success) {
      renderDesignerResult(data.designer_system_html, `${data.provider} / ${data.model}`);
      setStatus(els.generationStatus, "Design System gerado!", "success");
      return;
    }

    if (data.fallback_required) {
      showManualFallbackPanel(data.manual_fallback_prompt, data.provider_attempts);
      setStatus(els.generationStatus, "IA offline. Use o módulo de backup.", "warning");
      setStepComplete(stepEls.step2, false);
      return;
    }
    setStatus(els.generationStatus, "Erro na geração.", "error");
    setStepComplete(stepEls.step2, false);
  } catch (error) {
    setStatus(els.generationStatus, error.message, "error");
    setStepComplete(stepEls.step2, false);
  } finally {
    setBusy(els.validateAndGenerateBtn, false, "Gerar Design System", "Validando...");
  }
};

export const applyManualResult = async () => {
  const manualHtml = els.manualResultInput.value.trim();
  if (!manualHtml) {
    setStatus(els.generationStatus, "Insira o resultado do backup.", "warning");
    return;
  }
  const lower = manualHtml.toLowerCase();
  if (!lower.includes("<html") && !lower.includes("<!doctype html")) {
    setStatus(els.generationStatus, "HTML inválido ou incompleto.", "error");
    return;
  }
  renderDesignerResult(manualHtml, "Backup Manual");
  setStatus(els.generationStatus, "DNA aplicado com sucesso.", "success");
};

export const copyDesignerHtml = async () => {
  if (!state.designerHtml) {
    setStatus(els.generationStatus, "Nao ha HTML para copiar.", "warning");
    return;
  }
  try {
    await copyToClipboard(state.designerHtml);
    setStatus(els.generationStatus, "Copiado para a área de transferência!", "success");
  } catch (e) {
    setStatus(els.generationStatus, "Erro ao copiar: " + e.message, "error");
  }
};

export const downloadDesignerHtml = () => {
  if (!state.designerHtml) {
    setStatus(els.generationStatus, "Nao ha HTML para baixar.", "warning");
    return;
  }
  const blob = new Blob([state.designerHtml], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "designer_system.html";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  setStatus(els.generationStatus, "Download iniciado.", "success");
};

export const copyManualPrompt = async () => {
  const prompt = els.manualPromptText.value.trim();
  if (!prompt) {
    setStatus(els.generationStatus, "Nao existe prompt.", "warning");
    return;
  }
  try {
    await copyToClipboard(prompt);
    setStatus(els.generationStatus, "Prompt copiado.", "success");
  } catch (e) {
    setStatus(els.generationStatus, "Erro ao copiar: " + e.message, "error");
  }
};

export const extractSiteUrlFromIndexHtml = (indexHtml) => {
  if (!indexHtml) return "";
  const patterns = [
    /<link[^>]+rel=["']canonical["'][^>]*href=["']([^"']+)["']/i,
    /<meta[^>]+property=["']og:url["'][^>]*content=["']([^"']+)["']/i,
    /<meta[^>]+content=["']([^"']+)["'][^>]*property=["']og:url["']/i,
  ];
  for (const pattern of patterns) {
    const match = indexHtml.match(pattern);
    if (match && match[1] && URL.canParse(match[1])) return match[1];
  }
  return "";
};

export const zipFilenameFromSiteUrl = (siteUrl, fallbackId) => {
  if (!siteUrl || !URL.canParse(siteUrl)) {
    return (fallbackId || "site") + ".zip";
  }
  try {
    const parsed = new URL(siteUrl);
    let cleanName = parsed.hostname.replace(/^www\./i, "");
    cleanName = cleanName.replaceAll(/[^a-zA-Z0-9.-]/g, "_");
    if (parsed.pathname && parsed.pathname !== "/") {
      const pathPart = parsed.pathname
        .split("/")
        .filter(Boolean)
        .join("_")
        .replaceAll(/[^a-zA-Z0-9]/g, "_")
        .slice(0, 30);
      if (pathPart) cleanName = cleanName + "_" + pathPart;
    }
    return (cleanName || fallbackId || "site") + ".zip";
  } catch (parseError) {
    console.warn("Falha ao montar nome do ZIP:", parseError);
    return (fallbackId || "site") + ".zip";
  }
};

export const readFileContent = (file) => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Nao foi possivel ler o arquivo."));
    reader.readAsText(file, "utf-8");
  });
};

export const copyToClipboard = async (text) => {
  await navigator.clipboard.writeText(text);
};

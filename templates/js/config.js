export const BRIDGE_LAST_URL_KEY = "layoutgenome_bridge_last_url";

export const API_BASE_URL = (() => {
  const origin = globalThis.location.origin;
  const host = globalThis.location.hostname;
  const port = globalThis.location.port;
  const liveServerPorts = new Set(["5500", "5501", "5502", "5503"]);

  if (port === "5001") return origin;
  if ((host === "127.0.0.1" || host === "localhost") && liveServerPorts.has(port)) {
    return "http://127.0.0.1:5001";
  }
  return origin;
})();

export const apiUrl = (path) => {
  if (!path || !path.startsWith("/")) return path;
  return API_BASE_URL + path;
};

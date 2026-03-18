import { apiUrl } from './config.js';

const apiErrorMessage = (response, fallback) =>
  response && response.error ? response.error : fallback;

export const postJson = async (url, payload) => {
  const response = await fetch(apiUrl(url), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  const raw = await response.text();
  let data = {};
  if (raw) {
    try {
      data = JSON.parse(raw);
    } catch (parseError) {
      data = {
        error: "Resposta invalida do servidor: " + parseError.message,
        raw: raw,
      };
    }
  }

  if (!response.ok) {
    throw new Error(apiErrorMessage(data, "Falha na requisicao."));
  }

  return data;
};

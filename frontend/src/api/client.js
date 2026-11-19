// client.js - all calls to the FastAPI backend live here so components stay simple.

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Generating 3 designs makes several LLM calls, so allow up to 5 minutes before giving up.
const REQUEST_TIMEOUT_MS = 5 * 60 * 1000;

// FastAPI sends either {detail: "text"} or {detail: [{loc, msg}, ...]} for validation errors.
function readErrorMessage(body, status) {
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail)) {
    return body.detail.map((d) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ");
  }
  return `Request failed with status ${status}.`;
}

// Wrapper around fetch that adds a timeout and turns every failure into a readable Error.
async function request(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_URL}${path}`, { ...options, signal: controller.signal });
    const body = await response.json().catch(() => null);
    if (!response.ok) throw new Error(readErrorMessage(body, response.status));
    return body;
  } catch (err) {
    if (err.name === "AbortError") throw new Error("The request took too long. Please try again.");
    if (err instanceof TypeError) {
      throw new Error(`Cannot reach the backend at ${API_URL}. Is it running?`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export function generateDesigns(payload) {
  return request("/api/designs/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getDesigns(requestId) {
  return request(`/api/designs/${requestId}`);
}

// Images are saved on the backend and served from /generated, so turn the returned path into a full URL.
export function imageUrl(path) {
  return `${API_URL}${path}`;
}

// Only reads what is already saved. Never spends image quota.
export function getImages(designId) {
  return request(`/api/designs/${designId}/images`);
}

// Generates whichever of the 4 images are missing, then returns all of them.
export function generateImages(designId) {
  return request(`/api/designs/${designId}/images`, { method: "POST" });
}

// Sends only the edited fields. The backend copies the viewed version and saves the result as the next one.
export function modifyDesigns(requestId, changes) {
  return request(`/api/designs/${requestId}/modify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  });
}

export function getVersions(projectId) {
  return request(`/api/designs/projects/${projectId}/versions`);
}

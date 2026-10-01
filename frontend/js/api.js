// Transport only. Scientific evaluation belongs to the Python engine.
export async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, options);
  } catch {
    throw new Error("Cannot reach the local engine. Start Chronologer and reload this page.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail)
      ? detail.map(error => `${error.loc.slice(1).join(" · ")}: ${error.msg}`).join("; ")
      : `Request failed (${response.status}). Please try again.`);
  }
  return response.json();
}
export const getCurves = () => request("/curves");
export const getCurve = name => request(`/curves/${encodeURIComponent(name)}`);
export const calibrate = data => request("/calibrate", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
});
export const fitDensity = data => request("/density", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
});

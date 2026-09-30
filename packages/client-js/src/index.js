import { readFile } from "node:fs/promises";
import { basename } from "node:path";

/** Server-side client for Reality Cloud. Do not bundle API keys into browsers. */
export class RealityCloudError extends Error {}

export class Model {
  constructor(client, id) { this.client = client; this.id = id; }
  status() { return this.client.request("GET", `/v1/files/${this.id}`); }
  summary() { return this.client.request("GET", `/v1/models/${this.id}/summary`); }
  parts() { return this.client.request("GET", `/v1/models/${this.id}/parts`); }
  measure(part) { return this.client.request("POST", `/v1/models/${this.id}/measure`, {part}); }
  distance(first, second) { return this.client.request("POST", `/v1/models/${this.id}/distance`, {first, second}); }
}

export class Reality {
  constructor({ apiKey, baseUrl = "https://api.reality.dev", fetchImpl = fetch }) {
    if (!apiKey?.startsWith("rlt_")) throw new Error("Reality API keys begin with rlt_");
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.fetch = fetchImpl;
  }
  async upload(pathOrFile) {
    const form = new FormData();
    if (typeof pathOrFile === "string") {
      const bytes = await readFile(pathOrFile);
      form.append("file", new Blob([bytes]), basename(pathOrFile));
    } else {
      form.append("file", pathOrFile);
    }
    const data = await this.request("POST", "/v1/files", form, true);
    return new Model(this, data.id);
  }
  async request(method, path, body, isForm = false) {
    const headers = { Authorization: `Bearer ${this.apiKey}` };
    if (body && !isForm) headers["Content-Type"] = "application/json";
    const response = await this.fetch(`${this.baseUrl}${path}`, {
      method, headers, body: body ? (isForm ? body : JSON.stringify(body)) : undefined,
    });
    const data = await response.json();
    if (!response.ok) throw new RealityCloudError(`Reality API ${response.status}: ${data.message ?? "request failed"}`);
    return data;
  }
}

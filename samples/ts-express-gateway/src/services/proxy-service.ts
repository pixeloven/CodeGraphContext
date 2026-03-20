/**
 * Lightweight proxy that forwards requests to backend services.
 *
 * Uses Node's built-in `http` module so that OTEL HttpInstrumentation
 * wraps these calls with CLIENT spans and injects W3C traceparent headers.
 */
import http from "http";

function httpRequest(
  url: string,
  options: http.RequestOptions = {},
  body?: string
): Promise<{ status: number; data: string }> {
  return new Promise((resolve, reject) => {
    const req = http.request(url, options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () =>
        resolve({ status: res.statusCode ?? 0, data })
      );
    });
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

export class ProxyService {
  async proxyGet(url: string): Promise<unknown> {
    const res = await httpRequest(url);
    if (res.status < 200 || res.status >= 300) {
      throw new Error(`Upstream GET ${url} returned ${res.status}`);
    }
    return JSON.parse(res.data);
  }

  async proxyPost(url: string, body: unknown): Promise<unknown> {
    const payload = JSON.stringify(body);
    const res = await httpRequest(
      url,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(payload).toString(),
        },
      },
      payload
    );
    if (res.status < 200 || res.status >= 300) {
      throw new Error(`Upstream POST ${url} returned ${res.status}`);
    }
    return JSON.parse(res.data);
  }
}

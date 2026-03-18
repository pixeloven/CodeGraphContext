/**
 * Lightweight proxy that forwards requests to backend services.
 *
 * Uses the global `fetch` (Node 18+). OTEL auto-instrumentation wraps
 * these calls with CLIENT spans and injects W3C traceparent headers
 * automatically.
 */
export class ProxyService {
  async proxyGet(url: string): Promise<unknown> {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(
        `Upstream GET ${url} returned ${response.status}: ${response.statusText}`
      );
    }
    return response.json();
  }

  async proxyPost(url: string, body: unknown): Promise<unknown> {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(
        `Upstream POST ${url} returned ${response.status}: ${response.statusText}`
      );
    }
    return response.json();
  }
}

const PHP_BACKEND =
  process.env.PHP_BACKEND_URL ?? "http://sample-php:8080";
const PYTHON_BACKEND =
  process.env.PYTHON_BACKEND_URL ?? "http://sample-python:8081";

export interface DashboardResult {
  orders: unknown[];
  stats: {
    php_count: number;
    python_count: number;
  };
}

export class DashboardService {
  /**
   * Aggregates data from both PHP and Python backends.
   *
   * Uses the global `fetch` (Node 18+). OTEL auto-instrumentation wraps
   * these calls with CLIENT spans and injects W3C traceparent headers,
   * producing `CALLS_SERVICE` edges in the CGC graph.
   */
  async getDashboard(): Promise<DashboardResult> {
    const [phpResponse, pythonResponse] = await Promise.all([
      fetch(`${PHP_BACKEND}/api/orders`),
      fetch(`${PYTHON_BACKEND}/api/orders`),
    ]);

    const phpOrders: unknown[] = phpResponse.ok
      ? await phpResponse.json()
      : [];
    const pythonOrders: unknown[] = pythonResponse.ok
      ? await pythonResponse.json()
      : [];

    return {
      orders: [...phpOrders, ...pythonOrders],
      stats: {
        php_count: phpOrders.length,
        python_count: pythonOrders.length,
      },
    };
  }
}

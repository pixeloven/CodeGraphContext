/**
 * Aggregates data from PHP and Python backend services.
 *
 * Uses Node's built-in `http` module so that OTEL HttpInstrumentation
 * wraps these calls with CLIENT spans and injects W3C traceparent headers,
 * producing `CALLS_SERVICE` edges in the CGC graph.
 */
import http from "http";

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

function httpGet(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    http.get(url, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => resolve(data));
    }).on("error", reject);
  });
}

export class DashboardService {
  async getDashboard(): Promise<DashboardResult> {
    const [phpData, pythonData] = await Promise.all([
      httpGet(`${PHP_BACKEND}/api/orders`),
      httpGet(`${PYTHON_BACKEND}/api/orders`),
    ]);

    const phpOrders = JSON.parse(phpData) as unknown[];
    const pythonOrders = JSON.parse(pythonData) as unknown[];

    return {
      orders: [...phpOrders, ...pythonOrders],
      stats: {
        php_count: phpOrders.length,
        python_count: pythonOrders.length,
      },
    };
  }
}

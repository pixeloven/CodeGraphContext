import { Router, Request, Response } from "express";
import { ProxyService } from "../services/proxy-service";

export const ordersRouter = Router();
const proxy = new ProxyService();

const PHP_BACKEND =
  process.env.PHP_BACKEND_URL ?? "http://sample-php:8080";

/**
 * GET /api/orders — proxies to PHP backend.
 */
ordersRouter.get("/", async (_req: Request, res: Response) => {
  try {
    const data = await proxy.proxyGet(`${PHP_BACKEND}/api/orders`);
    res.json(data);
  } catch (err) {
    console.error("Proxy GET /api/orders failed:", err);
    res.status(502).json({ error: "Failed to fetch orders from backend" });
  }
});

/**
 * POST /api/orders — proxies to PHP backend.
 */
ordersRouter.post("/", async (req: Request, res: Response) => {
  try {
    const data = await proxy.proxyPost(
      `${PHP_BACKEND}/api/orders`,
      req.body
    );
    res.status(201).json(data);
  } catch (err) {
    console.error("Proxy POST /api/orders failed:", err);
    res.status(502).json({ error: "Failed to create order via backend" });
  }
});

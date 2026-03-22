import { Router, Request, Response } from "express";

export const healthRouter = Router();

/**
 * GET /health — simple liveness check.
 */
healthRouter.get("/", (_req: Request, res: Response) => {
  res.json({ status: "ok" });
});

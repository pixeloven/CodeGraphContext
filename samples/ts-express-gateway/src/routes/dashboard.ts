import { Router, Request, Response } from "express";
import { DashboardService } from "../services/dashboard-service";

export const dashboardRouter = Router();
const service = new DashboardService();

/**
 * GET /api/dashboard
 *
 * Aggregates data from both the PHP and Python backends into a single
 * response.  The outgoing HTTP calls produce CLIENT spans with
 * `peer.service` attributes, which generate `CALLS_SERVICE` edges in
 * the CGC graph.
 */
dashboardRouter.get("/", async (_req: Request, res: Response) => {
  try {
    const result = await service.getDashboard();
    res.json(result);
  } catch (err) {
    console.error("Dashboard aggregation failed:", err);
    res.status(502).json({ error: "Failed to aggregate dashboard data" });
  }
});

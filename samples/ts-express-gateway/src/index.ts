// Side-effect import: initialises OTEL SDK before anything else.
import "./instrumentation";

import express from "express";
import { dashboardRouter } from "./routes/dashboard";
import { ordersRouter } from "./routes/orders";
import { healthRouter } from "./routes/health";

const app = express();
const PORT = parseInt(process.env.PORT ?? "8082", 10);

app.use(express.json());

app.use("/api/dashboard", dashboardRouter);
app.use("/api/orders", ordersRouter);
app.use("/health", healthRouter);

app.listen(PORT, () => {
  console.log(`sample-ts-gateway listening on :${PORT}`);
});

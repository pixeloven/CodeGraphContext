/**
 * OTEL SDK setup — must be imported before any other modules so that
 * auto-instrumentations can monkey-patch http, express, etc.
 */

import { NodeSDK } from "@opentelemetry/sdk-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";
import { HttpInstrumentation } from "@opentelemetry/instrumentation-http";
import { ExpressInstrumentation } from "@opentelemetry/instrumentation-express";
import { Resource } from "@opentelemetry/resources";
import { SEMRESATTRS_SERVICE_NAME } from "@opentelemetry/semantic-conventions";
import type { Span } from "@opentelemetry/api";
import type { ClientRequest } from "http";

const endpoint =
  process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? "http://otel-collector:4318";

const sdk = new NodeSDK({
  resource: new Resource({
    [SEMRESATTRS_SERVICE_NAME]: "sample-ts-gateway",
  }),
  traceExporter: new OTLPTraceExporter({
    url: `${endpoint}/v1/traces`,
  }),
  instrumentations: [
    getNodeAutoInstrumentations({
      // Disable fs instrumentation to reduce noise
      "@opentelemetry/instrumentation-fs": { enabled: false },
    }),
    new HttpInstrumentation({
      requestHook: (span, request) => {
        // Map target hostname to service name for CALLS_SERVICE edges
        const req = request as ClientRequest;
        const host = (req.getHeader?.("host") ?? "").toString();
        const peerMap: Record<string, string> = {
          "sample-php:8080": "sample-php",
          "sample-python:8081": "sample-python",
        };
        const peer = peerMap[host];
        if (peer) {
          span.setAttribute("peer.service", peer);
        }
      },
    }),
    new ExpressInstrumentation(),
  ],
});

sdk.start();

process.on("SIGTERM", () => {
  sdk.shutdown().then(
    () => console.log("OTEL SDK shut down"),
    (err) => console.error("Error shutting down OTEL SDK", err)
  );
});

console.log(
  `OTEL instrumentation initialized — exporting to ${endpoint}/v1/traces`
);

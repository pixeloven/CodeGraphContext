# Build stage
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

# Run stage
FROM node:20-slim
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --omit=dev
COPY --from=builder /app/dist ./dist

ENV OTEL_SERVICE_NAME=sample-ts-gateway
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
ENV OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
ENV PHP_BACKEND_URL=http://sample-php:8080
ENV PYTHON_BACKEND_URL=http://sample-python:8081

EXPOSE 8082

CMD ["node", "dist/index.js"]

# Hosted MCP Server Deployment Guide

The CGC hosted MCP server runs the Model Context Protocol over HTTP transport,
making it accessible to remote AI clients without requiring a local CGC
installation. Use it for shared team infrastructure (one server, many clients)
or when your AI client runs in a cloud environment and cannot use stdio.

The standard CGC MCP mode (`cgc mcp start`) uses stdio — it is launched as a
child process by the IDE. The hosted server (`cgc mcp start --transport http`)
listens on a port and accepts JSON-RPC requests at `POST /mcp`. The same tools
are available; only the transport layer changes.

---

## Quick Start (Docker Compose + Neo4j)

The fastest path to a running server:

```bash
# 1. Clone and enter the repo
git clone https://github.com/your-org/codegraphcontext.git
cd codegraphcontext

# 2. Create an env file (minimum: set a real password)
cp .env.example .env
# Edit .env: set NEO4J_PASSWORD

# 3. Start Neo4j + the hosted MCP server
docker compose -f docker-compose.plugin-stack.yml up -d neo4j cgc-mcp

# 4. Verify the server is healthy
curl http://localhost:8045/healthz
# Expected: {"status":"ok","neo4j":"connected"}
```

The MCP endpoint is now available at `http://localhost:8045/mcp`.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_TYPE` | `neo4j` | Backend database driver. Only `neo4j` is supported in the current release. |
| `NEO4J_URI` | `bolt://localhost:7687` | Bolt URI for the Neo4j instance. Use the container service name (e.g. `bolt://neo4j:7687`) when running in Docker. |
| `NEO4J_USERNAME` | `neo4j` | Neo4j username. |
| `NEO4J_PASSWORD` | *(required)* | Neo4j password. Always supply at runtime; never bake into an image. |
| `CGC_MCP_PORT` | `8045` | Port the HTTP server listens on. |
| `CGC_CORS_ORIGIN` | `*` | Value for the `Access-Control-Allow-Origin` response header. Set to your specific origin in production (e.g. `https://app.example.com`). |

---

## Deployment Options

### Docker Standalone

```bash
docker build -f Dockerfile.mcp -t cgc-mcp:latest .

docker run -d \
  --name cgc-mcp \
  -e DATABASE_TYPE=neo4j \
  -e NEO4J_URI=bolt://your-neo4j-host:7687 \
  -e NEO4J_USERNAME=neo4j \
  -e NEO4J_PASSWORD=your-password \
  -e CGC_CORS_ORIGIN=https://your-client-origin.com \
  -p 8045:8045 \
  cgc-mcp:latest
```

### Docker Compose

The repository ships `docker-compose.plugin-stack.yml`, which includes the
`cgc-mcp` service wired to Neo4j on the `cgc-network` bridge. To start only
the hosted MCP server and its dependency:

```bash
docker compose -f docker-compose.plugin-stack.yml up -d neo4j cgc-mcp
```

To start the full plugin stack (including the OTEL collector and processor):

```bash
docker compose -f docker-compose.plugin-stack.yml up -d
```

The samples demo stack (`samples/docker-compose.yml`) also includes a
`cgc-mcp` service under the `mcp` profile — see
[Hosted MCP in the Sample Stack](#hosted-mcp-in-the-sample-stack) below.

### Docker Swarm

```bash
docker service create \
  --name cgc-mcp \
  --replicas 2 \
  --publish published=8045,target=8045 \
  --env DATABASE_TYPE=neo4j \
  --env NEO4J_URI=bolt://neo4j:7687 \
  --env NEO4J_USERNAME=neo4j \
  --secret cgc_neo4j_password \
  cgc-mcp:latest
```

Use Docker secrets (`--secret`) rather than `--env` for the password in Swarm
mode.

### Kubernetes

Manifests are in `k8s/cgc-mcp/`:

```bash
# Apply the ConfigMap, Deployment, and Service
kubectl apply -f k8s/cgc-mcp/

# Verify rollout
kubectl rollout status deployment/cgc-mcp
kubectl get svc cgc-mcp
```

The Service exposes port 8045. Create an Ingress or use a LoadBalancer service
type to expose it externally. Supply `NEO4J_PASSWORD` via a Kubernetes Secret
rather than a plain ConfigMap value.

---

## Client Configuration

Any MCP client that supports HTTP transport can connect to `POST /mcp`.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "codegraphcontext": {
      "transport": "http",
      "url": "http://your-server:8045/mcp"
    }
  }
}
```

Restart Claude Desktop after saving.

### VS Code / Cursor (MCP Extension)

In your workspace or user settings:

```json
{
  "mcp.servers": {
    "codegraphcontext": {
      "transport": "http",
      "url": "http://your-server:8045/mcp"
    }
  }
}
```

### Claude Code

```bash
claude mcp add codegraphcontext --transport http --url http://your-server:8045/mcp
```

Verify it was added:

```bash
claude mcp list
```

### Generic MCP Client

Point the client at `http://your-server:8045/mcp` using HTTP transport.
Send JSON-RPC 2.0 requests with `Content-Type: application/json`.

Example — list available tools:

```bash
curl -s -X POST http://localhost:8045/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | jq '.result.tools[].name'
```

---

## Security

The server has no application-level authentication. This is intentional: auth
is the responsibility of the reverse proxy in front of it.

### Nginx — Bearer Token Auth + TLS

```nginx
server {
    listen 443 ssl;
    server_name mcp.example.com;

    ssl_certificate     /etc/ssl/certs/mcp.crt;
    ssl_certificate_key /etc/ssl/private/mcp.key;

    location /mcp {
        # Require a shared secret from the client
        if ($http_authorization != "Bearer your-shared-secret") {
            return 401;
        }
        proxy_pass http://127.0.0.1:8045;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /healthz {
        proxy_pass http://127.0.0.1:8045;
    }
}
```

### Traefik — Forward Auth Middleware

```yaml
# docker-compose labels on the cgc-mcp service:
labels:
  - "traefik.enable=true"
  - "traefik.http.routers.cgc-mcp.rule=Host(`mcp.example.com`)"
  - "traefik.http.routers.cgc-mcp.tls=true"
  - "traefik.http.routers.cgc-mcp.middlewares=cgc-auth"
  - "traefik.http.middlewares.cgc-auth.forwardauth.address=http://your-auth-service/verify"
  - "traefik.http.services.cgc-mcp.loadbalancer.server.port=8045"
```

Set `CGC_CORS_ORIGIN` to the specific client origin rather than `*` whenever
the server is reachable from the public internet.

---

## Health Checks

`GET /healthz` returns the server's operational status.

| Condition | HTTP Status | Response body |
|---|---|---|
| Server running, Neo4j reachable | `200 OK` | `{"status":"ok","neo4j":"connected"}` |
| Server running, Neo4j unreachable | `503 Service Unavailable` | `{"status":"degraded","neo4j":"unreachable"}` |

The Docker image uses this endpoint for its `HEALTHCHECK` directive (every 30s,
3 retries before marking the container unhealthy). The Kubernetes liveness and
readiness probes in `k8s/cgc-mcp/deployment.yaml` use it for the same purpose.

Monitor `/healthz` from your load balancer or uptime tool to detect Neo4j
connectivity issues early.

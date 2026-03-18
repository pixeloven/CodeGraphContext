# Known Limitations — CGC Sample Applications

## FQN Correlation Gap

**Status**: Known limitation — not a bug. Will be resolved in a future story.

### Problem

`CORRELATES_TO` edges (OTEL spans → static code nodes) and `RESOLVES_TO` edges (Xdebug
stack frames → static code nodes) **will never form** with the current codebase.

### Root Cause

The OTEL writer attempts to match spans to static nodes using:

```cypher
MATCH (m:Method {fqn: $fqn})
MERGE (sp)-[:CORRELATES_TO]->(m)
```

The Xdebug writer does the same for `RESOLVES_TO`:

```cypher
MATCH (m:Method {fqn: $fqn})
MERGE (sf)-[:RESOLVES_TO]->(m)
```

However, CGC's graph builder (`src/codegraphcontext/tools/graph_builder.py:379`) creates
**`Function` nodes** (not `Method` nodes) and does **not compute an `fqn` property**:

```cypher
MERGE (n:Function {name: $name, path: $path, line_number: $line})
```

This means:

1. **Label mismatch**: Queries match `Method` but the graph contains `Function`
2. **Missing property**: Even if the label were correct, there is no `fqn` property to
   match against

### Impact on Sample Apps

- OTEL spans will be ingested correctly (Service, Trace, Span nodes all form)
- Static code will be indexed correctly (Function, Class nodes all form)
- **Cross-layer correlation will not work** — the graph has both runtime and static nodes
  but no edges connecting them
- The smoke script (`smoke-all.sh`) tests for this explicitly: the `correlates_to`
  assertion expects a count of 0 and reports **WARN** (not FAIL)

### What Each Sample App Would Produce (Once Fixed)

| App | OTEL `code.namespace` | OTEL `code.function` | Expected FQN |
|---|---|---|---|
| PHP/Laravel | `App\Http\Controllers\OrderController` | `index` | `App\Http\Controllers\OrderController::index` |
| Python/FastAPI | `app.services.order_service.OrderService` | `list_orders` | `app.services.order_service.OrderService.list_orders` |
| TypeScript/Express | `DashboardService` | `getDashboard` | `DashboardService.getDashboard` |

### Resolution Path

A future story will:

1. Add FQN computation to the graph builder (combining path, class, and function name
   into a language-appropriate FQN)
2. Change `Function` nodes to `Method` nodes where appropriate (or add a `Method` label
   alongside `Function`)
3. Add an `fqn` property to these nodes

Once that story lands, the sample apps will serve as **regression fixtures** — re-running
`smoke-all.sh` should show the `correlates_to` assertion changing from WARN (count=0) to
PASS (count>0).

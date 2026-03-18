# Python / FastAPI Sample App

Sample application that exercises the CGC OTEL plugin with Python-format FQN conventions. It sends OpenTelemetry spans to an OTLP-compatible collector at `otel-collector:4318`.

## Routes

| Method | Path             | Description        |
|--------|------------------|--------------------|
| GET    | `/api/orders`    | List all orders    |
| POST   | `/api/orders`    | Create a new order |
| GET    | `/health`        | Health check       |

## Call Hierarchy

```
Router (app.routers.orders)
  -> Service (app.services.order_service.OrderService)
    -> Repository (app.repositories.order_repository.OrderRepository)
```

## FQN Format

Python uses dotted module paths throughout, which differs from PHP conventions:

| Attribute          | Python example                                             | PHP equivalent                                    |
|--------------------|------------------------------------------------------------|---------------------------------------------------|
| `code.namespace`   | `app.services.order_service.OrderService`                  | `App\Services\OrderService`                       |
| `code.function`    | `list_orders`                                              | `listOrders`                                      |
| Full FQN           | `app.services.order_service.OrderService.list_orders`      | `App\Services\OrderService::listOrders`           |

Key differences from PHP:
- Python uses `.` as the separator throughout (module path, class, method).
- PHP uses `\` for namespaces and `::` for methods.

## Part of CGC Sample Apps

This sample is part of the CodeGraphContext sample application suite. See `samples/README.md` for the full walkthrough including Docker Compose setup and OTEL collector configuration.

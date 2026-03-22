# CGC Sample: PHP / Laravel

A minimal Laravel 11 application that exercises both the **OTEL** and **Xdebug**
CGC plugins. The app provides a Controller -> Service -> Repository call
hierarchy so that traces and call stacks capture meaningful multi-layer spans.

## Routes

| Method | Path            | Handler                                          |
|--------|-----------------|--------------------------------------------------|
| GET    | `/health`       | `App\Http\Controllers\HealthController::index`   |
| GET    | `/api/orders`   | `App\Http\Controllers\OrderController::index`    |
| POST   | `/api/orders`   | `App\Http\Controllers\OrderController::store`    |

## Call Hierarchy

```
OrderController::index
  -> OrderService::listOrders
    -> OrderRepository::findAll

OrderController::store
  -> OrderService::createOrder
    -> OrderRepository::create
```

## FQN Format

PHP uses `\` as the namespace separator and `::` as the method separator:

```
App\Http\Controllers\OrderController::index
App\Services\OrderService::listOrders
App\Repositories\OrderRepository::findAll
```

## OTEL Span Attributes

The OpenTelemetry auto-instrumentation for Laravel emits spans with:

- `code.namespace` = `App\Http\Controllers\OrderController`
- `code.function` = `index`

These attributes let CGC correlate runtime spans back to the static code graph.

## Triggering Xdebug Traces

Xdebug is configured with `start_with_request=trigger`. To activate a debug
session, include the trigger in your request:

```bash
# Via cookie
curl -b "XDEBUG_TRIGGER=1" http://localhost:8080/api/orders

# Via query parameter
curl "http://localhost:8080/api/orders?XDEBUG_TRIGGER=1"
```

The Xdebug client host is set to `xdebug-listener` (the CGC Xdebug plugin
container) on port 9003.

## Running

This app is intended to run as part of the CGC Docker Compose stack.
See `samples/README.md` for the full walkthrough.

To run standalone for development:

```bash
composer install
php artisan serve --port=8080
```

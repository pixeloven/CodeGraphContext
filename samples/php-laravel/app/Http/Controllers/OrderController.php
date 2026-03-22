<?php

namespace App\Http\Controllers;

use App\Services\OrderService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class OrderController extends Controller
{
    public function __construct(
        private readonly OrderService $orderService,
    ) {}

    /**
     * GET /api/orders
     *
     * Lists all orders. Demonstrates Controller -> Service -> Repository
     * call hierarchy that produces OTEL spans and Xdebug call stacks.
     */
    public function index(): JsonResponse
    {
        $orders = $this->orderService->listOrders();

        return response()->json($orders);
    }

    /**
     * POST /api/orders
     *
     * Creates a new order. Expects JSON body with "product" and "quantity".
     */
    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'product' => 'required|string|max:255',
            'quantity' => 'required|integer|min:1',
        ]);

        $order = $this->orderService->createOrder($data);

        return response()->json($order, 201);
    }
}

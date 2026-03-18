<?php

namespace App\Services;

use App\Repositories\OrderRepository;

class OrderService
{
    public function __construct(
        private readonly OrderRepository $orderRepository,
    ) {}

    /**
     * List all orders.
     *
     * @return array<int, array<string, mixed>>
     */
    public function listOrders(): array
    {
        return $this->orderRepository->findAll();
    }

    /**
     * Create a new order after validation.
     *
     * @param  array{product: string, quantity: int}  $data
     * @return array<string, mixed>
     */
    public function createOrder(array $data): array
    {
        if (empty($data['product'])) {
            throw new \InvalidArgumentException('Product name is required');
        }

        if (($data['quantity'] ?? 0) < 1) {
            throw new \InvalidArgumentException('Quantity must be at least 1');
        }

        return $this->orderRepository->create($data);
    }
}

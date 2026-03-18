<?php

namespace App\Repositories;

use PDO;

class OrderRepository
{
    private PDO $pdo;

    public function __construct()
    {
        $dbPath = database_path('database.sqlite');

        $this->pdo = new PDO("sqlite:{$dbPath}");
        $this->pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $this->pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);

        $this->ensureTableExists();
    }

    /**
     * Create the orders table if it does not exist.
     */
    private function ensureTableExists(): void
    {
        $this->pdo->exec('
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime(\'now\'))
            )
        ');
    }

    /**
     * Fetch all orders.
     *
     * @return array<int, array<string, mixed>>
     */
    public function findAll(): array
    {
        $stmt = $this->pdo->query('SELECT * FROM orders ORDER BY id DESC');

        return $stmt->fetchAll();
    }

    /**
     * Insert a new order and return it.
     *
     * @param  array{product: string, quantity: int}  $data
     * @return array<string, mixed>
     */
    public function create(array $data): array
    {
        $stmt = $this->pdo->prepare(
            'INSERT INTO orders (product, quantity) VALUES (:product, :quantity)'
        );

        $stmt->execute([
            ':product' => $data['product'],
            ':quantity' => $data['quantity'],
        ]);

        $id = $this->pdo->lastInsertId();

        $stmt = $this->pdo->prepare('SELECT * FROM orders WHERE id = :id');
        $stmt->execute([':id' => $id]);

        return $stmt->fetch();
    }
}

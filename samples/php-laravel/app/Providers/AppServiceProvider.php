<?php

namespace App\Providers;

use App\Repositories\OrderRepository;
use App\Services\OrderService;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register application services.
     */
    public function register(): void
    {
        $this->app->singleton(OrderRepository::class);
        $this->app->singleton(OrderService::class);
    }

    /**
     * Bootstrap application services.
     */
    public function boot(): void
    {
        //
    }
}

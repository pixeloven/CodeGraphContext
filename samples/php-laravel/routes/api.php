<?php

use App\Http\Controllers\HealthController;
use App\Http\Controllers\OrderController;
use Illuminate\Support\Facades\Route;

Route::get('/health', [HealthController::class, 'index']);

Route::get('/api/orders', [OrderController::class, 'index']);
Route::post('/api/orders', [OrderController::class, 'store']);

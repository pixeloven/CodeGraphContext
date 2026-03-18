<?php

namespace App\Http\Controllers;

use Illuminate\Http\JsonResponse;

class HealthController extends Controller
{
    /**
     * GET /health
     *
     * Simple health check endpoint.
     */
    public function index(): JsonResponse
    {
        return response()->json(['status' => 'ok']);
    }
}

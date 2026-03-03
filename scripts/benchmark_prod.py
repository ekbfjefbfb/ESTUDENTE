
import asyncio
import httpx
import time
import statistics
from typing import List, Dict

# Configuración - Reemplazar con URL de producción de Render
BASE_URL = "https://mi-backend-super.onrender.com"  # O la URL que el usuario tenga
ENDPOINTS = [
    "/",
    "/api/health",
]

async def benchmark_endpoint(client: httpx.AsyncClient, endpoint: str, iterations: int = 10) -> Dict:
    url = f"{BASE_URL}{endpoint}"
    latencies = []
    status_codes = []
    
    print(f"Benchmarking {endpoint}...")
    
    for _ in range(iterations):
        start_time = time.perf_counter()
        try:
            response = await client.get(url)
            end_time = time.perf_counter()
            latencies.append((end_time - start_time) * 1000)
            status_codes.append(response.status_code)
        except Exception as e:
            print(f"Error connecting to {url}: {e}")
            return {"endpoint": endpoint, "error": str(e)}
            
    return {
        "endpoint": endpoint,
        "avg_ms": statistics.mean(latencies),
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        "p95_ms": statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies),
        "success_rate": status_codes.count(200) / iterations * 100
    }

async def run_benchmarks():
    async with httpx.AsyncClient(timeout=10.0) as client:
        results = []
        for endpoint in ENDPOINTS:
            res = await benchmark_endpoint(client, endpoint)
            results.append(res)
            
        print("\n" + "="*50)
        print("RESULTADOS DE RENDIMIENTO (PRODUCCIÓN)")
        print("="*50)
        for r in results:
            if "error" in r:
                print(f"Endpoint: {r['endpoint']} - ERROR: {r['error']}")
            else:
                print(f"Endpoint: {r['endpoint']}")
                print(f"  Media: {r['avg_ms']:.2f} ms")
                print(f"  Min:   {r['min_ms']:.2f} ms")
                print(f"  Max:   {r['max_ms']:.2f} ms")
                print(f"  Éxito: {r['success_rate']:.1f}%")
        print("="*50)

if __name__ == "__main__":
    try:
        asyncio.run(run_benchmarks())
    except KeyboardInterrupt:
        pass

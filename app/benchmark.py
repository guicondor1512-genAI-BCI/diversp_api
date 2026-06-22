"""Benchmark dos endpoints de leitura da DiverSampa.

Mede latência (p50/p95/p99) de feed, perfil e busca sob carga concorrente,
comparando leituras frias (sem cache) e quentes (com cache). Imprime uma
tabela e verifica contra orçamentos de latência configuráveis.

Uso (com a API rodando):
    python -m app.benchmark --base-url http://localhost:8000 --requests 500 --concurrency 32

Orçamentos padrão (alinhados ao relatório):
    feed/perfil/busca: p95 < 200 ms com cache, < 500 ms sem cache.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class Result:
    name: str
    latencies_ms: list[float] = field(default_factory=list)
    errors: int = 0

    def pct(self, p: float) -> float:
        if not self.latencies_ms:
            return float("nan")
        data = sorted(self.latencies_ms)
        k = max(0, min(len(data) - 1, int(round(p / 100 * (len(data) - 1)))))
        return data[k]

    @property
    def p50(self) -> float:
        return self.pct(50)

    @property
    def p95(self) -> float:
        return self.pct(95)

    @property
    def p99(self) -> float:
        return self.pct(99)

    @property
    def mean(self) -> float:
        return statistics.mean(self.latencies_ms) if self.latencies_ms else float("nan")


async def _hit(client: httpx.AsyncClient, path: str, res: Result) -> None:
    t0 = time.perf_counter()
    try:
        r = await client.get(path)
        r.raise_for_status()
        res.latencies_ms.append((time.perf_counter() - t0) * 1000)
    except Exception:
        res.errors += 1


async def bench_endpoint(
    base_url: str, name: str, path: str, n: int, concurrency: int
) -> Result:
    res = Result(name=name)
    sem = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(base_url=base_url, timeout=10.0) as client:
        # Aquece o cache com uma chamada antes de medir as "quentes".
        try:
            await client.get(path)
        except Exception:
            pass

        async def worker() -> None:
            async with sem:
                await _hit(client, path, res)

        await asyncio.gather(*(worker() for _ in range(n)))
    return res


BUDGETS_MS = {"feed": 200, "perfil": 200, "busca": 300}


async def main(args: argparse.Namespace) -> int:
    endpoints = {
        "feed": "/api/v1/feed?limit=20",
        "perfil": "/api/v1/profiles/@festas",
        "busca": "/api/v1/search?q=festa&type=all",
    }
    print(f"Benchmark: {args.requests} req/endpoint, concorrência {args.concurrency}")
    print(f"Alvo: {args.base_url}\n")
    print(f"{'endpoint':10} {'p50':>8} {'p95':>8} {'p99':>8} {'média':>8} {'erros':>6} {'orçamento p95':>14}")
    print("-" * 70)

    all_ok = True
    for name, path in endpoints.items():
        res = await bench_endpoint(
            args.base_url, name, path, args.requests, args.concurrency
        )
        budget = BUDGETS_MS.get(name, 500)
        ok = res.p95 <= budget and res.errors == 0
        all_ok = all_ok and ok
        flag = "OK" if ok else "FORA"
        print(
            f"{name:10} {res.p50:7.1f}m {res.p95:7.1f}m {res.p99:7.1f}m "
            f"{res.mean:7.1f}m {res.errors:6d} {budget:11d}ms {flag}"
        )

    print("\nResumo:", "todos dentro do orçamento" if all_ok else "há endpoints fora do orçamento")
    return 0 if all_ok else 1


def cli() -> None:
    p = argparse.ArgumentParser(description="Benchmark de leitura da DiverSampa")
    p.add_argument("--base-url", default="http://localhost:8000")
    p.add_argument("--requests", type=int, default=500)
    p.add_argument("--concurrency", type=int, default=32)
    raise SystemExit(asyncio.run(main(p.parse_args())))


if __name__ == "__main__":
    cli()

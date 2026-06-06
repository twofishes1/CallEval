"""Export static /api/eval1 responses for Cloudflare Pages demo mode."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval1.analysis_service import build_layer1_analysis, list_eval1_datasets  # noqa: E402
from eval1.bot_provider import (  # noqa: E402
    BOT_PROVIDER_DEEPSEEK,
    BOT_PROVIDER_QWEN,
    list_available_report_providers,
    reports_output_path,
)
from eval1.pipeline.orchestrator import enrich_eval_payload  # noqa: E402


def snapshot_key(path: str, **query: str | int | bool | None) -> str:
    items = [
        (k, v)
        for k, v in query.items()
        if v not in (None, "", False, 0, "false", "0")
    ]
    if not items:
        return path
    qs = "&".join(f"{quote(str(k))}={quote(str(v))}" for k, v in sorted(items))
    return f"{path}?{qs}"


def put(out: dict[str, object], path: str, value: object, **query: object) -> None:
    out[snapshot_key(path, **query)] = value


async def main() -> None:
    out: dict[str, object] = {}
    datasets = list_eval1_datasets()
    put(out, "/api/eval1/datasets", datasets)

    for dataset in datasets:
        dataset_id = dataset["dataset_id"]
        layer1 = await build_layer1_analysis(dataset_id)
        put(out, f"/api/eval1/layer1/{dataset_id}", layer1)

        providers = list_available_report_providers(dataset_id)
        put(
            out,
            f"/api/eval1/reports/{dataset_id}/providers",
            {"dataset_id": dataset_id, "providers": providers},
        )

        for provider in (BOT_PROVIDER_QWEN, BOT_PROVIDER_DEEPSEEK):
            report_path = reports_output_path(dataset_id, provider)
            if not report_path.exists():
                continue
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            enriched = enrich_eval_payload(payload, layer1=layer1)
            enriched["bot_provider"] = provider
            enriched["report_file"] = report_path.name
            put(out, f"/api/eval1/layer2/{dataset_id}", enriched, bot_provider=provider)

    dest = ROOT / "frontend" / "public" / "demo-eval1-api.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)} with {len(out)} responses")


if __name__ == "__main__":
    asyncio.run(main())

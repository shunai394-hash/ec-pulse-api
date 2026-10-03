from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field, HttpUrl

from app.main import get_api_key, _charge, _refund, _set_usage_headers
from app.services.consumer_insights import analyze_comments
from app.services.monitor_store import save_research_run
from app.services.research_ingest import fetch_public_comments
from app.services.url_safety import validate_public_url


class ResearchBatchRequest(BaseModel):
    urls: list[HttpUrl] = Field(min_length=1, max_length=20)
    max_comments_per_url: int = Field(default=500, ge=1, le=500)


def _aggregate_pains(results: list[dict]) -> list[dict]:
    aggregated: dict[str, dict] = {}
    for item in results:
        analysis = item.get("analysis") or {}
        source = item.get("source") or "unknown"
        market = item.get("market") or "GLOBAL"
        for pain in analysis.get("pain_points", []):
            label = pain.get("pain")
            count = int(pain.get("count", 0))
            if not label:
                continue
            row = aggregated.setdefault(
                label,
                {"pain": label, "count": 0, "sources": set(), "markets": set()},
            )
            row["count"] += count
            row["sources"].add(source)
            row["markets"].add(market)

    rows = []
    for row in aggregated.values():
        rows.append(
            {
                "pain": row["pain"],
                "count": row["count"],
                "source_count": len(row["sources"]),
                "sources": sorted(row["sources"]),
                "markets": sorted(row["markets"]),
            }
        )
    return sorted(rows, key=lambda x: (-x["count"], -x["source_count"], x["pain"]))


def register_research_batch_routes(app: FastAPI):
    @app.post("/v1/research/batch")
    async def research_batch(
        request: ResearchBatchRequest,
        request_http: Request,
        response: Response,
        api_key: str = Depends(get_api_key),
    ):
        for url in request.urls:
            try:
                await validate_public_url(str(url))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid public URL: {exc}") from exc
        charge = _charge(api_key, "POST /v1/research/batch", len(request.urls))

        results = []
        for url in request.urls:
            try:
                item = await fetch_public_comments(
                    str(url), request.max_comments_per_url
                )
                if item["comments"]:
                    item["analysis"] = analyze_comments(
                        item["comments"], item["source"], item.get("locale")
                    )
                    try:
                        item["trend"] = save_research_run(
                            api_key, item, item["analysis"]
                        )
                    except Exception as exc:
                        item["trend"] = {
                            "signal": "persistence_error",
                            "error": type(exc).__name__,
                        }
                else:
                    item["analysis"] = {
                        "comments_analyzed": 0,
                        "pain_points": [],
                        "top_terms": [],
                        "recommended_angle": None,
                    }
                results.append(item)
            except Exception as exc:
                results.append(
                    {
                        "url": str(url),
                        "ok": False,
                        "error": type(exc).__name__,
                    }
                )

        charge = _refund(api_key, "POST /v1/research/batch", sum(1 for item in results if item.get("ok") is False), charge)
        _set_usage_headers(response, request_http, api_key, charge)
        successful = [item for item in results if item.get("analysis")]
        total_comments = sum(
            item.get("analysis", {}).get("comments_analyzed", 0)
            for item in successful
        )

        markets: dict[str, dict] = {}
        for item in successful:
            market = item.get("market") or "GLOBAL"
            bucket = markets.setdefault(
                market, {"urls": 0, "comments": 0, "sources": set()}
            )
            bucket["urls"] += 1
            bucket["comments"] += item.get("analysis", {}).get(
                "comments_analyzed", 0
            )
            if item.get("source"):
                bucket["sources"].add(item["source"])

        for bucket in markets.values():
            bucket["sources"] = sorted(bucket["sources"])

        rising_pains: dict[str, dict] = {}
        for item in successful:
            trend = item.get("trend") or {}
            for pain in trend.get("emerging_pains", []):
                label = pain.get("pain")
                if not label:
                    continue
                row = rising_pains.setdefault(
                    label,
                    {
                        "pain": label,
                        "count_delta": 0,
                        "share_delta_percent": 0.0,
                        "runs": 0,
                    },
                )
                row["count_delta"] += pain.get("count_delta", 0)
                row["share_delta_percent"] += pain.get(
                    "share_delta_percent", 0
                )
                row["runs"] += 1

        return {
            "count": len(results),
            "successful": len(successful),
            "failed": len(results) - len(successful),
            "credits": charge,
            "summary": {
                "comments_analyzed": total_comments,
                "top_pains": _aggregate_pains(results)[:15],
                "rising_pains": sorted(
                    rising_pains.values(),
                    key=lambda x: (
                        -x["runs"],
                        -x["count_delta"],
                        -x["share_delta_percent"],
                    ),
                )[:15],
                "markets": markets,
            },
            "results": results,
        }

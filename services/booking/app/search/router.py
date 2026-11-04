from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from app.cache import ResponseCache, cache_key
from app.db import SessionDep
from app.pagination import Page
from app.ratelimit import LimitPerClient
from app.search import service
from app.search.schemas import SearchParams, SearchResult

router = APIRouter(prefix="/api/v1/listings", tags=["search"])


@router.get(
    "",
    response_model=Page[SearchResult],
    dependencies=[Depends(LimitPerClient("search"))],
)
async def search_listings(
    request: Request, session: SessionDep, params: Annotated[SearchParams, Query()]
) -> Response:
    """Bookable listings on the map, by filters and free dates.

    Results may be up to `Cache-Control: max-age` seconds old; the price and the dates are
    always checked again when booking.
    """
    ttl: int = request.app.state.settings.search_cache_seconds
    cache: ResponseCache = request.app.state.cache
    key = cache_key("search:v1", params.model_dump(mode="json"))

    body = await cache.get(key) if ttl else None
    status = "HIT" if body is not None else "MISS"
    if body is None:
        body = (await service.search(session, params)).model_dump_json().encode()
        if ttl:
            await cache.set(key, body, ttl)
    return Response(
        body,
        media_type="application/json",
        headers={"Cache-Control": f"public, max-age={ttl}", "X-Cache": status},
    )

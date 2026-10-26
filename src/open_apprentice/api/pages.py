"""Product page: Tavily Extract reads the owner's page, Nemotron lifts grounded facts and drafts copy, a deterministic check compares the banner with the page (see docs/superpowers/specs/2026-10-26-sketch-to-banner-design.md)."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from open_apprentice.api.campaign import _account, _model, _rate_limit, _ws
from open_apprentice.api.v2.routes import client_key
from open_apprentice.campaign.copy import draft_copy
from open_apprentice.campaign.facts import baseline_facts, extract_facts
from open_apprentice.campaign.pages import PageError, validate_page_url
from open_apprentice.evaluation.page_check import check_page

router = APIRouter(prefix="/api/campaign", tags=["campaign"])

PAGE_REQUESTS_PER_HOUR = 6  # per address: every page is a paid Tavily call plus two Nemotron calls
MAX_PAGES = 3  # per workspace: the page text is held in memory until the workspace expires


class PageIn(BaseModel):
    url: str = Field(
        max_length=2000
    )  # validate_page_url gives the plain-language 300-character message
    # False: the banner door only wants a price check, so no model call is made (alias: `copy` shadows BaseModel.copy)
    want_copy: bool = Field(default=True, alias="copy")


class PageCheckIn(BaseModel):
    banner_id: str = Field(max_length=40)
    page_id: str = Field(max_length=40)


def _page_quota(request: Request) -> bool:
    now, hits = time.time(), request.app.state.rate.setdefault(
        (client_key(request), "campaign_page"), []
    )
    hits[:] = [t for t in hits if now - t < 3600]
    if len(hits) >= PAGE_REQUESTS_PER_HOUR:
        return False
    hits.append(now)
    return True


@router.post("/workspaces/{wid}/pages")
async def read_page(request: Request, wid: str, body: PageIn) -> dict:
    """Tavily reads the page, Nemotron proposes facts and headlines, deterministic checks keep only what the page says."""
    _rate_limit(request, "campaign")
    ws = _ws(request, wid)
    try:
        url = validate_page_url(body.url)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    fetcher = getattr(request.app.state, "page_fetcher", None)
    async with ws.lock:
        if len(ws.pages) >= MAX_PAGES:
            raise HTTPException(
                409, f"a workspace holds {MAX_PAGES} pages at most; start a new one"
            )
        if not _page_quota(request):
            raise HTTPException(
                429,
                f"reading pages is limited to {PAGE_REQUESTS_PER_HOUR} per hour per address on this demo; try again later",
            )
        if fetcher is None:
            raise HTTPException(
                502, "The page could not be read: no page reader is configured on this server."
            )
        try:
            page = await fetcher.fetch(url)
        except PageError as e:
            msg = str(e)
            raise HTTPException(502, msg[:1].upper() + msg[1:]) from e
        if body.want_copy:
            provider, notes = _model(request, ws)
            try:
                facts = await extract_facts(provider, ws.ledger, page.text)
                copy = await draft_copy(provider, ws.ledger, facts, facts.language, page.text)
            finally:
                _account(request, ws)
            out_copy = copy.as_dict()
        else:
            notes, facts = [], baseline_facts(page.text)
            price = facts.prices[0]["text"] if facts.prices else None
            out_copy = {
                "origin": "template",
                "options": [],
                "price": price,
                "cta": "",
                "legal": "",
                "problems": [],
            }
        pid = uuid.uuid4().hex[:12]
        out_facts = facts.as_dict()
        ws.pages[pid] = {"url": url, "text": page.text, "facts": out_facts, "copy": out_copy}
    return {
        "page_id": pid,
        "url": url,
        "title": page.title,
        "chars": len(page.text),
        "origin": page.origin,
        "language": facts.language,
        "facts": out_facts,
        "copy": out_copy,
        "problems": facts.problems,
        "note": " ".join(notes),
    }


@router.post("/workspaces/{wid}/page-check")
async def page_check(request: Request, wid: str, body: PageCheckIn) -> dict:
    """Advisory: the banner's price against the prices on the page. Never blocks a run."""
    _rate_limit(request, "campaign")
    ws = _ws(request, wid)
    banner, page = ws.banners.get(body.banner_id), ws.pages.get(body.page_id)
    if banner is None:
        raise HTTPException(404, "unknown or expired banner")
    if page is None:
        raise HTTPException(404, "unknown or expired page")
    return check_page(banner["scene"], page["text"])

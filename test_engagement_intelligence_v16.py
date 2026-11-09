import asyncio
import json
import httpx
import pytest

from services.engagement_intelligence_engine import (
    build_intelligence_payload, dispatch_engagement_intelligence, event_id,
)


def test_payload_is_human_review_only_and_stable():
    a = build_intelligence_payload(platform="LinkedIn", post_id="urn:post:1", post_url="https://example.test/p", approval_id=4)
    b = build_intelligence_payload(platform="linkedin", post_id="urn:post:1", post_url="https://example.test/p", approval_id=4)
    assert a["event_id"] == b["event_id"] == event_id("linkedin", "urn:post:1", 4)
    assert a["workflow"]["comment_suggestions"] == "human_review_only"
    assert a["workflow"]["reactions_and_comments"] == "human_action_required"
    assert a["workflow"]["engagement_pods"] == "prohibited"


def test_payload_requires_platform_and_post():
    with pytest.raises(ValueError):
        build_intelligence_payload(platform="", post_id="p", post_url=None, approval_id=1)


@pytest.mark.parametrize("enabled", ["false", "0", ""])
def test_disabled_returns_without_dispatch(monkeypatch, enabled):
    monkeypatch.setenv("ENGAGEMENT_INTELLIGENCE_ENABLED", enabled)
    result = asyncio.run(dispatch_engagement_intelligence(
        platform="linkedin", post_id="p", post_url=None, approval_id=1,
    ))
    assert result["status"] == "skipped"


def test_successful_webhook_has_signature_and_idempotency(monkeypatch):
    monkeypatch.setenv("ENGAGEMENT_INTELLIGENCE_ENABLED", "true")
    monkeypatch.setenv("ENGAGEMENT_INTELLIGENCE_WEBHOOK_URL", "https://hooks.example.test/events")
    monkeypatch.setenv("ENGAGEMENT_INTELLIGENCE_WEBHOOK_SECRET", "test-secret")
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(202)
    transport = httpx.MockTransport(handler)
    result = asyncio.run(dispatch_engagement_intelligence(
        platform="linkedin", post_id="p1", post_url="https://linkedin.test/p1",
        approval_id=42, transport=transport,
    ))
    assert result["status"] == "delivered"
    assert seen[0].headers["Idempotency-Key"] == result["event_id"]
    assert seen[0].headers["X-TAPAS-Signature"].startswith("sha256=")
    assert json.loads(seen[0].content)["post_id"] == "p1"


def test_webhook_retries_and_reports_failure(monkeypatch):
    monkeypatch.setenv("ENGAGEMENT_INTELLIGENCE_ENABLED", "true")
    monkeypatch.setenv("ENGAGEMENT_INTELLIGENCE_WEBHOOK_URL", "https://hooks.example.test/events")
    monkeypatch.setenv("ENGAGEMENT_INTELLIGENCE_WEBHOOK_SECRET", "test-secret")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503)
    result = asyncio.run(dispatch_engagement_intelligence(
        platform="x", post_id="x-1", post_url=None, approval_id=8,
        transport=httpx.MockTransport(handler), attempts=3,
    ))
    assert len(calls) == 3
    assert result["status"] == "failed"
    assert result["attempts"] == 3


def test_rejects_non_https_webhook(monkeypatch):
    monkeypatch.setenv("ENGAGEMENT_INTELLIGENCE_ENABLED", "true")
    monkeypatch.setenv("ENGAGEMENT_INTELLIGENCE_WEBHOOK_URL", "http://unsafe.test")
    monkeypatch.setenv("ENGAGEMENT_INTELLIGENCE_WEBHOOK_SECRET", "secret")
    result = asyncio.run(dispatch_engagement_intelligence(
        platform="x", post_id="p", post_url=None, approval_id=1,
    ))
    assert result["status"] == "failed"

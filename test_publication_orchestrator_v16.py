import pytest
from services.publication_orchestrator_v16 import plan_distribution


def test_requires_confirmed_publication():
    with pytest.raises(ValueError, match="publication_must_be_confirmed_published"):
        plan_distribution({"publication_id": "p1", "status": "draft"})


def test_idempotent_tasks_and_review_gates():
    event = {"publication_id": "pub-123", "status": "published"}
    a = plan_distribution(event, ["linkedin_profile", "x"])
    b = plan_distribution(event, ["x", "linkedin_profile"])
    assert a["idempotency_key"] == b["idempotency_key"]
    assert [t["task_id"] for t in a["tasks"]] == [t["task_id"] for t in b["tasks"]]
    assert all(t["approval_required"] for t in a["tasks"])
    assert all(t["status"] == "human_review_queue" for t in a["tasks"] if t["action"] in {"comment", "reaction", "share"})


def test_paid_campaign_needs_explicit_approval():
    event = {"publication_id": "pub-123", "status": "published"}
    pending = plan_distribution(event, ["youtube"], include_paid=True)
    paid = next(t for t in pending["tasks"] if t["action"] == "paid_promotion")
    assert paid["status"] == "approval_required"
    assert paid["approval_required"] is True
    approved = plan_distribution(event, ["youtube"], include_paid=True, paid_approved=True)
    paid2 = next(t for t in approved["tasks"] if t["action"] == "paid_promotion")
    assert paid2["status"] == "approved_to_queue"


def test_unknown_channel_fails_closed():
    with pytest.raises(ValueError, match="unsupported_channels"):
        plan_distribution({"publication_id": "p1", "status": "published"}, ["telegram_fake"])


def test_requires_publication_id():
    with pytest.raises(ValueError, match="publication_id_required"):
        plan_distribution({"status": "published"})

from app.outbox import PendingMap
from app.models import FeedbackRequest


def test_pending_feedback_and_actor_survive_reopen_without_replaying_actions(tmp_path):
    path = str(tmp_path / "outbox.db")
    first = PendingMap(path, "feedback")
    actors = PendingMap(path, "actors")
    actors["f1"] = {"label": "Operator", "owner": False}
    first["f1"] = [FeedbackRequest(category="dashboard_change", feedback="Show source dates").model_dump(), ""]
    reopened = PendingMap(path, "feedback")
    assert reopened["f1"][0]["feedback"] == "Show source dates"
    assert PendingMap(path, "actors")["f1"]["owner"] is False
    reopened.pop("f1")
    assert len(PendingMap(path, "feedback")) == 0
    assert "f1" in actors

from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts import sync_github_backlog


def issue(
    number: int,
    title: str,
    state: str,
    *,
    body: str | None = None,
    children: int = 0,
) -> dict:
    closed_at = "2026-08-28T12:00:00Z" if state == "closed" else None
    return {
        "number": number,
        "title": title,
        "state": state,
        "state_reason": "completed" if state == "closed" else None,
        "body": body,
        "html_url": f"https://github.com/example/project/issues/{number}",
        "user": {"login": "author"},
        "assignees": [],
        "labels": [],
        "milestone": None,
        "created_at": "2026-08-28T10:00:00Z",
        "updated_at": "2026-08-28T12:00:00Z",
        "closed_at": closed_at,
        "sub_issues_summary": {"total": children},
    }


class RenderBacklogTest(unittest.TestCase):
    def test_includes_closed_issues_comments_history_and_hierarchy(self) -> None:
        parent = issue(1, "Planejamento <script>", "open", children=1)
        child = issue(2, "Implementar", "closed", body="<script>nao executar</script>")
        comment = {
            "issue_url": "https://api.github.com/repos/example/project/issues/2",
            "html_url": "https://github.com/example/project/issues/2#issuecomment-1",
            "body": "Verificacao concluida",
            "user": {"login": "reviewer"},
            "created_at": "2026-08-28T11:00:00Z",
            "updated_at": "2026-08-28T11:00:00Z",
        }
        event = {
            "issue": {"number": 2},
            "event": "closed",
            "actor": {"login": "reviewer"},
            "created_at": "2026-08-28T12:00:00Z",
        }

        def fake_api_list(_repository: str, resource: str) -> list[dict]:
            if resource.startswith("issues?state=all"):
                return [parent, child]
            if resource.startswith("issues/comments"):
                return [comment]
            if resource.startswith("issues/events"):
                return [event]
            if resource.startswith("issues/1/sub_issues"):
                return [child]
            raise AssertionError(f"recurso inesperado: {resource}")

        with patch.object(sync_github_backlog, "api_list", side_effect=fake_api_list):
            result = sync_github_backlog.render("example/project")

        self.assertIn("- **Abertas:** 1", result)
        self.assertIn("- **Fechadas:** 1", result)
        self.assertIn("#2 — Implementar", result)
        self.assertIn("**Issue-pai:** [#1 — Planejamento &lt;script&gt;]", result)
        self.assertIn("**Sub-issues:** [#2 — Implementar]", result)
        self.assertIn("Comentarios (1)", result)
        self.assertIn("fechada por @reviewer", result)
        self.assertIn("&lt;script&gt;nao executar&lt;/script&gt;", result)
        self.assertNotIn("<script>nao executar</script>", result)
        self.assertNotIn("Planejamento <script>", result)


if __name__ == "__main__":
    unittest.main()

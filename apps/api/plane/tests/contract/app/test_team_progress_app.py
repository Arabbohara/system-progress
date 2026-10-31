# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Team progress page, "my active projects" on Home, and the scheduled Slack report."""

from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.bgtasks.slack_report_task import build_slack_payload, is_report_due, send_due_slack_reports
from plane.db.models import (
    Issue,
    IssueAssignee,
    Project,
    ProjectMember,
    State,
    User,
    WorkspaceMember,
    WorkspaceSlackReport,
)
from plane.license.utils.encryption import encrypt_data
from plane.utils.team_progress import build_team_progress, resolve_period

WEBHOOK = "https://hooks.slack.com/services/T000/B000/XXXXXXXX"


def _make_user(email: str) -> User:
    local_part = email.split("@")[0]
    user = User.objects.create(email=email, username=local_part, first_name=local_part)
    user.set_password("test-password")
    user.save()
    return user


def _client(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def member_user(db, workspace):
    user = _make_user("progress-member@vegecoop.co.jp")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=15, is_active=True)
    return user


@pytest.fixture
def project(db, workspace, create_user, member_user):
    project = Project.objects.create(
        name="Sales", identifier="SAL", workspace=workspace, created_by=create_user, progress=40
    )
    ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20, is_active=True)
    ProjectMember.objects.create(workspace=workspace, project=project, member=member_user, role=15, is_active=True)
    return project


@pytest.fixture
def states(db, workspace, project):
    return {
        group: State.objects.create(name=group, project=project, workspace=workspace, group=group)
        for group in ("backlog", "started", "completed")
    }


def _issue(workspace, project, state, assignee=None, **fields):
    issue = Issue.objects.create(name="Issue", workspace=workspace, project=project, state=state, **fields)
    if assignee:
        IssueAssignee.objects.create(issue=issue, assignee=assignee, project=project, workspace=workspace)
    return issue


@pytest.mark.contract
@pytest.mark.django_db
class TestTeamProgress:
    def test_counts_per_member_and_project(self, workspace, project, states, member_user):
        _issue(workspace, project, states["started"], member_user)
        _issue(
            workspace, project, states["backlog"], member_user, target_date=timezone.now().date() - timedelta(days=2)
        )
        _issue(workspace, project, states["completed"], member_user)
        old = _issue(workspace, project, states["completed"], member_user)
        Issue.objects.filter(pk=old.pk).update(completed_at=timezone.now() - timedelta(days=30))
        _issue(workspace, project, states["started"])  # unassigned

        response = _client(workspace.owner).get(f"/api/workspaces/{workspace.slug}/team-progress/")

        assert response.status_code == status.HTTP_200_OK
        member = next(row for row in response.data["members"] if row["member_id"] == member_user.id)
        assert member["totals"] == {
            "backlog": 1,
            "unstarted": 0,
            "started": 1,
            "overdue": 1,
            "completed": 1,
            "created": 4,
            "updated": 4,
        }
        assert member["projects"][0]["name"] == "Sales"
        assert member["projects"][0]["progress"] == 40
        assert response.data["summary"]["started"] == 2
        assert response.data["summary"]["completed"] == 1
        assert response.data["projects"][0]["started"] == 2

    def test_period_filter_counts_older_completions(self, workspace, project, states, member_user):
        old = _issue(workspace, project, states["completed"], member_user)
        Issue.objects.filter(pk=old.pk).update(completed_at=timezone.now() - timedelta(days=20))
        today = timezone.now().date()

        response = _client(workspace.owner).get(
            f"/api/workspaces/{workspace.slug}/team-progress/",
            {"start_date": (today - timedelta(days=29)).isoformat(), "end_date": today.isoformat()},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["summary"]["completed"] == 1

    def test_invalid_period_is_rejected(self, workspace):
        response = _client(workspace.owner).get(
            f"/api/workspaces/{workspace.slug}/team-progress/",
            {"start_date": "2026-10-10", "end_date": "2026-10-01"},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_members_cannot_see_team_progress(self, workspace, member_user):
        response = _client(member_user).get(f"/api/workspaces/{workspace.slug}/team-progress/")

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_my_project_progress(self, workspace, project, states, member_user):
        _issue(workspace, project, states["started"], member_user)
        _issue(workspace, project, states["started"], workspace.owner)

        response = _client(member_user).get(f"/api/workspaces/{workspace.slug}/my-project-progress/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == [{"project_id": project.id, "backlog": 0, "unstarted": 0, "started": 1, "overdue": 0}]


@pytest.mark.contract
@pytest.mark.django_db
class TestSlackReport:
    def test_settings_store_encrypted_url_and_mask_it(self, workspace):
        client = _client(workspace.owner)

        response = client.patch(
            f"/api/workspaces/{workspace.slug}/slack-report/",
            {"webhook_url": WEBHOOK, "is_enabled": True, "frequency": "weekly", "weekday": 4, "hour": 17},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["webhook_configured"] is True
        assert WEBHOOK not in str(response.data)
        report = WorkspaceSlackReport.objects.get(workspace=workspace)
        assert report.webhook_url != WEBHOOK
        assert (report.weekday, report.hour, report.is_enabled) == (4, 17, True)

    def test_rejects_non_slack_url(self, workspace):
        response = _client(workspace.owner).patch(
            f"/api/workspaces/{workspace.slug}/slack-report/",
            {"webhook_url": "https://example.com/hook"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_cannot_enable_without_url(self, workspace):
        response = _client(workspace.owner).patch(
            f"/api/workspaces/{workspace.slug}/slack-report/", {"is_enabled": True}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_members_cannot_change_settings(self, workspace, member_user):
        response = _client(member_user).patch(
            f"/api/workspaces/{workspace.slug}/slack-report/", {"webhook_url": WEBHOOK}, format="json"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_send_now_posts_to_webhook(self, workspace, project, states, member_user):
        _issue(workspace, project, states["started"], member_user)
        _issue(
            workspace, project, states["backlog"], member_user, target_date=timezone.now().date() - timedelta(days=3)
        )
        WorkspaceSlackReport.objects.create(workspace=workspace, webhook_url=encrypt_data(WEBHOOK))

        with mock.patch("plane.bgtasks.slack_report_task.requests.post") as post:
            post.return_value.status_code = 200
            response = _client(workspace.owner).post(
                f"/api/workspaces/{workspace.slug}/slack-report/send/", {}, format="json"
            )

        assert response.status_code == status.HTTP_200_OK
        assert post.call_args.args[0] == WEBHOOK
        text = str(post.call_args.kwargs["json"])
        assert "Sales" in text
        assert "progress-member" in text
        # Overdue work items are listed with how late they are
        assert "SAL-2" in text
        assert "3日超過" in text

    def test_send_now_reports_slack_errors(self, workspace):
        WorkspaceSlackReport.objects.create(workspace=workspace, webhook_url=encrypt_data(WEBHOOK))

        with mock.patch("plane.bgtasks.slack_report_task.requests.post") as post:
            post.return_value.status_code = 404
            post.return_value.text = "no_service"
            response = _client(workspace.owner).post(
                f"/api/workspaces/{workspace.slug}/slack-report/send/", {}, format="json"
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "404" in response.data["error"]

    def test_schedule(self, workspace):
        workspace.timezone = "Asia/Tokyo"
        workspace.save()
        report = WorkspaceSlackReport(workspace=workspace, frequency="weekly", weekday=0, hour=9)
        tokyo = ZoneInfo("Asia/Tokyo")
        monday_9 = datetime(2026, 11, 2, 9, 5, tzinfo=tokyo)

        assert is_report_due(report, monday_9) is True
        assert is_report_due(report, monday_9 - timedelta(hours=1)) is False
        assert is_report_due(report, monday_9 + timedelta(days=1)) is False
        report.last_sent_at = monday_9
        assert is_report_due(report, monday_9 + timedelta(hours=3)) is False

        report.frequency = "monthly"
        report.last_sent_at = None
        assert is_report_due(report, datetime(2026, 11, 1, 10, 0, tzinfo=tokyo)) is True
        assert is_report_due(report, datetime(2026, 11, 2, 10, 0, tzinfo=tokyo)) is False

    def test_scheduled_task_sends_once(self, workspace):
        WorkspaceSlackReport.objects.create(
            workspace=workspace, webhook_url=encrypt_data(WEBHOOK), is_enabled=True, frequency="daily", hour=0
        )

        with mock.patch("plane.bgtasks.slack_report_task.requests.post") as post:
            post.return_value.status_code = 200
            send_due_slack_reports()
            send_due_slack_reports()

        assert post.call_count == 1
        assert WorkspaceSlackReport.objects.get(workspace=workspace).last_sent_at is not None

    def test_payload_fits_slack_limits(self, workspace, project, states, member_user):
        for _ in range(3):
            _issue(workspace, project, states["started"], member_user)
        start, end = resolve_period(workspace)

        payload = build_slack_payload(workspace, build_team_progress(workspace, start, end))

        assert len(payload["blocks"]) <= 50
        for block in payload["blocks"]:
            if block["type"] == "section" and "text" in block:
                assert len(block["text"]["text"]) <= 3000
        # Slack allows one table per message, at most 100 rows of 20 cells
        tables = [block for block in payload["blocks"] if block["type"] == "table"]
        assert len(tables) == 1
        assert len(tables[0]["rows"]) <= 100
        assert all(len(row) <= 20 for row in tables[0]["rows"])
        # Slack answers invalid_blocks to null column settings
        assert None not in tables[0]["column_settings"]
        assert "Sales" in str(tables[0]["rows"])

    def test_payload_leaves_out_projects_without_activity(self, workspace, project, states, member_user, create_user):
        _issue(workspace, project, states["started"], member_user)
        # Finished the month before and untouched since
        idle = Project.objects.create(name="Finished", identifier="FIN", workspace=workspace, created_by=create_user)
        idle_state = State.objects.create(name="done", project=idle, workspace=workspace, group="completed")
        done = _issue(workspace, idle, idle_state, member_user)
        long_ago = timezone.now() - timedelta(days=30)
        Issue.objects.filter(pk=done.pk).update(completed_at=long_ago, created_at=long_ago, updated_at=long_ago)
        start, end = resolve_period(workspace)

        payload = build_slack_payload(workspace, build_team_progress(workspace, start, end))

        table = next(block for block in payload["blocks"] if block["type"] == "table")
        assert "Sales" in str(table["rows"])
        assert "Finished" not in str(payload)

    def test_link_points_at_the_web_app(self, workspace, settings):
        settings.APP_BASE_URL = "http://app.example.com"
        settings.WEB_URL = "http://api.example.com"
        start, end = resolve_period(workspace)

        payload = build_slack_payload(workspace, build_team_progress(workspace, start, end))

        assert f"http://app.example.com/{workspace.slug}/team-progress/" in str(payload)

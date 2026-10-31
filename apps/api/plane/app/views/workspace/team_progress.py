# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.bgtasks.slack_report_task import (
    SLACK_WEBHOOK_PREFIX,
    SlackReportError,
    report_period,
    send_slack_report,
)
from plane.db.models import Workspace, WorkspaceSlackReport
from plane.license.utils.encryption import decrypt_data, encrypt_data
from plane.utils.team_progress import (
    build_member_project_progress,
    build_team_progress,
    resolve_period,
    workspace_zone,
)


class TeamProgressEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def get(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        try:
            start, end = resolve_period(
                workspace, request.query_params.get("start_date"), request.query_params.get("end_date")
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(build_team_progress(workspace, start, end), status=status.HTTP_200_OK)


class MyProjectProgressEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST], level="WORKSPACE")
    def get(self, request, slug):
        workspace = Workspace.objects.get(slug=slug)
        return Response(build_member_project_progress(workspace, request.user), status=status.HTTP_200_OK)


def _mask(webhook_url):
    return f"{webhook_url[:34]}…{webhook_url[-4:]}" if webhook_url else ""


def _serialize_slack_report(report):
    webhook_url = decrypt_data(report.webhook_url)
    return {
        "is_enabled": report.is_enabled,
        "frequency": report.frequency,
        "weekday": report.weekday,
        "hour": report.hour,
        "last_sent_at": report.last_sent_at,
        "webhook_configured": bool(webhook_url),
        "webhook_url_masked": _mask(webhook_url),
    }


class SlackReportSettingEndpoint(BaseAPIView):
    def _get_report(self, slug):
        workspace = Workspace.objects.get(slug=slug)
        report, _ = WorkspaceSlackReport.objects.get_or_create(workspace=workspace)
        return report

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def get(self, request, slug):
        return Response(_serialize_slack_report(self._get_report(slug)), status=status.HTTP_200_OK)

    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def patch(self, request, slug):
        report = self._get_report(slug)
        data = request.data

        if "webhook_url" in data:
            webhook_url = (data["webhook_url"] or "").strip()
            if webhook_url and not webhook_url.startswith(SLACK_WEBHOOK_PREFIX):
                return Response(
                    {"error": "The webhook URL must start with https://hooks.slack.com/"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            report.webhook_url = encrypt_data(webhook_url) if webhook_url else ""
        if "is_enabled" in data:
            if not isinstance(data["is_enabled"], bool):
                return Response({"error": "`is_enabled` must be a boolean"}, status=status.HTTP_400_BAD_REQUEST)
            report.is_enabled = data["is_enabled"]
        if "frequency" in data:
            if data["frequency"] not in WorkspaceSlackReport.Frequency.values:
                return Response({"error": "Invalid frequency"}, status=status.HTTP_400_BAD_REQUEST)
            report.frequency = data["frequency"]
        for field, upper in (("weekday", 6), ("hour", 23)):
            if field in data:
                value = data[field]
                if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= upper:
                    return Response({"error": f"`{field}` must be 0-{upper}"}, status=status.HTTP_400_BAD_REQUEST)
                setattr(report, field, value)

        if report.is_enabled and not report.webhook_url:
            return Response(
                {"error": "Set a Slack webhook URL before enabling the report"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        report.save()
        return Response(_serialize_slack_report(report), status=status.HTTP_200_OK)


class SlackReportSendEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN], level="WORKSPACE")
    def post(self, request, slug):
        """Send the report now, for the given period or the report's own period ending today."""
        workspace = Workspace.objects.get(slug=slug)
        report, _ = WorkspaceSlackReport.objects.get_or_create(workspace=workspace)
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        try:
            if start_date or end_date:
                start, end = resolve_period(workspace, start_date, end_date)
            else:
                start, end = report_period(report, timezone.now().astimezone(workspace_zone(workspace)).date())
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            send_slack_report(report, start, end)
        except SlackReportError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"start_date": start.isoformat(), "end_date": end.isoformat()}, status=status.HTTP_200_OK)

# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Scheduled progress reports posted to a Slack incoming webhook."""

# Python imports
import logging
from datetime import date, timedelta

# Third party imports
import requests
from celery import shared_task

# Django imports
from django.conf import settings
from django.utils import timezone

# Module imports
from plane.db.models import Issue, WorkspaceSlackReport
from plane.license.utils.encryption import decrypt_data
from plane.utils.exception_logger import log_exception
from plane.utils.team_progress import workspace_zone, build_team_progress

logger = logging.getLogger("plane.worker")

SLACK_WEBHOOK_PREFIX = "https://hooks.slack.com/"
PERIOD_DAYS = {"daily": 1, "weekly": 7, "monthly": 30}
FREQUENCY_LABELS = {"daily": "日次", "weekly": "週次", "monthly": "月次"}
# Keeps the table and the member list well inside Slack's size limits
MAX_MEMBERS = 20
MAX_PROJECTS = 20


class SlackReportError(Exception):
    pass


WEEKDAYS = "月火水木金土日"
OVERDUE_ITEMS = 5
# Assignee names shown per project row before "ほか N 名"
MAX_ASSIGNEES = 4
PROJECT_COLUMNS = ["プロジェクト", "進捗", "完了", "進行中", "残り", "期限切れ", "担当者"]


def _progress_bar(percent):
    filled = round(max(0, min(percent, 100)) / 10)
    return "■" * filled + "□" * (10 - filled) + f" {percent}%"


def _member_name(member):
    full_name = f"{member['first_name'] or ''} {member['last_name'] or ''}".strip()
    return full_name or member["display_name"]


def _open_count(counts):
    return counts["backlog"] + counts["unstarted"] + counts["started"]


def _date_label(day):
    return f"{day:%Y/%m/%d}（{WEEKDAYS[day.weekday()]}）"


def _cell(text):
    return {"type": "raw_text", "text": str(text)}


def _bold_cell(text):
    bold_text = {"type": "text", "text": text, "style": {"bold": True}}
    return {"type": "rich_text", "elements": [{"type": "rich_text_section", "elements": [bold_text]}]}


def _names(names):
    shown = "、".join(names[:MAX_ASSIGNEES])
    return shown + (f" ほか{len(names) - MAX_ASSIGNEES}名" if len(names) > MAX_ASSIGNEES else "") or "-"


def _project_table(projects, assignees):
    """Slack allows one table per message, so the projects get it."""
    rows = [[_bold_cell(column) for column in PROJECT_COLUMNS]]
    for project in projects:
        rows.append(
            [
                _cell(project["name"]),
                _cell(_progress_bar(project["progress"])),
                _cell(project["completed"]),
                _cell(project["started"]),
                _cell(_open_count(project)),
                _cell(project["overdue"] or "-"),
                _cell(_names(assignees.get(project["id"], []))),
            ]
        )
    numeric = {"align": "right"}
    wrapped = {"is_wrapped": True}
    # Webhooks reject null entries here with invalid_blocks, although the docs allow them
    return {
        "type": "table",
        "column_settings": [wrapped, {"align": "left"}, numeric, numeric, numeric, numeric, wrapped],
        "rows": rows,
    }


def _member_line(member):
    totals = member["totals"]
    projects = member["projects"]
    project_line = projects[0]["name"] + (f" ほか{len(projects) - 1}件" if len(projects) > 1 else "")
    overdue = f"・期限切れ {totals['overdue']}" if totals["overdue"] else ""
    return (
        f"• *{_member_name(member)}*　進行中 {totals['started']}・完了 {totals['completed']}"
        f"・未完了 {_open_count(totals)}{overdue}（{project_line}）"
    )


def overdue_work_items(workspace, limit=OVERDUE_ITEMS):
    """The open work items that are furthest past their due date."""
    today = timezone.now().astimezone(workspace_zone(workspace)).date()
    issues = (
        Issue.issue_objects.filter(
            workspace_id=workspace.id,
            state__group__in=["backlog", "unstarted", "started"],
            target_date__lt=today,
        )
        .select_related("project")
        .prefetch_related("assignees")
        .order_by("target_date", "sequence_id")[:limit]
    )
    return [
        {
            "key": f"{issue.project.identifier}-{issue.sequence_id}",
            "name": issue.name,
            "target_date": issue.target_date,
            "days_late": (today - issue.target_date).days,
            "assignees": [
                f"{user.first_name or ''} {user.last_name or ''}".strip() or user.display_name
                for user in issue.assignees.all()
            ],
        }
        for issue in issues
    ]


def team_progress_url(workspace, start, end):
    # APP_BASE_URL is the web app; WEB_URL can point at the API in local setups
    base_url = (settings.APP_BASE_URL or settings.WEB_URL or "").rstrip("/")
    if not base_url:
        return None
    return f"{base_url}/{workspace.slug}/team-progress/?start_date={start.isoformat()}&end_date={end.isoformat()}"


def _section(text):
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def build_slack_payload(workspace, progress, title_prefix="進捗レポート", overdue_items=None):
    start = date.fromisoformat(progress["start_date"])
    end = date.fromisoformat(progress["end_date"])
    summary = progress["summary"]
    # The report is about the period, so work that did not move in it is left out
    # (e.g. a project finished the week before); stalled overdue work still shows in its own list
    members = [
        {**member, "projects": [project for project in member["projects"] if project["updated"]]}
        for member in progress["members"]
    ]
    members = sorted(
        (member for member in members if member["projects"]),
        key=lambda member: (-member["totals"]["started"], -_open_count(member["totals"])),
    )
    # Projects that need attention first
    projects = sorted(
        (project for project in progress["projects"] if project["updated"]),
        key=lambda project: (-project["overdue"], -project["started"]),
    )
    # Everyone on the project, not only those whose own work moved in the period
    assignees = {}
    for member in progress["members"]:
        for project in member["projects"]:
            assignees.setdefault(project["id"], []).append(_member_name(member))

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": title_prefix}},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{workspace.name}　｜　{_date_label(start)} 〜 {_date_label(end)}"
                    f"　｜　期間中に動きのあった {len(projects)} プロジェクト・{len(members)} 人",
                }
            ],
        },
        _section(
            f"期間内に完了 *{summary['completed']}* 件　｜　期間内に作成 *{summary['created']}* 件　｜　"
            f"進行中 *{summary['started']}* 件　｜　未完了 *{_open_count(summary)}* 件　｜　"
            f"期限切れ *{summary['overdue']}* 件"
        ),
    ]

    if projects:
        blocks += [{"type": "divider"}, _section("*プロジェクト別*")]
        blocks.append(_project_table(projects[:MAX_PROJECTS], assignees))
        if len(projects) > MAX_PROJECTS:
            more = f"ほか {len(projects) - MAX_PROJECTS} プロジェクト"
            blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": more}]})
    else:
        blocks += [{"type": "divider"}, _section("期間中に動きのあったプロジェクトはありません")]

    if members:
        lines = [_member_line(member) for member in members[:MAX_MEMBERS]]
        if len(members) > MAX_MEMBERS:
            lines.append(f"ほか {len(members) - MAX_MEMBERS} 名")
        blocks += [{"type": "divider"}, _section("*担当者別*\n" + "\n".join(lines))]

    if overdue_items:
        lines = [
            f"• `{item['key']}` {item['name']} — {'・'.join(item['assignees']) or '担当者なし'}"
            f"　*{item['days_late']}日超過* （期限 {item['target_date']:%m/%d}）"
            for item in overdue_items
        ]
        blocks += [{"type": "divider"}, _section("*期限切れの作業項目（遅れが大きい順）*\n" + "\n".join(lines))]

    url = team_progress_url(workspace, start, end)
    if url:
        blocks += [{"type": "divider"}, _section(f"<{url}|チーム進捗ページで詳しく見る>")]

    return {
        "text": f"{title_prefix} — {workspace.name}（{start:%m/%d}〜{end:%m/%d}）: 完了 {summary['completed']} 件"
        f"・進行中 {summary['started']} 件・期限切れ {summary['overdue']} 件",
        "blocks": blocks,
    }


def post_to_slack(webhook_url, payload):
    if not webhook_url.startswith(SLACK_WEBHOOK_PREFIX):
        raise SlackReportError("The webhook URL must start with https://hooks.slack.com/")
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
    except requests.RequestException as e:
        raise SlackReportError(f"Could not reach Slack: {e.__class__.__name__}") from e
    if response.status_code != 200:
        raise SlackReportError(f"Slack returned {response.status_code}: {response.text[:200]}")


def report_period(report, today):
    days = PERIOD_DAYS.get(report.frequency, 7)
    return today - timedelta(days=days - 1), today


def send_slack_report(report, start, end):
    """Build and post the report for the period; raises SlackReportError on failure."""
    webhook_url = decrypt_data(report.webhook_url)
    if not webhook_url:
        raise SlackReportError("No Slack webhook URL is configured")
    workspace = report.workspace
    progress = build_team_progress(workspace, start, end)
    title = f"{FREQUENCY_LABELS.get(report.frequency, '')}進捗レポート"
    payload = build_slack_payload(workspace, progress, title_prefix=title, overdue_items=overdue_work_items(workspace))
    post_to_slack(webhook_url, payload)


def is_report_due(report, now):
    local_now = now.astimezone(workspace_zone(report.workspace))
    if report.frequency == WorkspaceSlackReport.Frequency.WEEKLY and local_now.weekday() != report.weekday:
        return False
    if report.frequency == WorkspaceSlackReport.Frequency.MONTHLY and local_now.day != 1:
        return False
    if local_now.hour < report.hour:
        return False
    if report.last_sent_at is None:
        return True
    # Catches up later the same day if the worker was down at the scheduled hour, but never sends twice
    return report.last_sent_at.astimezone(local_now.tzinfo).date() < local_now.date()


@shared_task
def send_due_slack_reports():
    """Runs hourly; posts every enabled report whose scheduled time has come."""
    now = timezone.now()
    for report in (
        WorkspaceSlackReport.objects.filter(is_enabled=True).exclude(webhook_url="").select_related("workspace")
    ):
        try:
            if not is_report_due(report, now):
                continue
            today = now.astimezone(workspace_zone(report.workspace)).date()
            start, end = report_period(report, today)
            send_slack_report(report, start, end)
            report.last_sent_at = now
            report.save(update_fields=["last_sent_at", "updated_at"], disable_auto_set_user=True)
            logger.info("Sent Slack report for workspace %s", report.workspace.slug)
        except Exception as e:
            log_exception(e)

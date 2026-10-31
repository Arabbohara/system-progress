# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Who is working on what, and how far along it is.

Shared by the team progress page, the "my active projects" home section and the
Slack report. Open counts (backlog/unstarted/started/overdue) are a snapshot of
now; ``completed`` and ``created`` count what happened inside the requested period.
"""

# Python imports
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# Django imports
from django.db.models import Count, F, Q

# Module imports
from plane.db.models import DepartmentMember, Issue, Project, ProjectMember, WorkspaceMember

OPEN_GROUPS = ["backlog", "unstarted", "started"]
DEFAULT_PERIOD_DAYS = 7
MAX_PERIOD_DAYS = 366


def workspace_zone(workspace):
    try:
        return ZoneInfo(workspace.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def resolve_period(workspace, start_date=None, end_date=None):
    """
    Turn optional ``YYYY-MM-DD`` strings into an inclusive date range in the workspace's timezone.
    Defaults to the last 7 days ending today. Raises ValueError on bad input.
    """
    today = datetime.now(workspace_zone(workspace)).date()
    end = date.fromisoformat(end_date) if end_date else today
    start = date.fromisoformat(start_date) if start_date else end - timedelta(days=DEFAULT_PERIOD_DAYS - 1)
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    if (end - start).days >= MAX_PERIOD_DAYS:
        raise ValueError(f"The period can be at most {MAX_PERIOD_DAYS} days")
    return start, end


def _period_bounds(workspace, start, end):
    zone = workspace_zone(workspace)
    return datetime.combine(start, time.min, tzinfo=zone), datetime.combine(
        end + timedelta(days=1), time.min, tzinfo=zone
    )


def _counts(since, until, today):
    return {
        "backlog": Count("id", filter=Q(state__group="backlog"), distinct=True),
        "unstarted": Count("id", filter=Q(state__group="unstarted"), distinct=True),
        "started": Count("id", filter=Q(state__group="started"), distinct=True),
        "overdue": Count("id", filter=Q(state__group__in=OPEN_GROUPS, target_date__lt=today), distinct=True),
        "completed": Count(
            "id",
            filter=Q(state__group="completed", completed_at__gte=since, completed_at__lt=until),
            distinct=True,
        ),
        "created": Count("id", filter=Q(created_at__gte=since, created_at__lt=until), distinct=True),
        # Any change during the period, so reports can skip work that did not move
        "updated": Count("id", filter=Q(updated_at__gte=since, updated_at__lt=until), distinct=True),
    }


def _empty_counts():
    return {"backlog": 0, "unstarted": 0, "started": 0, "overdue": 0, "completed": 0, "created": 0, "updated": 0}


def _add_counts(total, row):
    for key in total:
        total[key] += row[key]


def _project_info(project):
    return {
        "id": project.id,
        "name": project.name,
        "identifier": project.identifier,
        "logo_props": project.logo_props,
        "progress": project.progress,
        "department_id": project.department_id,
    }


def build_team_progress(workspace, start, end):
    """Per-member and per-project progress for every active project of the workspace."""
    since, until = _period_bounds(workspace, start, end)
    today = datetime.now(workspace_zone(workspace)).date()
    counts = _counts(since, until, today)

    projects = {
        project.id: project for project in Project.objects.filter(workspace_id=workspace.id, archived_at__isnull=True)
    }
    issues = Issue.issue_objects.filter(workspace_id=workspace.id, project_id__in=list(projects))

    # Per project: everything, assigned or not
    project_rows = {row["project_id"]: row for row in issues.order_by().values("project_id").annotate(**counts)}

    # Per member and project: only issues assigned to the member
    assignment_rows = (
        issues.filter(issue_assignee__deleted_at__isnull=True, issue_assignee__assignee__isnull=False)
        .order_by()
        .values("project_id", member_id=F("issue_assignee__assignee_id"))
        .annotate(**counts)
    )

    workspace_members = (
        WorkspaceMember.objects.filter(workspace_id=workspace.id, is_active=True, member__is_bot=False)
        .select_related("member")
        .order_by("member__display_name")
    )
    member_departments = {}
    for member_id, department_id in DepartmentMember.objects.filter(
        workspace_id=workspace.id, department__deleted_at__isnull=True
    ).values_list("member_id", "department_id"):
        member_departments.setdefault(member_id, []).append(department_id)

    members = {}
    for workspace_member in workspace_members:
        user = workspace_member.member
        members[user.id] = {
            "member_id": user.id,
            "display_name": user.display_name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "avatar_url": user.avatar_url,
            "role": workspace_member.role,
            "department_ids": member_departments.get(user.id, []),
            "totals": _empty_counts(),
            "projects": [],
        }

    for row in assignment_rows:
        member = members.get(row["member_id"])
        if member is None:
            continue
        stats = {key: row[key] for key in _empty_counts()}
        if not any(stats.values()):
            continue
        _add_counts(member["totals"], stats)
        member["projects"].append({**_project_info(projects[row["project_id"]]), **stats})

    for member in members.values():
        # Most active work first
        member["projects"].sort(key=lambda project: (-project["started"], -project["completed"], project["name"]))

    project_list = []
    summary = _empty_counts()
    for project_id, project in projects.items():
        row = project_rows.get(project_id, {})
        stats = {key: row.get(key, 0) for key in summary}
        _add_counts(summary, stats)
        project_list.append({**_project_info(project), **stats})
    project_list.sort(key=lambda project: (-project["completed"], -project["started"], project["name"]))

    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "summary": {**summary, "active_projects": len(projects), "members": len(members)},
        "projects": project_list,
        "members": list(members.values()),
    }


def build_member_project_progress(workspace, user):
    """The projects the user belongs to, with the user's own open work in each."""
    today = datetime.now(workspace_zone(workspace)).date()
    project_ids = ProjectMember.objects.filter(
        workspace_id=workspace.id,
        member=user,
        is_active=True,
        project__archived_at__isnull=True,
    ).values_list("project_id", flat=True)

    rows = {
        row["project_id"]: row
        for row in Issue.issue_objects.filter(
            project_id__in=project_ids,
            issue_assignee__assignee=user,
            issue_assignee__deleted_at__isnull=True,
        )
        .order_by()
        .values("project_id")
        .annotate(
            backlog=Count("id", filter=Q(state__group="backlog"), distinct=True),
            unstarted=Count("id", filter=Q(state__group="unstarted"), distinct=True),
            started=Count("id", filter=Q(state__group="started"), distinct=True),
            overdue=Count("id", filter=Q(state__group__in=OPEN_GROUPS, target_date__lt=today), distinct=True),
        )
    }

    result = []
    for project_id in project_ids:
        row = rows.get(project_id, {})
        result.append(
            {
                "project_id": project_id,
                "backlog": row.get("backlog", 0),
                "unstarted": row.get("unstarted", 0),
                "started": row.get("started", 0),
                "overdue": row.get("overdue", 0),
            }
        )
    return result

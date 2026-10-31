# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db import models

from .base import BaseModel


class WorkspaceSlackReport(BaseModel):
    """Scheduled progress report posted to a Slack incoming webhook, one per workspace."""

    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"
        MONTHLY = "monthly", "Monthly"

    workspace = models.OneToOneField("db.Workspace", on_delete=models.CASCADE, related_name="slack_report")
    # Encrypted with plane.license.utils.encryption; the URL alone lets anyone post to the channel
    webhook_url = models.TextField(blank=True)
    is_enabled = models.BooleanField(default=False)
    frequency = models.CharField(max_length=16, choices=Frequency.choices, default=Frequency.WEEKLY)
    # Monday = 0; only used for weekly reports. Monthly reports go out on the 1st.
    weekday = models.PositiveSmallIntegerField(default=0)
    # Hour of day in the workspace's timezone
    hour = models.PositiveSmallIntegerField(default=9)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Workspace Slack Report"
        verbose_name_plural = "Workspace Slack Reports"
        db_table = "workspace_slack_reports"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.workspace_id} ({self.frequency})"

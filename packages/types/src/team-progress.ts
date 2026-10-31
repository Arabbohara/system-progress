/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TLogoProps } from "./common";

/** Open counts are a snapshot of now; `completed` and `created` fall inside the requested period */
export type TProgressCounts = {
  backlog: number;
  unstarted: number;
  started: number;
  overdue: number;
  completed: number;
  created: number;
};

export type TTeamProgressProject = TProgressCounts & {
  id: string;
  name: string;
  identifier: string;
  logo_props: TLogoProps;
  progress: number;
  department_id: string | null;
};

export type TTeamProgressMember = {
  member_id: string;
  display_name: string;
  first_name: string;
  last_name: string;
  avatar_url: string | null;
  role: number;
  department_ids: string[];
  totals: TProgressCounts;
  projects: TTeamProgressProject[];
};

export type TTeamProgress = {
  start_date: string;
  end_date: string;
  summary: TProgressCounts & { active_projects: number; members: number };
  projects: TTeamProgressProject[];
  members: TTeamProgressMember[];
};

export type TMyProjectProgress = {
  project_id: string;
  backlog: number;
  unstarted: number;
  started: number;
  overdue: number;
};

export type TSlackReportFrequency = "daily" | "weekly" | "monthly";

export type TSlackReportSetting = {
  is_enabled: boolean;
  frequency: TSlackReportFrequency;
  /** Monday = 0 */
  weekday: number;
  /** Hour of day in the workspace timezone */
  hour: number;
  last_sent_at: string | null;
  webhook_configured: boolean;
  webhook_url_masked: string;
};

export type TSlackReportSettingUpdate = Partial<
  Pick<TSlackReportSetting, "is_enabled" | "frequency" | "weekday" | "hour"> & { webhook_url: string }
>;

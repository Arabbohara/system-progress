/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type { TMyProjectProgress, TSlackReportSetting, TSlackReportSettingUpdate, TTeamProgress } from "@plane/types";
import { APIService } from "@/services/api.service";

export class TeamProgressService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getTeamProgress(
    workspaceSlug: string,
    period: { start_date?: string; end_date?: string } = {}
  ): Promise<TTeamProgress> {
    return this.get(`/api/workspaces/${workspaceSlug}/team-progress/`, { params: period })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getMyProjectProgress(workspaceSlug: string): Promise<TMyProjectProgress[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/my-project-progress/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getSlackReportSetting(workspaceSlug: string): Promise<TSlackReportSetting> {
    return this.get(`/api/workspaces/${workspaceSlug}/slack-report/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async updateSlackReportSetting(workspaceSlug: string, data: TSlackReportSettingUpdate): Promise<TSlackReportSetting> {
    return this.patch(`/api/workspaces/${workspaceSlug}/slack-report/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async sendSlackReport(
    workspaceSlug: string,
    period: { start_date?: string; end_date?: string } = {}
  ): Promise<{ start_date: string; end_date: string }> {
    return this.post(`/api/workspaces/${workspaceSlug}/slack-report/send/`, period)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}

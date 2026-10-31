/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// services
import { API_BASE_URL } from "@plane/constants";
import type { TDepartment, TDepartmentMember } from "@plane/types";
import { APIService } from "@/services/api.service";

export class DepartmentService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getDepartments(workspaceSlug: string): Promise<TDepartment[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/departments/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async createDepartment(workspaceSlug: string, data: Partial<TDepartment>): Promise<TDepartment> {
    return this.post(`/api/workspaces/${workspaceSlug}/departments/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async updateDepartment(
    workspaceSlug: string,
    departmentId: string,
    data: Partial<TDepartment>
  ): Promise<TDepartment> {
    return this.patch(`/api/workspaces/${workspaceSlug}/departments/${departmentId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async deleteDepartment(workspaceSlug: string, departmentId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/departments/${departmentId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getDepartmentMembers(workspaceSlug: string): Promise<TDepartmentMember[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/departments/members/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async addDepartmentMembers(
    workspaceSlug: string,
    departmentId: string,
    data: { members: { member_id: string; role: number }[] }
  ): Promise<TDepartmentMember[]> {
    return this.post(`/api/workspaces/${workspaceSlug}/departments/${departmentId}/members/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async updateDepartmentMember(
    workspaceSlug: string,
    departmentId: string,
    departmentMemberId: string,
    data: Partial<Pick<TDepartmentMember, "role" | "full_access">>
  ): Promise<TDepartmentMember> {
    return this.patch(
      `/api/workspaces/${workspaceSlug}/departments/${departmentId}/members/${departmentMemberId}/`,
      data
    )
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async removeDepartmentMember(workspaceSlug: string, departmentId: string, departmentMemberId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/departments/${departmentId}/members/${departmentMemberId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async joinDepartment(workspaceSlug: string, departmentId: string): Promise<TDepartmentMember> {
    return this.post(`/api/workspaces/${workspaceSlug}/departments/${departmentId}/join/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async joinDepartments(workspaceSlug: string, departmentIds?: string[]): Promise<TDepartmentMember[]> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/departments/join/`,
      departmentIds ? { department_ids: departmentIds } : {}
    )
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async leaveDepartment(workspaceSlug: string, departmentId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/departments/${departmentId}/join/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}

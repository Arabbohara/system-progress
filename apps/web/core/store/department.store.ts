/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { set, sortBy } from "lodash-es";
import { action, computed, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// types
import type { TDepartment, TDepartmentMember } from "@plane/types";
// services
import { DepartmentService } from "@/services/project";
// store
import type { CoreRootStore } from "./root.store";

export interface IDepartmentStore {
  fetchedMap: Record<string, boolean>;
  departmentMap: Record<string, TDepartment>;
  workspaceDepartments: TDepartment[] | undefined;
  getDepartmentById: (departmentId: string | undefined | null) => TDepartment | undefined;
  fetchDepartments: (workspaceSlug: string) => Promise<TDepartment[]>;
  createDepartment: (workspaceSlug: string, data: Partial<TDepartment>) => Promise<TDepartment>;
  updateDepartment: (workspaceSlug: string, departmentId: string, data: Partial<TDepartment>) => Promise<TDepartment>;
  deleteDepartment: (workspaceSlug: string, departmentId: string) => Promise<void>;
  // department members
  departmentMemberMap: Record<string, TDepartmentMember>;
  getDepartmentMembers: (departmentId: string) => TDepartmentMember[];
  getCurrentUserDepartmentMember: (departmentId: string) => TDepartmentMember | undefined;
  fetchDepartmentMembers: (workspaceSlug: string) => Promise<TDepartmentMember[]>;
  addDepartmentMembers: (
    workspaceSlug: string,
    departmentId: string,
    members: { member_id: string; role: number }[]
  ) => Promise<TDepartmentMember[]>;
  updateDepartmentMember: (
    workspaceSlug: string,
    departmentId: string,
    departmentMemberId: string,
    data: Partial<Pick<TDepartmentMember, "role" | "full_access">>
  ) => Promise<TDepartmentMember>;
  removeDepartmentMember: (workspaceSlug: string, departmentId: string, departmentMemberId: string) => Promise<void>;
  joinDepartment: (workspaceSlug: string, departmentId: string) => Promise<TDepartmentMember>;
  /** Join every department the current user is not in yet, or only `departmentIds` */
  joinDepartments: (workspaceSlug: string, departmentIds?: string[]) => Promise<TDepartmentMember[]>;
  leaveDepartment: (workspaceSlug: string, departmentId: string) => Promise<void>;
}

export class DepartmentStore implements IDepartmentStore {
  rootStore;
  departmentMap: Record<string, TDepartment> = {};
  departmentMemberMap: Record<string, TDepartmentMember> = {};
  fetchedMap: Record<string, boolean> = {};
  departmentService;

  constructor(_rootStore: CoreRootStore) {
    makeObservable(this, {
      departmentMap: observable,
      departmentMemberMap: observable,
      fetchedMap: observable,
      workspaceDepartments: computed,
      fetchDepartments: action,
      createDepartment: action,
      updateDepartment: action,
      deleteDepartment: action,
      fetchDepartmentMembers: action,
      addDepartmentMembers: action,
      updateDepartmentMember: action,
      removeDepartmentMember: action,
      joinDepartment: action,
      joinDepartments: action,
      leaveDepartment: action,
    });

    this.rootStore = _rootStore;
    this.departmentService = new DepartmentService();
  }

  get workspaceDepartments() {
    const currentWorkspaceDetails = this.rootStore.workspaceRoot.currentWorkspace;
    if (!currentWorkspaceDetails || !this.fetchedMap[currentWorkspaceDetails.slug]) return undefined;
    return sortBy(
      Object.values(this.departmentMap).filter((department) => department.workspace_id === currentWorkspaceDetails.id),
      "sort_order"
    );
  }

  getDepartmentById = computedFn((departmentId: string | undefined | null) =>
    departmentId ? this.departmentMap[departmentId] : undefined
  );

  fetchDepartments = async (workspaceSlug: string) =>
    await this.departmentService.getDepartments(workspaceSlug).then((response) => {
      runInAction(() => {
        response.forEach((department) => {
          set(this.departmentMap, [department.id], department);
        });
        set(this.fetchedMap, workspaceSlug, true);
      });
      return response;
    });

  createDepartment = async (workspaceSlug: string, data: Partial<TDepartment>) =>
    await this.departmentService.createDepartment(workspaceSlug, data).then((response) => {
      runInAction(() => {
        set(this.departmentMap, [response.id], response);
      });
      return response;
    });

  updateDepartment = async (workspaceSlug: string, departmentId: string, data: Partial<TDepartment>) => {
    const original = this.departmentMap[departmentId];
    try {
      runInAction(() => {
        set(this.departmentMap, [departmentId], { ...original, ...data });
      });
      return await this.departmentService.updateDepartment(workspaceSlug, departmentId, data);
    } catch (error) {
      runInAction(() => {
        set(this.departmentMap, [departmentId], original);
      });
      throw error;
    }
  };

  deleteDepartment = async (workspaceSlug: string, departmentId: string) => {
    await this.departmentService.deleteDepartment(workspaceSlug, departmentId);
    runInAction(() => {
      delete this.departmentMap[departmentId];
      Object.values(this.departmentMemberMap).forEach((departmentMember) => {
        if (departmentMember.department_id === departmentId) delete this.departmentMemberMap[departmentMember.id];
      });
    });
  };

  getDepartmentMembers = computedFn((departmentId: string) =>
    sortBy(
      Object.values(this.departmentMemberMap).filter(
        (departmentMember) => departmentMember.department_id === departmentId
      ),
      "created_at"
    )
  );

  getCurrentUserDepartmentMember = computedFn((departmentId: string) => {
    const currentUserId = this.rootStore.user.data?.id;
    if (!currentUserId) return undefined;
    return Object.values(this.departmentMemberMap).find(
      (departmentMember) =>
        departmentMember.department_id === departmentId && departmentMember.member_id === currentUserId
    );
  });

  /**
   * Department membership changes which projects the current user belongs to, so refresh them
   */
  private refreshCurrentUserProjects = async (workspaceSlug: string) => {
    await Promise.all([
      this.rootStore.projectRoot.project.fetchProjects(workspaceSlug),
      this.rootStore.user.permission.fetchUserProjectPermissions(workspaceSlug),
    ]);
  };

  fetchDepartmentMembers = async (workspaceSlug: string) =>
    await this.departmentService.getDepartmentMembers(workspaceSlug).then((response) => {
      runInAction(() => {
        this.departmentMemberMap = {};
        response.forEach((departmentMember) => {
          set(this.departmentMemberMap, [departmentMember.id], departmentMember);
        });
      });
      return response;
    });

  addDepartmentMembers = async (
    workspaceSlug: string,
    departmentId: string,
    members: { member_id: string; role: number }[]
  ) => {
    const response = await this.departmentService.addDepartmentMembers(workspaceSlug, departmentId, { members });
    runInAction(() => {
      response.forEach((departmentMember) => {
        set(this.departmentMemberMap, [departmentMember.id], departmentMember);
      });
    });
    const currentUserId = this.rootStore.user.data?.id;
    if (members.some((member) => member.member_id === currentUserId))
      await this.refreshCurrentUserProjects(workspaceSlug);
    return response;
  };

  updateDepartmentMember = async (
    workspaceSlug: string,
    departmentId: string,
    departmentMemberId: string,
    data: Partial<Pick<TDepartmentMember, "role" | "full_access">>
  ) => {
    const response = await this.departmentService.updateDepartmentMember(
      workspaceSlug,
      departmentId,
      departmentMemberId,
      data
    );
    runInAction(() => {
      set(this.departmentMemberMap, [departmentMemberId], response);
    });
    if (response.member_id === this.rootStore.user.data?.id) await this.refreshCurrentUserProjects(workspaceSlug);
    return response;
  };

  removeDepartmentMember = async (workspaceSlug: string, departmentId: string, departmentMemberId: string) => {
    const departmentMember = this.departmentMemberMap[departmentMemberId];
    await this.departmentService.removeDepartmentMember(workspaceSlug, departmentId, departmentMemberId);
    runInAction(() => {
      delete this.departmentMemberMap[departmentMemberId];
    });
    if (departmentMember?.member_id === this.rootStore.user.data?.id)
      await this.refreshCurrentUserProjects(workspaceSlug);
  };

  joinDepartment = async (workspaceSlug: string, departmentId: string) => {
    const response = await this.departmentService.joinDepartment(workspaceSlug, departmentId);
    runInAction(() => {
      set(this.departmentMemberMap, [response.id], response);
    });
    await this.refreshCurrentUserProjects(workspaceSlug);
    return response;
  };

  joinDepartments = async (workspaceSlug: string, departmentIds?: string[]) => {
    const response = await this.departmentService.joinDepartments(workspaceSlug, departmentIds);
    runInAction(() => {
      response.forEach((departmentMember) => {
        set(this.departmentMemberMap, [departmentMember.id], departmentMember);
      });
    });
    if (response.length > 0) await this.refreshCurrentUserProjects(workspaceSlug);
    return response;
  };

  leaveDepartment = async (workspaceSlug: string, departmentId: string) => {
    const departmentMember = this.getCurrentUserDepartmentMember(departmentId);
    await this.departmentService.leaveDepartment(workspaceSlug, departmentId);
    runInAction(() => {
      if (departmentMember) delete this.departmentMemberMap[departmentMember.id];
    });
    await this.refreshCurrentUserProjects(workspaceSlug);
  };
}

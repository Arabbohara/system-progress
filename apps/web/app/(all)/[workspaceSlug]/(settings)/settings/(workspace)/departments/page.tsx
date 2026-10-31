/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TDepartment } from "@plane/types";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
import { DepartmentForm } from "@/components/workspace/settings/departments/department-form";
import { DepartmentListItem } from "@/components/workspace/settings/departments/department-list-item";
// hooks
import { useDepartment } from "@/hooks/store/use-department";
import { useWorkspace } from "@/hooks/store/use-workspace";
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import type { Route } from "./+types/page";
import { DepartmentsWorkspaceSettingsHeader } from "./header";

function DepartmentsSettingsPage({ params }: Route.ComponentProps) {
  // router
  const { workspaceSlug } = params;
  // states
  const [isCreating, setIsCreating] = useState(false);
  const [isJoiningAll, setIsJoiningAll] = useState(false);
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { currentWorkspace } = useWorkspace();
  const {
    workspaceDepartments,
    fetchDepartments,
    fetchDepartmentMembers,
    createDepartment,
    getCurrentUserDepartmentMember,
    joinDepartments,
  } = useDepartment();
  // derived values
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const canEdit = allowPermissions([EUserPermissions.ADMIN, EUserPermissions.MEMBER], EUserPermissionsLevel.WORKSPACE);
  const canView = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER, EUserPermissions.GUEST],
    EUserPermissionsLevel.WORKSPACE
  );
  const unjoinedDepartmentCount =
    workspaceDepartments?.filter((department) => !getCurrentUserDepartmentMember(department.id)).length ?? 0;
  const pageTitle = currentWorkspace?.name
    ? `${currentWorkspace.name} - ${t("workspace_settings.settings.departments.title")}`
    : undefined;

  useSWR(
    canView ? `WORKSPACE_DEPARTMENTS_AND_MEMBERS_${workspaceSlug}` : null,
    canView ? () => Promise.all([fetchDepartments(workspaceSlug), fetchDepartmentMembers(workspaceSlug)]) : null,
    { revalidateOnFocus: false }
  );

  const handleCreate = async (data: Pick<TDepartment, "name" | "prefix" | "color">) => {
    try {
      await createDepartment(workspaceSlug, data);
      setIsCreating(false);
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("success"),
        message: t("workspace_settings.settings.departments.created_toast"),
      });
    } catch (error) {
      const fieldError = error as { name?: string[]; prefix?: string[] } | undefined;
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("error"),
        message: fieldError?.name?.[0] ?? fieldError?.prefix?.[0] ?? t("something_went_wrong_please_try_again"),
      });
    }
  };

  const handleJoinAll = async () => {
    setIsJoiningAll(true);
    try {
      const joined = await joinDepartments(workspaceSlug);
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("success"),
        message: t("workspace_settings.settings.departments.joined_all_toast", { count: joined.length }),
      });
    } catch (error) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("error"),
        message: (error as { error?: string } | undefined)?.error ?? t("something_went_wrong_please_try_again"),
      });
    } finally {
      setIsJoiningAll(false);
    }
  };

  if (workspaceUserInfo && !canView) {
    return <NotAuthorizedView section="settings" className="h-auto" />;
  }

  return (
    <SettingsContentWrapper header={<DepartmentsWorkspaceSettingsHeader />} hugging>
      <PageHead title={pageTitle} />
      <div className="flex w-full flex-col gap-y-6">
        <SettingsHeading
          title={t("workspace_settings.settings.departments.title")}
          description={
            <>
              {t("workspace_settings.settings.departments.description")}{" "}
              {t("workspace_settings.settings.departments.self_join_hint")}
            </>
          }
          control={
            canEdit &&
            !isCreating && (
              <div className="flex items-center gap-2">
                {unjoinedDepartmentCount > 0 && (
                  <Button variant="secondary" size="lg" onClick={handleJoinAll} loading={isJoiningAll}>
                    {t("workspace_settings.settings.departments.join_all")}
                  </Button>
                )}
                <Button variant="primary" size="lg" onClick={() => setIsCreating(true)}>
                  {t("workspace_settings.settings.departments.add_department")}
                </Button>
              </div>
            )
          }
        />
        <div className="flex flex-col gap-2">
          {isCreating && <DepartmentForm onSubmit={handleCreate} onCancel={() => setIsCreating(false)} />}
          {workspaceDepartments && workspaceDepartments.length === 0 && !isCreating ? (
            <p className="text-body-xs-regular text-tertiary">
              {t("workspace_settings.settings.departments.empty_state")}
            </p>
          ) : (
            workspaceDepartments?.map((department) => (
              <DepartmentListItem
                key={department.id}
                department={department}
                workspaceSlug={workspaceSlug}
                isAdmin={isAdmin}
                canEdit={canEdit}
              />
            ))
          )}
        </div>
      </div>
    </SettingsContentWrapper>
  );
}

export default observer(DepartmentsSettingsPage);

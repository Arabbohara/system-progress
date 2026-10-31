/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { TeamProgressRoot } from "@/components/team-progress/root";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
import { useUserPermissions } from "@/hooks/store/user";
import type { Route } from "./+types/page";

function TeamProgressPage({ params }: Route.ComponentProps) {
  const { workspaceSlug } = params;
  const { t } = useTranslation();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { currentWorkspace } = useWorkspace();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const pageTitle = currentWorkspace?.name ? `${currentWorkspace.name} - ${t("team_progress.title")}` : undefined;

  if (!workspaceUserInfo) return null;
  if (!isAdmin) return <NotAuthorizedView section="general" />;

  return (
    <>
      <PageHead title={pageTitle} />
      <div className="relative h-full w-full overflow-hidden overflow-y-auto">
        <TeamProgressRoot workspaceSlug={workspaceSlug} />
      </div>
    </>
  );
}

export default observer(TeamProgressPage);

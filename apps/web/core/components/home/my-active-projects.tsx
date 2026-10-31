/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import useSWR from "swr";
import { ChevronRight } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Logo } from "@plane/propel/emoji-icon-picker";
import type { TMyProjectProgress } from "@plane/types";
// hooks
import { useProject } from "@/hooks/store/use-project";
// services
import { TeamProgressService } from "@/services/workspace/team-progress.service";

const teamProgressService = new TeamProgressService();
const COLLAPSED_COUNT = 6;

const openCount = (progress: TMyProjectProgress | undefined) =>
  progress ? progress.backlog + progress.unstarted + progress.started : 0;

export const HomeMyActiveProjects = observer(function HomeMyActiveProjects() {
  const { workspaceSlug } = useParams();
  const { t } = useTranslation();
  const [showAll, setShowAll] = useState(false);
  const { joinedProjectIds, getProjectById } = useProject();

  const { data: myProgress } = useSWR(
    workspaceSlug ? `HOME_MY_PROJECT_PROGRESS_${workspaceSlug}` : null,
    workspaceSlug ? () => teamProgressService.getMyProjectProgress(workspaceSlug.toString()) : null,
    { revalidateOnFocus: false }
  );

  // A project is in progress for me if it isn't finished yet or I still have open work in it
  const activeProjects = useMemo(() => {
    const progressByProject = new Map((myProgress ?? []).map((row) => [row.project_id, row]));
    return (
      (joinedProjectIds ?? [])
        .map((projectId) => ({ project: getProjectById(projectId), progress: progressByProject.get(projectId) }))
        .filter(
          (row): row is { project: NonNullable<typeof row.project>; progress: TMyProjectProgress | undefined } =>
            !!row.project && ((row.project.progress ?? 0) < 100 || openCount(row.progress) > 0)
        )
        .slice()
        // oxlint-disable-next-line unicorn/no-array-sort
        .sort(
          (a, b) =>
            (b.progress?.started ?? 0) - (a.progress?.started ?? 0) ||
            openCount(b.progress) - openCount(a.progress) ||
            (b.project.progress ?? 0) - (a.project.progress ?? 0)
        )
    );
  }, [joinedProjectIds, getProjectById, myProgress]);

  if (!workspaceSlug || activeProjects.length === 0) return null;

  const visibleProjects = showAll ? activeProjects : activeProjects.slice(0, COLLAPSED_COUNT);

  return (
    <div className="mb-4 rounded-md border border-subtle">
      <div className="flex items-center justify-between border-b border-subtle px-4 py-2.5">
        <span className="text-13 font-medium text-primary">{t("home.my_active_projects.title")}</span>
        <span className="text-12 text-tertiary">
          {t("home.my_active_projects.count", { count: activeProjects.length })}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 p-3 sm:grid-cols-2">
        {visibleProjects.map(({ project, progress }) => {
          const percent = project.progress ?? 0;
          return (
            <Link
              key={project.id}
              href={`/${workspaceSlug.toString()}/projects/${project.id}/issues/`}
              className="group flex flex-col gap-2 rounded-md border border-subtle bg-surface-1 p-3 transition-colors hover:border-strong hover:bg-surface-2"
            >
              <div className="flex items-center gap-2">
                <span className="grid size-7 flex-shrink-0 place-items-center rounded-sm bg-layer-1">
                  <Logo logo={project.logo_props} size={16} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-13 font-medium text-primary">{project.name}</span>
                  <span className="block text-11 text-tertiary">{project.identifier}</span>
                </span>
                <ChevronRight className="size-4 flex-shrink-0 text-placeholder transition-transform group-hover:translate-x-0.5" />
              </div>
              <div className="flex items-center gap-2">
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <span className="block h-full rounded-full bg-accent-primary" style={{ width: `${percent}%` }} />
                </span>
                <span className="w-9 text-right text-12 text-secondary">{percent}%</span>
              </div>
              <div className="flex flex-wrap gap-1.5 text-11">
                {openCount(progress) === 0 ? (
                  <span className="text-tertiary">{t("home.my_active_projects.no_assigned")}</span>
                ) : (
                  <>
                    <span className="rounded-sm bg-accent-subtle px-1.5 py-0.5 text-accent-primary">
                      {t("home.my_active_projects.started", { count: progress?.started ?? 0 })}
                    </span>
                    <span className="rounded-sm bg-layer-1 px-1.5 py-0.5 text-secondary">
                      {t("home.my_active_projects.open", { count: openCount(progress) })}
                    </span>
                    {(progress?.overdue ?? 0) > 0 && (
                      <span className="rounded-sm bg-danger-subtle px-1.5 py-0.5 text-danger-primary">
                        {t("home.my_active_projects.overdue", { count: progress?.overdue ?? 0 })}
                      </span>
                    )}
                  </>
                )}
              </div>
            </Link>
          );
        })}
      </div>
      {activeProjects.length > COLLAPSED_COUNT && (
        <button
          type="button"
          className="w-full border-t border-subtle py-2 text-12 font-medium text-accent-primary hover:bg-surface-2"
          onClick={() => setShowAll((value) => !value)}
        >
          {showAll ? t("home.my_active_projects.show_less") : t("home.my_active_projects.show_all")}
        </button>
      )}
    </div>
  );
});

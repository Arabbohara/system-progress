/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, CircleDot, ListTodo, PlusCircle } from "lucide-react";
// plane imports
import { ROLE_DETAILS } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Logo } from "@plane/propel/emoji-icon-picker";
import type { EUserWorkspaceRoles, TProgressCounts, TTeamProgressMember, TTeamProgressProject } from "@plane/types";
import { Avatar } from "@plane/ui";
import { cn, getFileURL } from "@plane/utils";
// hooks
import { useDepartment } from "@/hooks/store/use-department";

export const openCount = (counts: TProgressCounts) => counts.backlog + counts.unstarted + counts.started;

export const memberName = (member: Pick<TTeamProgressMember, "first_name" | "last_name" | "display_name">) =>
  `${member.first_name ?? ""} ${member.last_name ?? ""}`.trim() || member.display_name;

function ProgressBar({ percent, className }: { percent: number; className?: string }) {
  return (
    <span className={cn("h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2", className)}>
      <span className="block h-full rounded-full bg-accent-primary" style={{ width: `${percent}%` }} />
    </span>
  );
}

function Stat({ icon, label, value, tone }: { icon: ReactNode; label: string; value: number; tone?: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5 rounded-md bg-layer-1 px-1 py-1.5">
      <span className={cn("flex items-center gap-1 text-14 font-semibold text-primary", tone)}>
        {icon}
        {value}
      </span>
      <span className="text-11 text-tertiary">{label}</span>
    </div>
  );
}

export function CountStats({ counts }: { counts: TProgressCounts }) {
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-4 gap-1.5">
      <Stat
        icon={<CircleDot className="size-3.5 text-accent-primary" />}
        label={t("team_progress.stats.started")}
        value={counts.started}
      />
      <Stat
        icon={<ListTodo className="size-3.5 text-secondary" />}
        label={t("team_progress.stats.open")}
        value={openCount(counts)}
      />
      <Stat
        icon={<CheckCircle2 className="size-3.5 text-success-primary" />}
        label={t("team_progress.stats.completed")}
        value={counts.completed}
      />
      <Stat
        icon={<AlertTriangle className={cn("size-3.5", counts.overdue ? "text-danger-primary" : "text-placeholder")} />}
        label={t("team_progress.stats.overdue")}
        value={counts.overdue}
        tone={counts.overdue ? "text-danger-primary" : undefined}
      />
    </div>
  );
}

const MEMBER_TILE_PROJECTS = 4;

export const TeamMemberTile = observer(function TeamMemberTile(props: {
  member: TTeamProgressMember;
  workspaceSlug: string;
}) {
  const { member, workspaceSlug } = props;
  const { t } = useTranslation();
  const { getDepartmentById } = useDepartment();
  const name = memberName(member);
  const hasWork = member.projects.length > 0;

  return (
    <div
      className={cn("flex flex-col gap-3 rounded-lg border border-subtle bg-surface-1 p-4 shadow-raised-100", {
        "opacity-60": !hasWork,
      })}
    >
      <div className="flex items-center gap-3">
        <Avatar src={getFileURL(member.avatar_url ?? "")} name={name} size="lg" showTooltip={false} />
        <div className="min-w-0 flex-1">
          <Link
            href={`/${workspaceSlug}/profile/${member.member_id}/`}
            className="block truncate text-14 font-semibold text-primary hover:underline"
          >
            {name}
          </Link>
          <div className="mt-0.5 flex flex-wrap items-center gap-1">
            <span className="text-11 text-tertiary">
              {t(ROLE_DETAILS[member.role as EUserWorkspaceRoles]?.i18n_title ?? "")}
            </span>
            {member.department_ids.map((departmentId) => {
              const department = getDepartmentById(departmentId);
              if (!department) return null;
              return (
                <span
                  key={departmentId}
                  className="rounded-sm px-1.5 py-0.5 text-11 text-secondary"
                  style={{ backgroundColor: department.color ? `${department.color}26` : undefined }}
                >
                  {department.name}
                </span>
              );
            })}
          </div>
        </div>
      </div>

      <CountStats counts={member.totals} />

      {hasWork ? (
        <div className="flex flex-col gap-1.5">
          {member.projects.slice(0, MEMBER_TILE_PROJECTS).map((project) => (
            <Link
              key={project.id}
              href={`/${workspaceSlug}/projects/${project.id}/issues/`}
              className="flex items-center gap-2 rounded-sm px-1 py-0.5 hover:bg-layer-1"
            >
              <span className="grid size-5 flex-shrink-0 place-items-center">
                <Logo logo={project.logo_props} size={14} />
              </span>
              <span className="min-w-0 flex-1 truncate text-12 text-secondary">{project.name}</span>
              <span className="text-11 text-tertiary">
                {t("team_progress.tile.started_of_open", { started: project.started, open: openCount(project) })}
              </span>
              <ProgressBar percent={project.progress} className="max-w-14" />
              <span className="w-8 text-right text-11 text-secondary">{project.progress}%</span>
            </Link>
          ))}
          {member.projects.length > MEMBER_TILE_PROJECTS && (
            <span className="px-1 text-11 text-tertiary">
              {t("team_progress.tile.more_projects", { count: member.projects.length - MEMBER_TILE_PROJECTS })}
            </span>
          )}
        </div>
      ) : (
        <p className="text-12 text-tertiary">{t("team_progress.tile.no_work")}</p>
      )}
    </div>
  );
});

export const TeamProjectTile = observer(function TeamProjectTile(props: {
  project: TTeamProgressProject;
  assignees: TTeamProgressMember[];
  workspaceSlug: string;
}) {
  const { project, assignees, workspaceSlug } = props;
  const { t } = useTranslation();
  const { getDepartmentById } = useDepartment();
  const department = getDepartmentById(project.department_id);

  return (
    <Link
      href={`/${workspaceSlug}/projects/${project.id}/issues/`}
      className="flex flex-col gap-3 rounded-lg border border-subtle bg-surface-1 p-4 shadow-raised-100 transition-colors hover:border-strong"
    >
      <div className="flex items-center gap-3">
        <span className="grid size-10 flex-shrink-0 place-items-center rounded-md bg-layer-1">
          <Logo logo={project.logo_props} size={22} />
        </span>
        <div className="min-w-0 flex-1">
          <span className="block truncate text-14 font-semibold text-primary">{project.name}</span>
          <span className="block text-11 text-tertiary">
            {project.identifier}
            {department ? ` · ${department.name}` : ""}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <ProgressBar percent={project.progress} />
        <span className="w-9 text-right text-12 font-medium text-primary">{project.progress}%</span>
      </div>
      <CountStats counts={project} />
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1 text-11 text-tertiary">
          <PlusCircle className="size-3" />
          {t("team_progress.tile.created", { count: project.created })}
        </span>
        {assignees.length > 0 ? (
          <span className="flex -space-x-1.5">
            {assignees.slice(0, 6).map((member) => (
              <Avatar
                key={member.member_id}
                src={getFileURL(member.avatar_url ?? "")}
                name={memberName(member)}
                size="md"
              />
            ))}
            {assignees.length > 6 && (
              <span className="grid size-6 place-items-center rounded-full bg-layer-1 text-11 text-secondary">
                +{assignees.length - 6}
              </span>
            )}
          </span>
        ) : (
          <span className="text-11 text-tertiary">{t("team_progress.tile.no_assignees")}</span>
        )}
      </div>
    </Link>
  );
});

/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { observer } from "mobx-react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  FolderKanban,
  PlusCircle,
  Printer,
  Search,
  Send,
  Settings2,
  Users,
} from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TTeamProgressMember } from "@plane/types";
import { CustomSelect, Loader } from "@plane/ui";
import { cn } from "@plane/utils";
// hooks
import { useDepartment } from "@/hooks/store/use-department";
// services
import { TeamProgressService } from "@/services/workspace/team-progress.service";
// local imports
import type { TPeriod } from "./period-filter";
import { TeamProgressPeriodFilter, presetPeriod } from "./period-filter";
import { SlackReportModal } from "./slack-report-modal";
import { TeamMemberTile, TeamProjectTile, memberName, openCount } from "./tiles";

const teamProgressService = new TeamProgressService();

type TView = "members" | "projects";
const ALL_DEPARTMENTS = "__all__";

function SummaryCard({ icon, label, value, tone }: { icon: ReactNode; label: string; value: number; tone: string }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-subtle bg-surface-1 p-3">
      <span className={cn("grid size-9 flex-shrink-0 place-items-center rounded-md", tone)}>{icon}</span>
      <span className="min-w-0">
        <span className="block text-20 leading-6 font-semibold text-primary">{value}</span>
        <span className="block truncate text-11 text-tertiary">{label}</span>
      </span>
    </div>
  );
}

export const TeamProgressRoot = observer(function TeamProgressRoot(props: { workspaceSlug: string }) {
  const { workspaceSlug } = props;
  const { t } = useTranslation();
  const searchParams = useSearchParams();
  const [period, setPeriod] = useState<TPeriod>(() => {
    const start = searchParams.get("start_date");
    const end = searchParams.get("end_date");
    return start && end ? { start_date: start, end_date: end } : presetPeriod(7);
  });
  const [view, setView] = useState<TView>("members");
  const [departmentId, setDepartmentId] = useState<string>(ALL_DEPARTMENTS);
  const [query, setQuery] = useState("");
  const [isSlackModalOpen, setIsSlackModalOpen] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const { workspaceDepartments, getDepartmentById, fetchDepartments } = useDepartment();

  useSWR(`WORKSPACE_DEPARTMENTS_${workspaceSlug}`, () => fetchDepartments(workspaceSlug), {
    revalidateOnFocus: false,
  });
  const { data, isLoading, error } = useSWR(
    `TEAM_PROGRESS_${workspaceSlug}_${period.start_date}_${period.end_date}`,
    () => teamProgressService.getTeamProgress(workspaceSlug, period),
    { revalidateOnFocus: false, keepPreviousData: true }
  );

  const normalizedQuery = query.trim().toLowerCase();
  const members = useMemo(
    () =>
      (data?.members ?? [])
        .filter((member) => departmentId === ALL_DEPARTMENTS || member.department_ids.includes(departmentId))
        .filter((member) => !normalizedQuery || memberName(member).toLowerCase().includes(normalizedQuery))
        .slice()
        .sort(
          (a, b) =>
            Number(b.projects.length > 0) - Number(a.projects.length > 0) ||
            b.totals.started - a.totals.started ||
            openCount(b.totals) - openCount(a.totals) ||
            memberName(a).localeCompare(memberName(b), "ja")
        ),
    [data, departmentId, normalizedQuery]
  );

  const projects = useMemo(
    () =>
      (data?.projects ?? [])
        .filter((project) => departmentId === ALL_DEPARTMENTS || project.department_id === departmentId)
        .filter((project) => !normalizedQuery || project.name.toLowerCase().includes(normalizedQuery)),
    [data, departmentId, normalizedQuery]
  );

  const assigneesByProject = useMemo(() => {
    const map = new Map<string, TTeamProgressMember[]>();
    (data?.members ?? []).forEach((member) =>
      member.projects.forEach((project) => {
        const list = map.get(project.id);
        if (list) list.push(member);
        else map.set(project.id, [member]);
      })
    );
    return map;
  }, [data]);

  const handleSendToSlack = async () => {
    setIsSending(true);
    try {
      await teamProgressService.sendSlackReport(workspaceSlug, period);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("success"), message: t("team_progress.slack.sent_toast") });
    } catch (sendError) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("error"),
        message: (sendError as { error?: string } | undefined)?.error ?? t("something_went_wrong_please_try_again"),
      });
    } finally {
      setIsSending(false);
    }
  };

  const departmentLabel =
    departmentId === ALL_DEPARTMENTS
      ? t("team_progress.filters.all_departments")
      : (getDepartmentById(departmentId)?.name ?? "");

  return (
    <div className="flex flex-col gap-5 px-page-x py-5">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <TeamProgressPeriodFilter period={period} onChange={setPeriod} />
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="lg" prependIcon={<Printer />} onClick={() => window.print()}>
            {t("team_progress.print")}
          </Button>
          <Button variant="secondary" size="lg" prependIcon={<Settings2 />} onClick={() => setIsSlackModalOpen(true)}>
            {t("team_progress.slack.settings")}
          </Button>
          <Button variant="primary" size="lg" prependIcon={<Send />} onClick={handleSendToSlack} loading={isSending}>
            {t("team_progress.slack.send_now")}
          </Button>
        </div>
      </div>

      {/* Summary */}
      {data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
          <SummaryCard
            icon={<Users className="size-4" />}
            label={t("team_progress.summary.members")}
            value={data.summary.members}
            tone="bg-layer-1 text-secondary"
          />
          <SummaryCard
            icon={<FolderKanban className="size-4" />}
            label={t("team_progress.summary.active_projects")}
            value={data.summary.active_projects}
            tone="bg-layer-1 text-secondary"
          />
          <SummaryCard
            icon={<CircleDot className="size-4" />}
            label={t("team_progress.summary.started")}
            value={data.summary.started}
            tone="bg-accent-subtle text-accent-primary"
          />
          <SummaryCard
            icon={<CheckCircle2 className="size-4" />}
            label={t("team_progress.summary.completed")}
            value={data.summary.completed}
            tone="bg-success-subtle text-success-primary"
          />
          <SummaryCard
            icon={<PlusCircle className="size-4" />}
            label={t("team_progress.summary.created")}
            value={data.summary.created}
            tone="bg-layer-1 text-secondary"
          />
          <SummaryCard
            icon={<AlertTriangle className="size-4" />}
            label={t("team_progress.summary.overdue")}
            value={data.summary.overdue}
            tone="bg-danger-subtle text-danger-primary"
          />
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 print:hidden">
        <div className="flex items-center rounded-md border border-subtle p-0.5">
          {(["members", "projects"] as TView[]).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setView(option)}
              className={cn("rounded-sm px-3 py-1 text-12 font-medium text-secondary hover:bg-layer-1", {
                "bg-layer-1 text-primary": view === option,
              })}
            >
              {t(`team_progress.view.${option}`)}
            </button>
          ))}
        </div>
        {(workspaceDepartments?.length ?? 0) > 0 && (
          <CustomSelect value={departmentId} onChange={setDepartmentId} label={departmentLabel} input>
            <CustomSelect.Option value={ALL_DEPARTMENTS}>
              {t("team_progress.filters.all_departments")}
            </CustomSelect.Option>
            {workspaceDepartments?.map((department) => (
              <CustomSelect.Option key={department.id} value={department.id}>
                {department.name}
              </CustomSelect.Option>
            ))}
          </CustomSelect>
        )}
        <div className="flex items-center gap-1.5 rounded-md border border-subtle px-2 py-1">
          <Search className="size-3.5 text-tertiary" />
          <input
            className="w-40 bg-transparent text-12 text-primary outline-none placeholder:text-placeholder"
            placeholder={t("team_progress.filters.search")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>

      {/* Tiles */}
      {error ? (
        <p className="text-13 text-danger-primary">
          {(error as { error?: string } | undefined)?.error ?? t("something_went_wrong_please_try_again")}
        </p>
      ) : isLoading && !data ? (
        <Loader className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, index) => (
            <Loader.Item key={index} height="220px" />
          ))}
        </Loader>
      ) : view === "members" ? (
        members.length === 0 ? (
          <p className="text-13 text-tertiary">{t("team_progress.empty")}</p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {members.map((member) => (
              <TeamMemberTile key={member.member_id} member={member} workspaceSlug={workspaceSlug} />
            ))}
          </div>
        )
      ) : projects.length === 0 ? (
        <p className="text-13 text-tertiary">{t("team_progress.empty")}</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {projects.map((project) => (
            <TeamProjectTile
              key={project.id}
              project={project}
              assignees={assigneesByProject.get(project.id) ?? []}
              workspaceSlug={workspaceSlug}
            />
          ))}
        </div>
      )}

      <SlackReportModal
        isOpen={isSlackModalOpen}
        onClose={() => setIsSlackModalOpen(false)}
        workspaceSlug={workspaceSlug}
      />
    </div>
  );
});

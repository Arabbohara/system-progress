/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { CalendarDays } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { cn } from "@plane/utils";

export type TPeriod = { start_date: string; end_date: string };

export const PERIOD_PRESETS = [7, 14, 30, 90] as const;

const toDateString = (date: Date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

/** The last `days` days, ending today */
export const presetPeriod = (days: number): TPeriod => {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - (days - 1));
  return { start_date: toDateString(start), end_date: toDateString(end) };
};

export const matchingPreset = (period: TPeriod) =>
  PERIOD_PRESETS.find((days) => {
    const preset = presetPeriod(days);
    return preset.start_date === period.start_date && preset.end_date === period.end_date;
  });

type Props = {
  period: TPeriod;
  onChange: (period: TPeriod) => void;
};

export function TeamProgressPeriodFilter(props: Props) {
  const { period, onChange } = props;
  const { t } = useTranslation();
  const activePreset = matchingPreset(period);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center rounded-md border border-subtle p-0.5">
        {PERIOD_PRESETS.map((days) => (
          <button
            key={days}
            type="button"
            onClick={() => onChange(presetPeriod(days))}
            className={cn("rounded-sm px-2.5 py-1 text-12 font-medium text-secondary hover:bg-layer-1", {
              "bg-layer-1 text-primary": activePreset === days,
            })}
          >
            {t("team_progress.period.last_days", { count: days })}
          </button>
        ))}
      </div>
      <div
        className={cn("flex items-center gap-1.5 rounded-md border border-subtle px-2 py-1 text-12 text-secondary", {
          "border-accent-strong": !activePreset,
        })}
      >
        <CalendarDays className="size-3.5 text-tertiary" />
        <input
          type="date"
          aria-label={t("team_progress.period.start")}
          className="bg-transparent text-12 text-primary outline-none"
          value={period.start_date}
          max={period.end_date}
          onChange={(event) => event.target.value && onChange({ ...period, start_date: event.target.value })}
        />
        <span className="text-tertiary">〜</span>
        <input
          type="date"
          aria-label={t("team_progress.period.end")}
          className="bg-transparent text-12 text-primary outline-none"
          value={period.end_date}
          min={period.start_date}
          onChange={(event) => event.target.value && onChange({ ...period, end_date: event.target.value })}
        />
      </div>
    </div>
  );
}

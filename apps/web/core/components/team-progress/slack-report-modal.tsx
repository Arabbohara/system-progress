/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TSlackReportFrequency, TSlackReportSettingUpdate } from "@plane/types";
import { CustomSelect, EModalPosition, EModalWidth, Input, ModalCore, ToggleSwitch } from "@plane/ui";
import { renderFormattedDate, renderFormattedTime } from "@plane/utils";
// services
import { TeamProgressService } from "@/services/workspace/team-progress.service";

const teamProgressService = new TeamProgressService();

const FREQUENCIES: TSlackReportFrequency[] = ["daily", "weekly", "monthly"];
const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6];
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);

type Props = {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string;
};

export function SlackReportModal(props: Props) {
  const { isOpen, onClose, workspaceSlug } = props;
  const { t } = useTranslation();
  const [webhookUrl, setWebhookUrl] = useState("");
  const [form, setForm] = useState<Required<Omit<TSlackReportSettingUpdate, "webhook_url">>>({
    is_enabled: false,
    frequency: "weekly",
    weekday: 0,
    hour: 9,
  });
  const [isSaving, setIsSaving] = useState(false);

  const { data: setting, mutate } = useSWR(
    isOpen ? `SLACK_REPORT_SETTING_${workspaceSlug}` : null,
    isOpen ? () => teamProgressService.getSlackReportSetting(workspaceSlug) : null,
    { revalidateOnFocus: false }
  );

  useEffect(() => {
    if (!setting) return;
    setForm({
      is_enabled: setting.is_enabled,
      frequency: setting.frequency,
      weekday: setting.weekday,
      hour: setting.hour,
    });
    setWebhookUrl("");
  }, [setting]);

  const weekdayLabel = (weekday: number) => t(`team_progress.slack.weekdays.${weekday}`);
  const frequencyLabel = (frequency: TSlackReportFrequency) => t(`team_progress.slack.frequency.${frequency}`);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const data: TSlackReportSettingUpdate = { ...form };
      if (webhookUrl.trim()) data.webhook_url = webhookUrl.trim();
      const updated = await teamProgressService.updateSlackReportSetting(workspaceSlug, data);
      await mutate(updated, false);
      setToast({ type: TOAST_TYPE.SUCCESS, title: t("success"), message: t("team_progress.slack.saved_toast") });
      onClose();
    } catch (error) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("error"),
        message: (error as { error?: string } | undefined)?.error ?? t("something_went_wrong_please_try_again"),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleRemoveWebhook = async () => {
    try {
      const updated = await teamProgressService.updateSlackReportSetting(workspaceSlug, {
        webhook_url: "",
        is_enabled: false,
      });
      await mutate(updated, false);
    } catch (error) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("error"),
        message: (error as { error?: string } | undefined)?.error ?? t("something_went_wrong_please_try_again"),
      });
    }
  };

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XXL}>
      <div className="flex flex-col gap-5 p-5">
        <div>
          <h3 className="text-16 font-semibold text-primary">{t("team_progress.slack.title")}</h3>
          <p className="mt-1 text-13 text-secondary">{t("team_progress.slack.description")}</p>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="slack-webhook-url" className="text-13 font-medium text-primary">
            {t("team_progress.slack.webhook_url")}
          </label>
          {setting?.webhook_configured && (
            <div className="flex items-center justify-between gap-2 rounded-md bg-layer-1 px-2 py-1.5">
              <code className="truncate text-12 text-secondary">{setting.webhook_url_masked}</code>
              <button
                type="button"
                className="flex-shrink-0 text-12 text-danger-primary hover:underline"
                onClick={handleRemoveWebhook}
              >
                {t("team_progress.slack.remove_webhook")}
              </button>
            </div>
          )}
          <Input
            id="slack-webhook-url"
            type="url"
            value={webhookUrl}
            onChange={(event) => setWebhookUrl(event.target.value)}
            placeholder={
              setting?.webhook_configured
                ? t("team_progress.slack.webhook_replace_placeholder")
                : "https://hooks.slack.com/services/..."
            }
            className="w-full"
          />
          <p className="text-11 text-tertiary">{t("team_progress.slack.webhook_help")}</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <span className="text-13 text-secondary">{t("team_progress.slack.schedule")}</span>
          <CustomSelect
            value={form.frequency}
            onChange={(frequency: TSlackReportFrequency) => setForm((current) => ({ ...current, frequency }))}
            label={frequencyLabel(form.frequency)}
            input
          >
            {FREQUENCIES.map((frequency) => (
              <CustomSelect.Option key={frequency} value={frequency}>
                {frequencyLabel(frequency)}
              </CustomSelect.Option>
            ))}
          </CustomSelect>
          {form.frequency === "weekly" && (
            <CustomSelect
              value={form.weekday}
              onChange={(weekday: number) => setForm((current) => ({ ...current, weekday }))}
              label={weekdayLabel(form.weekday)}
              input
            >
              {WEEKDAYS.map((weekday) => (
                <CustomSelect.Option key={weekday} value={weekday}>
                  {weekdayLabel(weekday)}
                </CustomSelect.Option>
              ))}
            </CustomSelect>
          )}
          {form.frequency === "monthly" && (
            <span className="text-13 text-secondary">{t("team_progress.slack.monthly_day")}</span>
          )}
          <CustomSelect
            value={form.hour}
            onChange={(hour: number) => setForm((current) => ({ ...current, hour }))}
            label={`${String(form.hour).padStart(2, "0")}:00`}
            maxHeight="md"
            input
          >
            {HOURS.map((hour) => (
              <CustomSelect.Option key={hour} value={hour}>
                {`${String(hour).padStart(2, "0")}:00`}
              </CustomSelect.Option>
            ))}
          </CustomSelect>
        </div>
        <p className="-mt-3 text-11 text-tertiary">{t("team_progress.slack.schedule_help")}</p>

        <button
          type="button"
          className="flex w-fit items-center gap-2"
          onClick={() => setForm((current) => ({ ...current, is_enabled: !current.is_enabled }))}
        >
          <ToggleSwitch value={form.is_enabled} onChange={() => {}} size="sm" />
          <span className="text-13 text-primary">{t("team_progress.slack.enabled")}</span>
        </button>

        {setting?.last_sent_at && (
          <p className="text-12 text-tertiary">
            {t("team_progress.slack.last_sent", {
              date: `${renderFormattedDate(setting.last_sent_at)} ${renderFormattedTime(setting.last_sent_at)}`,
            })}
          </p>
        )}

        <div className="flex justify-end gap-2 border-t border-subtle pt-4">
          <Button variant="secondary" size="lg" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button variant="primary" size="lg" onClick={handleSave} loading={isSaving}>
            {t("save")}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
}

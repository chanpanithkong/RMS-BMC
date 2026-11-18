"use client"

import * as React from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { RecordForm, validateFields, type Field, type FieldValue } from "@/components/rms/crud"
import { Panel } from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import { can, useSession } from "@/lib/api/session"
import { apiMessage, useApi } from "@/lib/api/use-api"

export interface SettingField extends Field {
  /** Path inside the settings group, e.g. "variance_tolerance.USD" (default: the field name). */
  path?: string
  /** "number" fields are stored as strings unless `asNumber` (the backend keeps money as strings). */
  asNumber?: boolean
  /** Comma-separated list stored as an array. */
  list?: boolean
}

const getPath = (o: Record<string, unknown>, path: string) =>
  path.split(".").reduce<unknown>((v, k) => (v && typeof v === "object" ? (v as Record<string, unknown>)[k] : undefined), o)

function setPath(o: Record<string, unknown>, path: string, value: unknown) {
  const keys = path.split(".")
  const out = { ...o }
  let cur: Record<string, unknown> = out
  keys.slice(0, -1).forEach((k) => {
    cur[k] = { ...((cur[k] as Record<string, unknown>) ?? {}) }
    cur = cur[k] as Record<string, unknown>
  })
  cur[keys[keys.length - 1]] = value
  return out
}

/**
 * Edit one settings group (`GET/PUT /settings/{key}`). Values shown are the effective ones for this branch;
 * saving writes this branch's override, or the restaurant-wide default when "all branches" is chosen.
 * Financial groups need settings.approve, which the backend checks.
 */
export function SettingsForm({
  group,
  title,
  description,
  fields,
  allowRestaurantWide = true,
}: {
  group: string
  title: string
  description?: string
  fields: SettingField[]
  allowRestaurantWide?: boolean
}) {
  const { me } = useSession()
  const editable = can(me, "settings.manage")
  const { data, loading, reload } = useApi(
    () => api<{ key: string; value: Record<string, unknown> }>("GET", `/settings/${group}`).then((r) => r.value),
    [group],
    null as Record<string, unknown> | null
  )
  const toForm = React.useCallback(
    (v: Record<string, unknown>) =>
      Object.fromEntries(
        fields.map((f) => {
          const raw = getPath(v, f.path ?? f.name)
          const val: FieldValue = f.type === "switch" ? Boolean(raw) : Array.isArray(raw) ? raw.join(", ") : raw === null || raw === undefined ? "" : String(raw)
          return [f.name, val]
        })
      ),
    [fields]
  )
  const [values, setValues] = React.useState<Record<string, FieldValue> | null>(null)
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  const [wide, setWide] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const shown = values ?? (data ? toForm(data) : null)

  const submit = async () => {
    if (!data || !shown) return
    const errs = validateFields(fields, shown)
    setErrors(errs)
    if (Object.keys(errs).length) return
    let next: Record<string, unknown> = {}
    // Only send the keys this form owns (nested objects are sent whole).
    for (const f of fields) {
      const top = (f.path ?? f.name).split(".")[0]
      if (!(top in next)) next[top] = data[top]
    }
    for (const f of fields) {
      const v = shown[f.name]
      const out =
        f.type === "switch"
          ? Boolean(v)
          : f.list
            ? String(v).split(",").map((s) => s.trim()).filter(Boolean)
            : f.type === "number" && f.asNumber
              ? Number(v)
              : v === ""
                ? null
                : String(v)
      next = setPath(next, f.path ?? f.name, out)
    }
    setSaving(true)
    try {
      await api("PUT", `/settings/${group}`, { body: { value: next, branch_scoped: !wide } })
      toast.success(`${title} saved`)
      setValues(null)
      reload()
    } catch (e) {
      toast.error(apiMessage(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Panel
      title={title}
      description={description}
      className="max-w-3xl"
      actions={
        editable && (
          <Button disabled={!values || saving} onClick={() => void submit()}>
            {saving ? "Saving…" : "Save"}
          </Button>
        )
      }
    >
      {loading || !shown ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <div className="grid gap-3">
          <fieldset disabled={!editable} className="contents">
            <RecordForm
              fields={fields}
              values={shown}
              errors={errors}
              setValue={(k, v) => setValues({ ...shown, [k]: v })}
            />
          </fieldset>
          {editable && allowRestaurantWide && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={wide} onChange={(e) => setWide(e.target.checked)} />
              Save as the default for all branches (otherwise only this branch changes)
            </label>
          )}
          {!editable && <p className="text-xs text-muted-foreground">You can view these settings but not change them.</p>}
        </div>
      )}
    </Panel>
  )
}

"use client"

import * as React from "react"
import { Plus, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { RecordDialog, type Field } from "@/components/rms/crud"
import { confirmAction } from "@/components/rms/dialog-host"
import {
  EmptyState,
  LinkButton,
  Page,
  PageHeader,
  Panel,
  KV,
} from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import { loadTables } from "@/lib/api/pos"
import { can, useSession } from "@/lib/api/session"
import { act, save, useApi } from "@/lib/api/use-api"
import { rms, useRms } from "@/lib/rms/store"
import { cn } from "@/lib/utils"

export default function FloorEditorPage() {
  const { tables } = useRms()
  const { me } = useSession()
  const manage = can(me, "tables.manage")
  // Dining areas and tables come from the server; positions are saved when a drag ends.
  const areaList = useApi(() => api<{ id: string; name: string; sort_order: number; is_active: boolean }[]>("GET", "/dining-areas"), [], [])
  const reloadTables = React.useCallback(() => void loadTables().catch(() => undefined), [])
  React.useEffect(reloadTables, [reloadTables])
  const allAreas = areaList.data.filter((a) => a.is_active).map((a) => a.name)
  const areaId = (name: unknown) => areaList.data.find((a) => a.name === name)?.id
  const [picked, setArea] = React.useState("")
  const area = allAreas.includes(picked) ? picked : (allAreas[0] ?? "")
  const [selId, setSelId] = React.useState<string | null>(null)
  const [dialog, setDialog] = React.useState<"table" | "area" | "edit" | null>(
    null
  )
  const canvas = React.useRef<HTMLDivElement>(null)
  const drag = React.useRef<{ id: string; dx: number; dy: number; moved?: boolean } | null>(null)
  const sel = tables.find((t) => t.id === selId)
  const fields: Field[] = [
    {
      name: "code",
      label: "Table code",
      required: true,
      half: true,
      validate: (v) =>
        tables.some(
          (t) => t.code === v && t.id !== (dialog === "edit" ? selId : "")
        )
          ? "This code already exists in this branch"
          : undefined,
    },
    {
      name: "capacity",
      label: "Capacity",
      type: "number",
      required: true,
      half: true,
      min: 1,
      max: 50,
    },
    {
      name: "shape",
      label: "Shape",
      type: "select",
      options: ["square", "round", "rect"],
      required: true,
      half: true,
    },
    {
      name: "area",
      label: "Dining area",
      type: "select",
      options: allAreas,
      required: true,
      half: true,
    },
  ]
  const move = (e: React.PointerEvent) => {
    if (!drag.current || !canvas.current) return
    const r = canvas.current.getBoundingClientRect()
    const x = Math.max(
      0,
      Math.min(86, ((e.clientX - r.left - drag.current.dx) / r.width) * 100)
    )
    const y = Math.max(
      0,
      Math.min(80, ((e.clientY - r.top - drag.current.dy) / r.height) * 100)
    )
    const t = tables.find((f) => f.id === drag.current!.id)
    if (t) rms.saveTable({ ...t, x: Math.round(x), y: Math.round(y) })
    drag.current.moved = true
  }
  /** Save the new position once; a stale version (someone else edited) shows the server's message. */
  const drop = () => {
    const d = drag.current
    drag.current = null
    if (!d?.moved) return
    const t = tables.find((f) => f.id === d.id)
    if (t) void act(() => api("PATCH", `/tables/${t.id}`, { body: { layout_x: String(t.x), layout_y: String(t.y), version: t.version } }), undefined, reloadTables)
  }
  return (
    <Page>
      <PageHeader
        title="Area editor"
        description="Drag tables to arrange the floor. Codes must be unique per branch."
        actions={
          <>
            <LinkButton href="/tables" variant="outline">
              Done
            </LinkButton>
            <Button variant="outline" disabled={!manage} onClick={() => setDialog("area")}>
              <Plus />
              New area
            </Button>
            <Button disabled={!manage || !allAreas.length} onClick={() => setDialog("table")}>
              <Plus />
              New table
            </Button>
          </>
        }
      />
      <div className="flex w-fit rounded-lg bg-muted p-1">
        {allAreas.map((a) => (
          <button
            key={a}
            onClick={() => setArea(a)}
            className={cn(
              "rounded-md px-3 py-1 text-sm font-medium",
              a === area ? "bg-background shadow-sm" : "text-muted-foreground"
            )}
          >
            {a}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[1fr_280px]">
        <div className="overflow-x-auto rounded-xl border bg-card">
          <div
            ref={canvas}
            onPointerMove={move}
            onPointerUp={drop}
            className="relative h-[520px] min-w-[780px] touch-none bg-[radial-gradient(var(--border)_1px,transparent_1px)] [background-size:20px_20px]"
          >
            {tables
              .filter((t) => t.area === area)
              .map((t) => (
                <button
                  key={t.id}
                  style={{ left: `${t.x}%`, top: `${t.y}%` }}
                  onPointerDown={(e) => {
                    setSelId(t.id)
                    if (!manage) return
                    const r = e.currentTarget.getBoundingClientRect()
                    drag.current = {
                      id: t.id,
                      dx: e.clientX - r.left,
                      dy: e.clientY - r.top,
                    }
                    e.currentTarget.setPointerCapture(e.pointerId)
                  }}
                  className={cn(
                    "absolute flex cursor-grab flex-col items-center justify-center border-2 bg-background font-bold active:cursor-grabbing",
                    t.id === selId
                      ? "border-primary ring-3 ring-primary/30"
                      : "border-border",
                    t.shape === "round"
                      ? "size-24 rounded-full"
                      : t.shape === "rect"
                        ? "h-24 w-44 rounded-xl"
                        : "h-24 w-28 rounded-xl"
                  )}
                >
                  {t.code}
                  <span className="text-xs font-normal text-muted-foreground">
                    {t.capacity} seats
                  </span>
                </button>
              ))}
          </div>
        </div>
        <Panel title={sel ? `Table ${sel.code}` : "Selected table"}>
          {sel ? (
            <>
              <KV
                items={[
                  ["Area", sel.area],
                  ["Capacity", sel.capacity],
                  ["Shape", sel.shape],
                  ["Position", `${sel.x}, ${sel.y}`],
                ]}
              />
              <div className="mt-3 flex gap-2">
                <Button
                  variant="outline"
                  className="flex-1"
                  disabled={!manage}
                  onClick={() => setDialog("edit")}
                >
                  Edit
                </Button>
                <Button
                  variant="destructive"
                  disabled={!manage}
                  aria-label="Deactivate table"
                  onClick={() =>
                    confirmAction({
                      title: `Deactivate ${sel.code}?`,
                      effect:
                        "It disappears from the floor plan. History is kept.",
                      destructive: true,
                      confirmLabel: "Deactivate",
                      onConfirm: () =>
                        void act(() => api("PATCH", `/tables/${sel.id}`, { body: { is_active: false, version: sel.version } }), `${sel.code} deactivated`, () => {
                          setSelId(null)
                          reloadTables()
                        }),
                    })
                  }
                >
                  <Trash2 />
                </Button>
              </div>
            </>
          ) : (
            <EmptyState
              title="Select a table"
              description="Click a table to see and change its details."
            />
          )}
        </Panel>
      </div>
      <RecordDialog
        open={dialog === "table" || dialog === "edit"}
        onOpenChange={(o) => !o && setDialog(null)}
        title={dialog === "edit" ? "Edit table" : "New table"}
        fields={fields}
        initial={
          dialog === "edit" && sel
            ? {
                code: sel.code,
                capacity: String(sel.capacity),
                shape: sel.shape,
                area: sel.area,
              }
            : { area, shape: "square", capacity: "4" }
        }
        onSubmit={(v) => {
          const body = { table_code: String(v.code), capacity: Number(v.capacity), shape: v.shape, dining_area_id: areaId(v.area) }
          return save(() =>
            dialog === "edit" && sel
              ? api("PATCH", `/tables/${sel.id}`, { body: { ...body, version: sel.version } })
              : api("POST", "/tables", { body: { ...body, layout_x: "40", layout_y: "40" } })
          ).then(() => {
            toast.success("Table saved")
            reloadTables()
          })
        }}
      />
      <RecordDialog
        open={dialog === "area"}
        onOpenChange={(o) => !o && setDialog(null)}
        title="New dining area"
        fields={[{ name: "name", label: "Area name", required: true }]}
        onSubmit={(v) =>
          save(() => api("POST", "/dining-areas", { body: { name: String(v.name), sort_order: areaList.data.length + 1 } })).then(() => {
            areaList.reload()
            setArea(String(v.name))
          })
        }
      />
    </Page>
  )
}

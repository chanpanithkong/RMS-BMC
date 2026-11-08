"use client"

import * as React from "react"
import { Pencil, Plus } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import {
  DataTable,
  type Column,
  type Filter,
  type RowAction,
} from "@/components/rms/data-table"
import { FormRow, SimpleSelect, opts } from "@/components/rms/kit"
import { cn } from "@/lib/utils"

export type FieldValue = string | boolean
export interface Field {
  name: string
  label: string
  type?:
    | "text"
    | "number"
    | "date"
    | "time"
    | "select"
    | "textarea"
    | "switch"
    | "email"
    | "tel"
    | "file"
  required?: boolean
  options?: string[]
  half?: boolean
  hint?: string
  min?: number
  max?: number
  validate?: (
    v: FieldValue,
    all: Record<string, FieldValue>
  ) => string | undefined
}

export function RecordForm({
  fields,
  values,
  setValue,
  errors,
}: {
  fields: Field[]
  values: Record<string, FieldValue>
  setValue: (k: string, v: FieldValue) => void
  errors: Record<string, string>
}) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {fields.map((f) => {
        const id = `f-${f.name}`
        const v = values[f.name] ?? (f.type === "switch" ? false : "")
        return (
          <div
            key={f.name}
            className={cn(f.half ? "col-span-2 sm:col-span-1" : "col-span-2")}
          >
            {f.type === "switch" ? (
              <label
                htmlFor={id}
                className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm"
              >
                <span>
                  {f.label}
                  {f.hint && (
                    <span className="block text-xs text-muted-foreground">
                      {f.hint}
                    </span>
                  )}
                </span>
                <Switch
                  id={id}
                  checked={Boolean(v)}
                  onCheckedChange={(c) => setValue(f.name, Boolean(c))}
                />
              </label>
            ) : (
              <FormRow
                label={f.label}
                required={f.required}
                error={errors[f.name]}
                htmlFor={id}
                hint={f.hint}
              >
                {f.type === "select" ? (
                  <SimpleSelect
                    id={id}
                    value={String(v)}
                    onChange={(x) => setValue(f.name, x)}
                    options={opts(...(f.options ?? []))}
                    placeholder="Select…"
                    invalid={!!errors[f.name]}
                  />
                ) : f.type === "textarea" ? (
                  <Textarea
                    id={id}
                    value={String(v)}
                    onChange={(e) => setValue(f.name, e.target.value)}
                    aria-invalid={!!errors[f.name] || undefined}
                  />
                ) : f.type === "file" ? (
                  <Input
                    id={id}
                    type="file"
                    onChange={(e) =>
                      setValue(f.name, e.target.files?.[0]?.name ?? "")
                    }
                  />
                ) : (
                  <Input
                    id={id}
                    type={f.type ?? "text"}
                    min={f.min}
                    max={f.max}
                    step={f.type === "number" ? "any" : undefined}
                    value={String(v)}
                    onChange={(e) => setValue(f.name, e.target.value)}
                    aria-invalid={!!errors[f.name] || undefined}
                  />
                )}
              </FormRow>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function validateFields(
  fields: Field[],
  values: Record<string, FieldValue>
) {
  const errors: Record<string, string> = {}
  for (const f of fields) {
    const v = values[f.name]
    if (
      f.required &&
      f.type !== "switch" &&
      (v === undefined || String(v).trim() === "")
    )
      errors[f.name] = `${f.label} is required`
    else if (f.type === "number" && v !== "" && v !== undefined) {
      const n = Number(v)
      if (Number.isNaN(n)) errors[f.name] = "Enter a number"
      else if (f.min !== undefined && n < f.min)
        errors[f.name] = `Must be at least ${f.min}`
      else if (f.max !== undefined && n > f.max)
        errors[f.name] = `Must be ${f.max} or less`
    }
    const custom = f.validate?.(v ?? "", values)
    if (custom) errors[f.name] = custom
  }
  return errors
}

export function RecordDialog({
  open,
  onOpenChange,
  title,
  description,
  fields,
  initial,
  submitLabel = "Save",
  onSubmit,
  wide,
}: {
  open: boolean
  onOpenChange: (o: boolean) => void
  title: string
  description?: string
  fields: Field[]
  initial?: Record<string, FieldValue>
  submitLabel?: string
  onSubmit: (v: Record<string, FieldValue>) => void
  wide?: boolean
}) {
  const [values, setValues] = React.useState<Record<string, FieldValue>>(
    initial ?? {}
  )
  const [errors, setErrors] = React.useState<Record<string, string>>({})
  const [seen, setSeen] = React.useState(open)
  if (open !== seen) {
    setSeen(open)
    if (open) {
      setValues(initial ?? {})
      setErrors({})
    }
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    const errs = validateFields(fields, values)
    setErrors(errs)
    if (Object.keys(errs).length) return
    onSubmit(values)
    onOpenChange(false)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn(
          "max-h-[90vh] overflow-y-auto",
          wide ? "sm:max-w-2xl" : "sm:max-w-lg"
        )}
      >
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description && (
              <DialogDescription>{description}</DialogDescription>
            )}
          </DialogHeader>
          <RecordForm
            fields={fields}
            values={values}
            errors={errors}
            setValue={(k, v) => setValues((s) => ({ ...s, [k]: v }))}
          />
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit">{submitLabel}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Table plus create/edit dialog, for the many back-office master-data lists. */
export function CrudTable<T extends { id: string }>({
  noun,
  seed,
  columns,
  fields,
  filters,
  extraActions,
  toRow,
  toForm,
  canEdit = true,
  canAdd = true,
  addLabel,
  onRowClick,
  pageSize,
  toolbar,
  searchPlaceholder,
  description,
}: {
  noun: string
  seed: T[]
  columns: Column<T>[]
  fields: Field[]
  filters?: Filter<T>[]
  canEdit?: boolean
  canAdd?: boolean
  addLabel?: string
  extraActions?: (row: T, update: (patch: Partial<T>) => void) => RowAction<T>[]
  toRow: (v: Record<string, FieldValue>, existing?: T) => T
  toForm?: (row: T) => Record<string, FieldValue>
  onRowClick?: (row: T) => void
  pageSize?: number
  toolbar?: React.ReactNode
  searchPlaceholder?: string
  description?: string
}) {
  const [rows, setRows] = React.useState(seed)
  const [editing, setEditing] = React.useState<T | null>(null)
  const [open, setOpen] = React.useState(false)
  const defaultForm = (r: T) =>
    Object.fromEntries(
      fields
        .map((f) => [
          f.name,
          ((r as Record<string, unknown>)[f.name] ?? "") as FieldValue,
        ])
        .map(([k, v]) => [k, typeof v === "boolean" ? v : String(v)])
    )
  return (
    <>
      <DataTable
        rows={rows}
        columns={columns}
        filters={filters}
        onRowClick={onRowClick}
        pageSize={pageSize}
        exportName={noun.toLowerCase().replaceAll(" ", "-")}
        searchPlaceholder={searchPlaceholder}
        toolbar={
          <>
            {toolbar}
            {canAdd && (
              <Button
                onClick={() => {
                  setEditing(null)
                  setOpen(true)
                }}
              >
                <Plus />
                {addLabel ?? `New ${noun.toLowerCase()}`}
              </Button>
            )}
          </>
        }
        emptyTitle={`No ${noun.toLowerCase()} records`}
        rowActions={(row) => [
          ...(canEdit
            ? [
                {
                  label: "Edit",
                  icon: Pencil,
                  onClick: (r: T) => {
                    setEditing(r)
                    setOpen(true)
                  },
                },
              ]
            : []),
          ...(extraActions?.(row, (patch) =>
            setRows((rs) =>
              rs.map((x) => (x.id === row.id ? { ...x, ...patch } : x))
            )
          ) ?? []),
        ]}
      />
      <RecordDialog
        open={open}
        onOpenChange={setOpen}
        title={
          editing
            ? `Edit ${noun.toLowerCase()}`
            : (addLabel ?? `New ${noun.toLowerCase()}`)
        }
        description={description}
        fields={fields}
        initial={editing ? (toForm ?? defaultForm)(editing) : undefined}
        onSubmit={(v) => {
          const row = toRow(v, editing ?? undefined)
          setRows((rs) =>
            editing
              ? rs.map((x) => (x.id === editing.id ? row : x))
              : [row, ...rs]
          )
          toast.success(`${noun} ${editing ? "updated" : "created"}`)
        }}
      />
    </>
  )
}

export const newId = () => `x${Math.random().toString(36).slice(2, 9)}`

"use client"

import * as React from "react"
import {
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Columns3,
  Download,
  MoreHorizontal,
  Search,
  type LucideIcon,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { EmptyState, SimpleSelect, opts } from "@/components/rms/kit"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

export interface Column<T> {
  key: string
  header: string
  render?: (row: T) => React.ReactNode
  value?: (row: T) => string | number
  align?: "left" | "right" | "center"
  hidden?: boolean
  sortable?: boolean
}
export interface RowAction<T> {
  label: string
  icon?: LucideIcon
  onClick: (row: T) => void
  destructive?: boolean
  hidden?: (row: T) => boolean
}
export interface Filter<T> {
  key: string
  label: string
  options?: string[]
  value?: (row: T) => string
}

const raw = <T,>(c: Column<T>, r: T): string | number => {
  if (c.value) return c.value(r)
  const v = (r as Record<string, unknown>)[c.key]
  return typeof v === "number" ? v : String(v ?? "")
}

export function DataTable<T extends { id: string }>({
  rows,
  columns,
  filters = [],
  rowActions,
  onRowClick,
  toolbar,
  pageSize = 10,
  exportName = "export",
  searchPlaceholder = "Search…",
  searchValue,
  emptyTitle = "Nothing here yet",
  emptyDescription,
  initialQuery = "",
}: {
  rows: T[]
  columns: Column<T>[]
  filters?: Filter<T>[]
  rowActions?: (row: T) => RowAction<T>[] | RowAction<T>[]
  onRowClick?: (row: T) => void
  toolbar?: React.ReactNode
  pageSize?: number
  exportName?: string
  searchPlaceholder?: string
  searchValue?: (row: T) => string
  emptyTitle?: string
  emptyDescription?: string
  initialQuery?: string
}) {
  const [q, setQ] = React.useState(initialQuery)
  const [sel, setSel] = React.useState<Record<string, string>>({})
  const [sort, setSort] = React.useState<{ key: string; dir: 1 | -1 } | null>(
    null
  )
  const [hidden, setHidden] = React.useState<Set<string>>(
    () => new Set(columns.filter((c) => c.hidden).map((c) => c.key))
  )
  const [page, setPage] = React.useState(0)

  const visible = columns.filter((c) => !hidden.has(c.key))

  const filtered = React.useMemo(() => {
    const needle = q.trim().toLowerCase()
    let out = rows.filter((r) => {
      if (needle) {
        const hay = searchValue
          ? searchValue(r)
          : columns.map((c) => raw(c, r)).join(" ")
        if (!hay.toLowerCase().includes(needle)) return false
      }
      return filters.every((f) => {
        const v = sel[f.key]
        if (!v || v === "All") return true
        const cell = f.value
          ? f.value(r)
          : String((r as Record<string, unknown>)[f.key] ?? "")
        return cell === v
      })
    })
    if (sort) {
      const col = columns.find((c) => c.key === sort.key)
      if (col)
        out = [...out].sort((a, b) => {
          const x = raw(col, a),
            y = raw(col, b)
          return (
            (typeof x === "number" && typeof y === "number"
              ? x - y
              : String(x).localeCompare(String(y))) * sort.dir
          )
        })
    }
    return out
  }, [rows, q, sel, sort, columns, filters, searchValue])

  const pages = Math.max(Math.ceil(filtered.length / pageSize), 1)
  const current = Math.min(page, pages - 1)
  const slice = filtered.slice(
    current * pageSize,
    current * pageSize + pageSize
  )

  const exportCsv = () => {
    const esc = (v: unknown) => `"${String(v).replaceAll('"', '""')}"`
    const csv = [
      visible.map((c) => esc(c.header)).join(","),
      ...filtered.map((r) => visible.map((c) => esc(raw(c, r))).join(",")),
    ].join("\n")
    const url = URL.createObjectURL(
      new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" })
    )
    const a = Object.assign(document.createElement("a"), {
      href: url,
      download: `${exportName}.csv`,
    })
    a.click()
    URL.revokeObjectURL(url)
    toast.success(`Exported ${filtered.length} rows`)
  }

  const options = (f: Filter<T>) =>
    f.options ??
    [
      ...new Set(
        rows.map((r) =>
          f.value
            ? f.value(r)
            : String((r as Record<string, unknown>)[f.key] ?? "")
        )
      ),
    ]
      .filter(Boolean)
      .sort()

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-48 flex-1 sm:max-w-72">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            aria-label="Search table"
            value={q}
            onChange={(e) => {
              setQ(e.target.value)
              setPage(0)
            }}
            placeholder={searchPlaceholder}
            className="pl-8"
          />
        </div>
        {filters.map((f) => (
          <SimpleSelect
            key={f.key}
            aria-label={f.label}
            className="w-auto min-w-32"
            value={sel[f.key] ?? "All"}
            onChange={(v) => {
              setSel((s) => ({ ...s, [f.key]: v }))
              setPage(0)
            }}
            options={[
              { value: "All", label: `All ${f.label.toLowerCase()}` },
              ...opts(...options(f)),
            ]}
          />
        ))}
        <div className="ml-auto flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger
              render={<Button variant="outline" aria-label="Choose columns" />}
            >
              <Columns3 />
              <span className="hidden sm:inline">Columns</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuGroup>
                <DropdownMenuLabel>Visible columns</DropdownMenuLabel>
                {columns.map((c) => (
                  <DropdownMenuCheckboxItem
                    key={c.key}
                    checked={!hidden.has(c.key)}
                    onCheckedChange={() =>
                      setHidden((h) => {
                        const n = new Set(h)
                        if (n.has(c.key)) n.delete(c.key)
                        else n.add(c.key)
                        return n
                      })
                    }
                  >
                    {c.header}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="outline" onClick={exportCsv}>
            <Download />
            <span className="hidden sm:inline">Export</span>
          </Button>
          {toolbar}
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title={emptyTitle}
          description={
            emptyDescription ?? "Try a different search or clear the filters."
          }
        />
      ) : (
        <div className="max-h-[65vh] overflow-auto rounded-lg border">
          <table className="w-full min-w-max caption-bottom text-sm">
            <thead className="sticky top-0 z-10 bg-muted/95 backdrop-blur">
              <tr>
                {visible.map((c) => (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={
                      sort?.key === c.key
                        ? sort.dir === 1
                          ? "ascending"
                          : "descending"
                        : undefined
                    }
                    className={cn(
                      "h-9 px-3 font-medium text-muted-foreground",
                      c.align === "right"
                        ? "text-right"
                        : c.align === "center"
                          ? "text-center"
                          : "text-left"
                    )}
                  >
                    {c.sortable === false ? (
                      c.header
                    ) : (
                      <button
                        className="inline-flex items-center gap-1 hover:text-foreground"
                        onClick={() =>
                          setSort((s) =>
                            s?.key === c.key
                              ? s.dir === 1
                                ? { key: c.key, dir: -1 }
                                : null
                              : { key: c.key, dir: 1 }
                          )
                        }
                      >
                        {c.header}
                        {sort?.key === c.key &&
                          (sort.dir === 1 ? (
                            <ArrowUp className="size-3" />
                          ) : (
                            <ArrowDown className="size-3" />
                          ))}
                      </button>
                    )}
                  </th>
                ))}
                {rowActions && (
                  <th className="w-10">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {slice.map((r) => {
                const actions = (rowActions?.(r) ?? []).filter(
                  (a) => !a.hidden?.(r)
                )
                return (
                  <tr
                    key={r.id}
                    className={cn(
                      "border-t transition-colors hover:bg-muted/40",
                      onRowClick && "cursor-pointer"
                    )}
                    onClick={() => onRowClick?.(r)}
                  >
                    {visible.map((c) => (
                      <td
                        key={c.key}
                        className={cn(
                          "px-3 py-2 align-middle whitespace-nowrap",
                          c.align === "right" && "tabular text-right",
                          c.align === "center" && "text-center"
                        )}
                      >
                        {c.render
                          ? c.render(r)
                          : raw(c, r) === ""
                            ? "—"
                            : String(raw(c, r))}
                      </td>
                    ))}
                    {rowActions && (
                      <td
                        className="px-1 text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {actions.length > 0 && (
                          <DropdownMenu>
                            <DropdownMenuTrigger
                              render={
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  aria-label="Row actions"
                                />
                              }
                            >
                              <MoreHorizontal />
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-52">
                              {actions.map((a) => (
                                <DropdownMenuItem
                                  key={a.label}
                                  variant={
                                    a.destructive ? "destructive" : "default"
                                  }
                                  onClick={() => a.onClick(r)}
                                >
                                  {a.icon && <a.icon />}
                                  {a.label}
                                </DropdownMenuItem>
                              ))}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {filtered.length > 0 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="tabular">
            {filtered.length} {filtered.length === 1 ? "record" : "records"}
          </span>
          <div className="flex items-center gap-1">
            <span className="tabular mr-1">
              Page {current + 1} of {pages}
            </span>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Previous page"
              disabled={current === 0}
              onClick={() => setPage(current - 1)}
            >
              <ChevronLeft />
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Next page"
              disabled={current >= pages - 1}
              onClick={() => setPage(current + 1)}
            >
              <ChevronRight />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

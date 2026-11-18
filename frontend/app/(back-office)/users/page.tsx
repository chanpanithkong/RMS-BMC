"use client"

import * as React from "react"
import { Ban, Check, KeyRound, LogOut, MonitorSmartphone, Unlock } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { CrudTable, RecordDialog } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Notice, Page, PageHeader, PageTabs, Panel, StatusBadge, useTab } from "@/components/rms/kit"
import { api } from "@/lib/api/client"
import { can, useSession } from "@/lib/api/session"
import { act, apiMessage, num, save, useApi, when } from "@/lib/api/use-api"

interface User {
  id: string
  username: string
  full_name: string
  email: string | null
  phone: string | null
  preferred_language: string
  status: string
  roles: { code: string; name: string }[]
  branches: { id: string; code: string; name_en: string }[]
  last_login_at: string | null
  mfa_enabled: boolean
  must_change_password: boolean
}
interface Role {
  id: string
  code: string
  name: string
  description: string | null
  is_system: boolean
  permissions: string[]
  limits: Record<string, string>
}
const LIMITS: Record<string, string> = {
  discount_pct: "Discount up to (%)",
  discount_amount: "Discount up to (USD)",
  void: "Void up to (USD)",
  refund: "Refund up to (USD)",
  cash_variance: "Cash variance up to (USD)",
  adjustment_value: "Stock adjustment up to (USD)",
  po_amount: "Purchase order up to (USD)",
  expense: "Expense up to (USD)",
  credit_override: "Credit override up to (USD)",
}
const EVENTS: Record<string, string> = {
  Login: "Signed in",
  LoginFailed: "Wrong password",
  LoginLocked: "Sign-in refused (locked)",
  Lockout: "Account locked",
  Logout: "Signed out",
  PinSwitch: "Switched user with PIN",
  PinFailed: "Wrong PIN",
  PasswordResetRequested: "Password reset requested",
}

export default function UsersPage() {
  const { me } = useSession()
  const manage = can(me, "users.manage")
  const [tab, setTab] = useTab("users")
  const users = useApi(async () => (await api<{ data: User[] }>("GET", "/users", { query: { page_size: 200 } })).data, [], [])
  const roles = useApi(() => api<Role[]>("GET", "/roles"), [], [])
  const perms = useApi(() => api<{ code: string; module: string; description: string }[]>("GET", "/permissions"), [], [])
  const authEvents = useApi(
    async () => (await api<{ data: { id: string; username: string; event: string; ip: string | null; device: string | null; occurred_at: string }[] }>("GET", "/users/auth-events", { query: { page_size: 200 } })).data,
    [tab === "auth"],
    []
  )
  const approvals = useApi(
    async () =>
      can(me, "audit.view")
        ? (await api<{ data: { id: number; occurred_at: string; actor_user_id: string | null; after_data: Record<string, unknown> | null; reason: string | null }[] }>("GET", "/audit-logs", { query: { action: "approval.granted", page_size: 200 } })).data
        : [],
    [tab === "approvals", me?.id],
    []
  )
  const [sessionsFor, setSessionsFor] = React.useState<User | null>(null)
  const sessions = useApi(
    () => (sessionsFor ? api<{ id: string; ip: string | null; user_agent: string | null; created_at: string; last_used_at: string | null; expires_at: string; revoked_at: string | null }[]>("GET", `/users/${sessionsFor.id}/sessions`) : Promise.resolve([])),
    [sessionsFor?.id],
    []
  )
  const [resetFor, setResetFor] = React.useState<User | null>(null)
  const [now] = React.useState(() => Date.now())
  const [roleId, setRoleId] = React.useState("")
  const role = roles.data.find((r) => r.id === roleId) ?? roles.data[0]
  const [draftPerms, setDraftPerms] = React.useState<string[] | null>(null)
  const [draftLimits, setDraftLimits] = React.useState<Record<string, string> | null>(null)
  const userName = (id: string | null) => users.data.find((u) => u.id === id)?.full_name ?? "—"
  const branchOpts = me?.branches ?? []

  const rows = users.data.map((u) => ({
    ...u,
    roleNames: u.roles.map((r) => r.name).join(", "),
    branchNames: u.branches.map((b) => b.name_en).join(", "),
    last: u.last_login_at ? when(u.last_login_at) : "Never",
  }))
  const modules = [...new Set(perms.data.map((p) => p.module))]
  const shownPerms = draftPerms ?? role?.permissions ?? []
  const shownLimits = draftLimits ?? role?.limits ?? {}
  const daysSince = (iso: string | null) => (iso ? Math.floor((now - Date.parse(iso)) / 86_400_000) : null)

  return (
    <Page>
      <PageHeader title="Users & roles" description="Staff accounts, what each role may do, approval limits and sign-in activity." />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "users", label: "Users", count: rows.length },
          { value: "roles", label: "Roles & permissions" },
          { value: "auth", label: "Sign-in history" },
          { value: "approvals", label: "Approvals log" },
          { value: "review", label: "Access review" },
        ]}
      />
      {tab === "users" && (
        <CrudTable
          noun="User"
          rows={rows}
          canAdd={manage}
          canEdit={manage}
          description="New users must change the temporary password when they first sign in."
          onSave={(v, e) => {
            const roleCodes = String(v.roles ?? "")
              .split(",")
              .map((s) => s.trim())
              .map((n) => roles.data.find((r) => r.name === n || r.code === n)?.code)
              .filter(Boolean)
            const branchIds = branchOpts.filter((b) => String(v.branches ?? "").split(",").map((s) => s.trim()).includes(b.name_en)).map((b) => b.id)
            const common = {
              full_name: v.name,
              email: String(v.email ?? "") || null,
              phone: String(v.phone ?? "") || null,
              preferred_language: v.lang === "Khmer" ? "km" : "en",
              role_codes: roleCodes,
              branch_ids: branchIds,
            }
            return save(() =>
              e
                ? api("PATCH", `/users/${e.id}`, { body: common })
                : api("POST", "/users", { body: { ...common, username: v.username, temporary_password: v.password, pin: String(v.pin ?? "") || undefined } })
            ).then(users.reload)
          }}
          filters={[{ key: "status", label: "Status", options: ["Active", "Inactive", "Locked"] }]}
          columns={[
            { key: "full_name", header: "Name", render: (u) => <span className="font-medium">{u.full_name}</span> },
            { key: "username", header: "Username" },
            { key: "roleNames", header: "Roles" },
            { key: "branchNames", header: "Branches" },
            { key: "last", header: "Last sign-in" },
            { key: "status", header: "Status", render: (u) => <StatusBadge status={u.must_change_password && u.status === "Active" ? "Must change password" : u.status} /> },
          ]}
          fields={[
            { name: "name", label: "Full name", required: true, half: true },
            { name: "username", label: "Username (can't change later)", required: true, half: true },
            { name: "email", label: "Email", type: "email", half: true },
            { name: "phone", label: "Phone", type: "tel", half: true },
            { name: "roles", label: `Roles, comma separated (${roles.data.map((r) => r.name).join(", ")})`, required: true },
            { name: "branches", label: `Branches, comma separated (${branchOpts.map((b) => b.name_en).join(", ")})`, required: true },
            { name: "lang", label: "Language", type: "select", options: ["English", "Khmer"], half: true },
            { name: "password", label: "Temporary password (new users, 10+ characters)", half: true },
            { name: "pin", label: "PIN for shared terminals (4–6 digits, optional)", half: true },
          ]}
          toForm={(u) => ({
            name: u.full_name,
            username: u.username,
            email: u.email ?? "",
            phone: u.phone ?? "",
            roles: u.roles.map((r) => r.name).join(", "),
            branches: u.branches.map((b) => b.name_en).join(", "),
            lang: u.preferred_language === "km" ? "Khmer" : "English",
            password: "",
            pin: "",
          })}
          extraActions={(u) =>
            manage
              ? [
                  { label: "Sessions", icon: MonitorSmartphone, onClick: () => setSessionsFor(u) },
                  { label: "Reset password or PIN", icon: KeyRound, onClick: () => setResetFor(u) },
                  { label: "Unlock", icon: Unlock, hidden: () => u.status !== "Locked", onClick: () => void act(() => api("POST", `/users/${u.id}/unlock`), `${u.full_name} unlocked`, users.reload) },
                  u.status === "Inactive"
                    ? { label: "Activate", icon: Check, onClick: () => void act(() => api("POST", `/users/${u.id}/activate`), `${u.full_name} activated`, users.reload) }
                    : {
                        label: "Deactivate",
                        icon: Ban,
                        destructive: true,
                        hidden: () => u.id === me?.id,
                        onClick: () =>
                          confirmAction({
                            title: `Deactivate ${u.full_name}?`,
                            effect: "They are signed out everywhere and can't sign in. Their history stays.",
                            destructive: true,
                            confirmLabel: "Deactivate",
                            onConfirm: () => void act(() => api("POST", `/users/${u.id}/deactivate`), `${u.full_name} deactivated`, users.reload),
                          }),
                      },
                ]
              : []
          }
        />
      )}
      {tab === "roles" && role && (
        <div className="grid items-start gap-4 lg:grid-cols-[260px_1fr]">
          <Panel title="Roles">
            <ul className="grid gap-1">
              {roles.data.map((r) => (
                <li key={r.id}>
                  <button
                    className={`w-full rounded-md px-2 py-1.5 text-left text-sm ${r.id === role.id ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
                    onClick={() => {
                      setRoleId(r.id)
                      setDraftPerms(null)
                      setDraftLimits(null)
                    }}
                  >
                    {r.name}
                    <span className="block text-xs opacity-75">{r.permissions.length} permissions</span>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
          <div className="grid gap-4">
            {role.code === "SYSADMIN" && <Notice tone="info">System administrator permissions are fixed.</Notice>}
            <Panel
              title={`${role.name} permissions`}
              description={role.description ?? undefined}
              actions={
                can(me, "roles.manage") &&
                draftPerms && (
                  <Button
                    onClick={() =>
                      void act(() => api("PUT", `/roles/${role.id}/permissions`, { body: { permissions: draftPerms } }), "Permissions saved", () => {
                        setDraftPerms(null)
                        roles.reload()
                      })
                    }
                  >
                    Save permissions
                  </Button>
                )
              }
            >
              <div className="grid gap-4 sm:grid-cols-2">
                {modules.map((m) => (
                  <fieldset key={m} className="grid gap-1">
                    <legend className="mb-1 text-sm font-medium capitalize">{m.replaceAll("_", " ")}</legend>
                    {perms.data
                      .filter((p) => p.module === m)
                      .map((p) => (
                        <label key={p.code} className="flex items-start gap-2 text-sm">
                          <Checkbox
                            className="mt-0.5"
                            disabled={!can(me, "roles.manage")}
                            checked={shownPerms.includes(p.code)}
                            onCheckedChange={(c) => setDraftPerms(c ? [...shownPerms, p.code] : shownPerms.filter((x) => x !== p.code))}
                          />
                          <span>
                            {p.description}
                            <span className="block font-mono text-[11px] text-muted-foreground">{p.code}</span>
                          </span>
                        </label>
                      ))}
                  </fieldset>
                ))}
              </div>
            </Panel>
            <Panel
              title="Approval limits"
              description="Above a limit, someone with a higher limit approves on the device. Empty means the role can't approve it."
              actions={
                can(me, "roles.manage") &&
                draftLimits && (
                  <Button
                    onClick={() =>
                      void act(
                        () =>
                          api("PUT", `/roles/${role.id}/limits`, {
                            body: { limits: Object.fromEntries(Object.entries(draftLimits).filter(([, v]) => v !== "").map(([k, v]) => [k, String(v)])) },
                          }),
                        "Limits saved",
                        () => {
                          setDraftLimits(null)
                          roles.reload()
                        }
                      )
                    }
                  >
                    Save limits
                  </Button>
                )
              }
            >
              <div className="grid gap-3 sm:grid-cols-2">
                {[...new Set([...Object.keys(LIMITS), ...Object.keys(role.limits)])].map((k) => (
                  <label key={k} className="grid gap-1 text-sm">
                    {LIMITS[k] ?? k}
                    <Input
                      inputMode="decimal"
                      disabled={!can(me, "roles.manage")}
                      value={shownLimits[k] === undefined ? "" : String(num(shownLimits[k]))}
                      onChange={(e) => setDraftLimits({ ...shownLimits, [k]: e.target.value })}
                    />
                  </label>
                ))}
              </div>
            </Panel>
          </div>
        </div>
      )}
      {tab === "auth" && (
        <DataTable
          rows={authEvents.data.map((e) => ({ ...e, time: when(e.occurred_at), what: EVENTS[e.event] ?? e.event }))}
          exportName="sign-in-history"
          emptyTitle="No sign-in events"
          filters={[{ key: "what", label: "Event" }]}
          columns={[
            { key: "time", header: "Time" },
            { key: "username", header: "Username" },
            { key: "what", header: "Event", render: (e) => <StatusBadge status={e.what} tone={/Fail|Lock/.test(e.event) ? "danger" : "neutral"} /> },
            { key: "ip", header: "IP", render: (e) => e.ip ?? "—" },
            { key: "device", header: "Device", render: (e) => e.device ?? "—" },
          ]}
        />
      )}
      {tab === "approvals" && (
        <DataTable
          rows={approvals.data.map((a) => ({
            id: String(a.id),
            time: when(a.occurred_at),
            action: String(a.after_data?.action ?? ""),
            amount: a.after_data?.amount ? String(a.after_data.amount) : "—",
            approver: String(a.after_data?.approver ?? ""),
            requester: userName(a.actor_user_id),
            reason: a.reason ?? "—",
          }))}
          exportName="approvals"
          emptyTitle={can(me, "audit.view") ? "No approvals recorded" : "You can't view the audit trail"}
          columns={[
            { key: "time", header: "Time" },
            { key: "action", header: "Action" },
            { key: "amount", header: "Amount", align: "right" },
            { key: "requester", header: "Requested by" },
            { key: "approver", header: "Approved by" },
            { key: "reason", header: "Reason" },
          ]}
        />
      )}
      {tab === "review" && (
        <>
          <Notice tone="info">Review who still needs access. Accounts unused for 90 days or more are flagged.</Notice>
          <DataTable
            rows={rows.filter((u) => u.status !== "Inactive").map((u) => ({ ...u, idle: daysSince(u.last_login_at) }))}
            exportName="access-review"
            columns={[
              { key: "full_name", header: "Name" },
              { key: "roleNames", header: "Roles" },
              { key: "branchNames", header: "Branches" },
              { key: "last", header: "Last sign-in" },
              {
                key: "idle",
                header: "Review",
                value: (u) => (u.idle === null || u.idle >= 90 ? "Unused" : "In use"),
                render: (u) => <StatusBadge status={u.idle === null ? "Never signed in" : u.idle >= 90 ? `${u.idle} days idle` : "In use"} tone={u.idle === null || u.idle >= 90 ? "warning" : "success"} />,
              },
            ]}
          />
        </>
      )}
      <RecordDialog
        open={!!resetFor}
        onOpenChange={(o) => !o && setResetFor(null)}
        title={`Reset ${resetFor?.full_name ?? ""}'s credentials`}
        description="They must change the password at their next sign-in. Fill in either or both."
        fields={[
          { name: "password", label: "Temporary password (10+ characters)", validate: (v) => (v && String(v).length < 10 ? "At least 10 characters" : undefined) },
          { name: "pin", label: "New PIN (4–6 digits)", validate: (v) => (v && !/^\d{4,6}$/.test(String(v)) ? "4 to 6 digits" : undefined) },
        ]}
        onSubmit={(v) => {
          if (!v.password && !v.pin) return Promise.reject(new Error("Enter a password, a PIN or both."))
          return save(() =>
            api("POST", `/users/${resetFor!.id}/reset-credentials`, { body: { temporary_password: String(v.password ?? "") || undefined, pin: String(v.pin ?? "") || undefined } })
          ).then(() => toast.success("Credentials reset"))
        }}
      />
      <Dialog open={!!sessionsFor} onOpenChange={(o) => !o && setSessionsFor(null)}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{sessionsFor?.full_name}&apos;s signed-in devices</DialogTitle>
          </DialogHeader>
          <DataTable
            rows={sessions.data.filter((x) => !x.revoked_at)}
            exportName="sessions"
            emptyTitle="No active sessions"
            columns={[
              { key: "created_at", header: "Signed in", render: (x) => when(x.created_at) },
              { key: "last_used_at", header: "Last used", render: (x) => when(x.last_used_at) || "—" },
              { key: "ip", header: "IP", render: (x) => x.ip ?? "—" },
              { key: "user_agent", header: "Device", render: (x) => (x.user_agent ?? "").slice(0, 40) },
            ]}
            rowActions={(x) => [
              {
                label: "Sign out this device",
                icon: LogOut,
                destructive: true,
                onClick: () =>
                  api("DELETE", `/users/sessions/${x.id}`).then(
                    () => {
                      toast.success("Session ended")
                      sessions.reload()
                    },
                    (e) => toast.error(apiMessage(e))
                  ),
              },
            ]}
          />
        </DialogContent>
      </Dialog>
    </Page>
  )
}

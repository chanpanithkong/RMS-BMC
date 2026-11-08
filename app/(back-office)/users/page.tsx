"use client"

import { Ban, KeyRound, LockOpen, ShieldOff, UserCheck } from "lucide-react"
import { toast } from "sonner"
import { CrudTable, newId } from "@/components/rms/crud"
import { DataTable } from "@/components/rms/data-table"
import { confirmAction } from "@/components/rms/dialog-host"
import {
  Page,
  PageHeader,
  PageTabs,
  StatusBadge,
  useTab,
} from "@/components/rms/kit"
import { permissionMatrix, roleCodes, users } from "@/lib/rms/back-office"
import { roleLabels } from "@/lib/rms/nav"
import { useRms } from "@/lib/rms/store"

export default function UsersPage() {
  const { role, userName } = useRms()
  const [tab, setTab] = useTab("users")
  const canManage = role === "SYSADMIN"
  return (
    <Page>
      <PageHeader
        title="User management"
        description="Accounts, roles and access history. You can't change your own roles, permissions or limits."
      />
      <PageTabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "users", label: "Users", count: users.length },
          { value: "roles", label: "Roles & permissions" },
          { value: "sessions", label: "Sessions" },
          { value: "auth", label: "Sign-in history" },
          { value: "approvals", label: "Approvals log" },
          { value: "review", label: "Access review" },
        ]}
      />
      {tab === "users" && (
        <CrudTable
          noun="User"
          seed={users}
          canAdd={canManage}
          canEdit={canManage}
          filters={[
            {
              key: "status",
              label: "Status",
              options: ["Active", "Locked", "Inactive"],
            },
            { key: "roles", label: "Role", options: roleCodes },
          ]}
          columns={[
            {
              key: "name",
              header: "Name",
              render: (u) => <span className="font-medium">{u.name}</span>,
            },
            { key: "username", header: "Username" },
            { key: "email", header: "Email", hidden: true },
            {
              key: "roles",
              header: "Role",
              value: (u) =>
                roleLabels[u.roles as keyof typeof roleLabels] ?? u.roles,
            },
            { key: "branches", header: "Branches" },
            { key: "mfa", header: "MFA", value: (u) => (u.mfa ? "On" : "Off") },
            { key: "last", header: "Last sign-in" },
            {
              key: "status",
              header: "Status",
              render: (u) => <StatusBadge status={u.status} />,
            },
          ]}
          fields={[
            { name: "name", label: "Full name", required: true, half: true },
            {
              name: "username",
              label: "Username",
              required: true,
              half: true,
              validate: (v) =>
                users.some((u) => u.username === v) ? undefined : undefined,
            },
            { name: "email", label: "Email", type: "email", half: true },
            { name: "phone", label: "Phone", type: "tel", half: true },
            {
              name: "roles",
              label: "Role",
              type: "select",
              options: roleCodes,
              required: true,
              half: true,
            },
            {
              name: "branches",
              label: "Branches",
              type: "select",
              options: ["All", "Riverside", "BKK1", "Siem Reap"],
              required: true,
              half: true,
            },
            {
              name: "language",
              label: "Preferred language",
              type: "select",
              options: ["Khmer", "English"],
              half: true,
            },
            {
              name: "employee",
              label: "Linked employee (optional)",
              half: true,
            },
          ]}
          description="A temporary password is issued and must be changed at first sign-in."
          toRow={(v, e) => ({
            id: e?.id ?? newId(),
            name: String(v.name),
            username: String(v.username),
            email: String(v.email ?? ""),
            roles: String(v.roles),
            branches: String(v.branches),
            status: e?.status ?? "Active",
            last: e?.last ?? "Never",
            mfa: e?.mfa ?? false,
          })}
          extraActions={(u, update) =>
            canManage
              ? [
                  {
                    label: "Reset password",
                    icon: KeyRound,
                    onClick: () =>
                      toast.success(`Temporary password issued to ${u.name}`),
                  },
                  {
                    label: "Unlock",
                    icon: LockOpen,
                    hidden: () => u.status !== "Locked",
                    onClick: () => {
                      update({ status: "Active" })
                      toast.success("Account unlocked")
                    },
                  },
                  {
                    label: "Activate",
                    icon: UserCheck,
                    hidden: () => u.status !== "Inactive",
                    onClick: () => update({ status: "Active" }),
                  },
                  {
                    label: "Deactivate",
                    icon: Ban,
                    destructive: true,
                    hidden: () =>
                      u.status === "Inactive" || u.name === userName,
                    onClick: () =>
                      confirmAction({
                        title: `Deactivate ${u.name}?`,
                        effect:
                          "All their sessions are revoked immediately. The account is kept for history.",
                        requireReason: true,
                        destructive: true,
                        confirmLabel: "Deactivate",
                        onConfirm: () => update({ status: "Inactive" }),
                      }),
                  },
                ]
              : []
          }
        />
      )}
      {tab === "roles" && (
        <div className="max-h-[70vh] overflow-auto rounded-xl border bg-card">
          <table className="w-full min-w-max text-xs">
            <thead className="sticky top-0 z-10 bg-muted">
              <tr>
                <th className="sticky left-0 z-20 bg-muted p-2 text-left font-medium">
                  Area
                </th>
                {roleCodes.map((r) => (
                  <th
                    key={r}
                    className="p-2 text-center font-medium"
                    title={roleLabels[r]}
                  >
                    {r}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {permissionMatrix.map(([area, ...cells]) => (
                <tr key={area} className="border-t">
                  <th
                    scope="row"
                    className="sticky left-0 bg-card p-2 text-left font-medium whitespace-nowrap"
                  >
                    {area}
                  </th>
                  {cells.map((c, i) => (
                    <td
                      key={i}
                      className={
                        c === "—"
                          ? "p-2 text-center text-muted-foreground/50"
                          : "p-2 text-center whitespace-nowrap"
                      }
                    >
                      {c}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="p-3 text-xs text-muted-foreground">
            V view · C create · E edit · A approve · X export · K cancel/void ·
            R refund/reverse · M manage · (o) own · (b) branch · (s) station ·
            (l) within limit. Proposed defaults, pending decision D-05.
          </p>
        </div>
      )}
      {tab === "sessions" && (
        <DataTable
          rows={[
            {
              id: "1",
              user: "Lina Chhay",
              device: "POS-1",
              ip: "10.0.1.21",
              started: "08/11 08:02",
              idle: "1 min",
            },
            {
              id: "2",
              user: "Bunna Kim",
              device: "KDS-1",
              ip: "10.0.1.50",
              started: "08/11 09:05",
              idle: "0 min",
            },
            {
              id: "3",
              user: "Dara Pich",
              device: "Chrome on Windows",
              ip: "10.0.1.70",
              started: "08/11 07:58",
              idle: "4 min",
            },
          ]}
          exportName="sessions"
          columns={[
            { key: "user", header: "User" },
            { key: "device", header: "Device" },
            { key: "ip", header: "IP address" },
            { key: "started", header: "Started" },
            { key: "idle", header: "Idle" },
          ]}
          rowActions={(s) => [
            {
              label: "Revoke session",
              icon: ShieldOff,
              destructive: true,
              onClick: () =>
                confirmAction({
                  title: `Revoke ${s.user}'s session?`,
                  effect: "They're signed out on that device.",
                  destructive: true,
                  confirmLabel: "Revoke",
                  onConfirm: () => toast.success("Session revoked"),
                }),
            },
          ]}
        />
      )}
      {tab === "auth" && (
        <DataTable
          rows={[
            {
              id: "1",
              time: "08/11 10:30",
              user: "sokha.heng",
              event: "PIN switch",
              device: "TAB-3",
              ip: "10.0.1.34",
            },
            {
              id: "2",
              time: "08/11 08:02",
              user: "lina.chhay",
              event: "Login",
              device: "POS-1",
              ip: "10.0.1.21",
            },
            {
              id: "3",
              time: "07/11 17:21",
              user: "ratha.seng",
              event: "Lockout",
              device: "KDS-2",
              ip: "10.0.1.51",
            },
            {
              id: "4",
              time: "07/11 17:20",
              user: "ratha.seng",
              event: "Failed login",
              device: "KDS-2",
              ip: "10.0.1.51",
            },
            {
              id: "5",
              time: "07/11 23:15",
              user: "chenda.roeun",
              event: "Logout",
              device: "POS-2",
              ip: "10.0.1.22",
            },
          ]}
          exportName="sign-in-history"
          filters={[{ key: "event", label: "Event" }]}
          columns={[
            { key: "time", header: "Time" },
            { key: "user", header: "User" },
            { key: "event", header: "Event" },
            { key: "device", header: "Device" },
            { key: "ip", header: "IP address" },
          ]}
        />
      )}
      {tab === "approvals" && (
        <DataTable
          rows={[
            {
              id: "1",
              time: "08/11 12:54",
              type: "Discount",
              ref: "B-5512",
              amount: "20%",
              requester: "Lina Chhay",
              approver: "Dara Pich",
              result: "Approved",
            },
            {
              id: "2",
              time: "08/11 11:15",
              type: "Purchase order",
              ref: "PO-1043",
              amount: "$640.00",
              requester: "Malis Som",
              approver: "—",
              result: "Pending",
            },
            {
              id: "3",
              time: "07/11 23:12",
              type: "Variance",
              ref: "CS-0411",
              amount: "−៛100",
              requester: "Chenda Roeun",
              approver: "Dara Pich",
              result: "Approved",
            },
            {
              id: "4",
              time: "07/11 19:02",
              type: "Refund",
              ref: "RF-0086",
              amount: "$21.00",
              requester: "Chenda Roeun",
              approver: "Sopheak Nou",
              result: "Rejected",
            },
          ]}
          exportName="approvals-log"
          filters={[{ key: "type", label: "Type" }]}
          columns={[
            { key: "time", header: "Time" },
            { key: "type", header: "Type" },
            { key: "ref", header: "Reference" },
            { key: "amount", header: "Amount", align: "right" },
            { key: "requester", header: "Requester" },
            { key: "approver", header: "Approver" },
            {
              key: "result",
              header: "Result",
              render: (r) => <StatusBadge status={r.result} />,
            },
          ]}
        />
      )}
      {tab === "review" && (
        <DataTable
          rows={users}
          exportName="access-review"
          columns={[
            { key: "name", header: "User" },
            { key: "roles", header: "Role" },
            { key: "branches", header: "Branches" },
            {
              key: "sensitive",
              header: "Sensitive permissions",
              value: (u) =>
                ["OWNER", "GM", "SYSADMIN"].includes(u.roles)
                  ? "Approvals, settings"
                  : u.roles === "ACCT"
                    ? "Refunds, rates"
                    : "None",
            },
            { key: "last", header: "Last sign-in" },
          ]}
        />
      )}
    </Page>
  )
}

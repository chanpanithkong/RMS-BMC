"use client"

import { KV, LinkButton, Notice, Page, PageHeader, Panel } from "@/components/rms/kit"
import { useSession } from "@/lib/api/session"

export default function ProfilePage() {
  const { me } = useSession()
  if (!me) return null
  return (
    <Page>
      <PageHeader title="My profile" description="Your account, roles and branches." />
      <div className="grid max-w-3xl items-start gap-4 md:grid-cols-2">
        <Panel title="Account">
          <KV
            items={[
              ["Name", me.full_name],
              ["Username", me.username],
              ["Roles", me.roles.map((r) => r.name).join(", ")],
              ["Current branch", me.current_branch.name_en],
              ["Branches", me.branches.map((b) => b.name_en).join(", ")],
              ["Business day", me.business_date],
            ]}
          />
          <div className="mt-3 flex gap-2">
            <LinkButton href="/change-password" variant="outline">
              Change password
            </LinkButton>
          </div>
        </Panel>
        <Panel title="Contact and language">
          <KV
            items={[
              ["Email", me.email ?? "—"],
              ["Preferred language", me.preferred_language === "km" ? "Khmer" : "English"],
            ]}
          />
          <Notice tone="info" className="mt-3">
            Ask an administrator to change your contact details or PIN (Users &amp; roles).
          </Notice>
        </Panel>
      </div>
    </Page>
  )
}

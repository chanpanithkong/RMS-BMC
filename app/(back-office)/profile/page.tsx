"use client"

import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { RecordForm, type FieldValue } from "@/components/rms/crud"
import { KV, LinkButton, Page, PageHeader, Panel } from "@/components/rms/kit"
import { roleLabels } from "@/lib/rms/nav"
import { useRms } from "@/lib/rms/store"
import * as React from "react"

export default function ProfilePage() {
  const { userName, role, branch } = useRms()
  const [v, setV] = React.useState<Record<string, FieldValue>>({
    phone: "012 100 200",
    email: "dara@example.com",
    language: "English",
  })
  return (
    <Page>
      <PageHeader
        title="My profile"
        description="Your contact details and sign-in options."
      />
      <div className="grid max-w-3xl items-start gap-4 md:grid-cols-2">
        <Panel title="Account">
          <KV
            items={[
              ["Name", userName],
              ["Role", roleLabels[role]],
              ["Branch", branch],
              ["Two-factor", "Enabled"],
            ]}
          />
          <div className="mt-3 flex gap-2">
            <LinkButton href="/change-password" variant="outline">
              Change password
            </LinkButton>
            <LinkButton href="/lock" variant="outline">
              Change PIN
            </LinkButton>
          </div>
        </Panel>
        <Panel title="Contact and language">
          <RecordForm
            errors={{}}
            values={v}
            setValue={(k, x) => setV((s) => ({ ...s, [k]: x }))}
            fields={[
              { name: "phone", label: "Phone", type: "tel" },
              { name: "email", label: "Email", type: "email" },
              {
                name: "language",
                label: "Preferred language",
                type: "select",
                options: ["Khmer", "English"],
              },
            ]}
          />
          <Button
            className="mt-3"
            onClick={() => toast.success("Profile saved")}
          >
            Save
          </Button>
        </Panel>
      </div>
    </Page>
  )
}

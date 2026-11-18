"use client"

import * as React from "react"
import { ShieldCheck } from "lucide-react"
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
import { Textarea } from "@/components/ui/textarea"
import { FormRow, KV, SimpleSelect, opts } from "@/components/rms/kit"

interface ConfirmOptions {
  title: string
  effect: string
  confirmLabel?: string
  destructive?: boolean
  reasons?: string[]
  requireReason?: boolean
  onConfirm: (reason: string) => void
}
interface ApprovalOptions {
  action: string
  amount?: string
  limit?: string
  reason?: string
  onApproved: (approver: string) => void
  onDeclined?: () => void
  /** API mode: check the approver with the backend (POST /approvals). Throw to show the error and keep the dialog open. */
  verify?: (approverUsername: string, secret: string) => Promise<void>
}

type Req =
  | { kind: "confirm"; o: ConfirmOptions }
  | { kind: "approval"; o: ApprovalOptions }
  | null
let push: (r: Req) => void = () => {}

/** ConfirmDialog (SRS §15.3): shows the effect and asks for a reason where one applies. */
export const confirmAction = (o: ConfirmOptions) => push({ kind: "confirm", o })
/** ApprovalDialog (SRS §15.3): manager PIN on the same device, or a remote request. */
export const requestApproval = (o: ApprovalOptions) =>
  push({ kind: "approval", o })

export function DialogHost() {
  const [req, setReq] = React.useState<Req>(null)
  const [reason, setReason] = React.useState("")
  const [pin, setPin] = React.useState("")
  const [approver, setApprover] = React.useState("")
  const [checking, setChecking] = React.useState(false)
  const [error, setError] = React.useState("")
  React.useEffect(() => {
    push = (r) => {
      setReason("")
      setPin("")
      setApprover("")
      setChecking(false)
      setError("")
      setReq(r)
    }
    return () => {
      push = () => {}
    }
  }, [])
  const close = () => setReq(null)

  if (req?.kind === "confirm") {
    const { o } = req
    const needs = o.requireReason || !!o.reasons
    return (
      <Dialog open onOpenChange={(v) => !v && close()}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{o.title}</DialogTitle>
            <DialogDescription>{o.effect}</DialogDescription>
          </DialogHeader>
          {needs && (
            <FormRow label="Reason" required error={error}>
              {o.reasons ? (
                <SimpleSelect
                  aria-label="Reason"
                  value={reason}
                  onChange={setReason}
                  options={opts(...o.reasons)}
                  placeholder="Select a reason…"
                  invalid={!!error}
                />
              ) : (
                <Textarea
                  aria-label="Reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  aria-invalid={!!error || undefined}
                />
              )}
            </FormRow>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={close}>
              Keep as is
            </Button>
            <Button
              variant={o.destructive ? "destructive" : "default"}
              onClick={() => {
                if (needs && !reason.trim())
                  return setError("Choose a reason to continue")
                close()
                o.onConfirm(reason)
              }}
            >
              {o.confirmLabel ?? "Confirm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
  }

  if (req?.kind === "approval") {
    const { o } = req
    const rows: [string, React.ReactNode][] = [["Action", o.action]]
    if (o.amount) rows.push(["Amount", o.amount])
    if (o.limit) rows.push(["Your limit", o.limit])
    if (o.reason) rows.push(["Reason", o.reason])
    const approve = async (e: React.FormEvent) => {
      e.preventDefault()
      if (o.verify) {
        if (!approver.trim() || !pin) return setError("Enter the approver's username and PIN or password")
        setChecking(true)
        try {
          await o.verify(approver.trim(), pin)
        } catch (err) {
          setChecking(false)
          return setError(err instanceof Error ? err.message : "Approval was not accepted")
        }
        close()
        return o.onApproved(approver.trim())
      }
      if (!/^\d{4,6}$/.test(pin))
        return setError("Enter the approver's 4–6 digit PIN")
      close()
      o.onApproved("Dara Pich")
    }
    return (
      <Dialog
        open
        onOpenChange={(v) => {
          if (!v) {
            close()
            o.onDeclined?.()
          }
        }}
      >
        <DialogContent className="sm:max-w-sm">
          <form onSubmit={approve} className="grid gap-4">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <ShieldCheck className="size-4 text-primary" />
                Manager approval needed
              </DialogTitle>
              <DialogDescription>
                The approver must be a different user from the requester.
              </DialogDescription>
            </DialogHeader>
            <KV items={rows} />
            {o.verify && (
              <FormRow label="Approver username" required htmlFor="approver-user">
                <Input
                  id="approver-user"
                  autoFocus
                  autoComplete="off"
                  value={approver}
                  onChange={(e) => setApprover(e.target.value)}
                />
              </FormRow>
            )}
            <FormRow
              label={o.verify ? "Approver PIN or password" : "Approver PIN"}
              required
              error={error}
              htmlFor="approver-pin"
            >
              <Input
                id="approver-pin"
                type="password"
                inputMode={o.verify ? undefined : "numeric"}
                autoFocus={!o.verify}
                autoComplete="off"
                value={pin}
                onChange={(e) => setPin(e.target.value)}
                aria-invalid={!!error || undefined}
              />
            </FormRow>
            <DialogFooter>
              {!o.verify && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    close()
                    toast.info("Approval request sent to managers")
                    o.onDeclined?.()
                  }}
                >
                  Send remote request
                </Button>
              )}
              <Button type="submit" disabled={checking}>
                {checking ? "Checking…" : "Approve"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    )
  }
  return null
}

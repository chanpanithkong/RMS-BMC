import { AuthGate } from "@/components/rms/auth-gate"

/** The rider app needs a signed-in rider; the backend only returns deliveries assigned to them. */
export default function RiderLayout({ children }: { children: React.ReactNode }) {
  return <AuthGate>{children}</AuthGate>
}

import { redirect } from "next/navigation"

/** Old tracking address; tracking links now use /track/<token>. */
export default async function OldTrackingPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
  redirect(`/track/${id}`)
}

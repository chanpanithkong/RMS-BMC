import { Suspense } from "react"
import { LoginForm } from "@/components/login-form"

export default function Page() {
  // LoginForm reads ?next= with useSearchParams, so it renders on the client inside a Suspense boundary.
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  )
}

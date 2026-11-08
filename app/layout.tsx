import type { Metadata } from "next"
import { Geist, Geist_Mono, Noto_Sans_Khmer } from "next/font/google"
import { TooltipProvider } from "@/components/ui/tooltip"
import { Toaster } from "@/components/ui/sonner"
import { ThemeProvider } from "@/components/theme-provider"
import { DialogHost } from "@/components/rms/dialog-host"
import { cn } from "@/lib/utils"
import "./globals.css"

const geist = Geist({ subsets: ["latin"], variable: "--font-latin" })
const khmer = Noto_Sans_Khmer({ subsets: ["khmer"], variable: "--font-khmer" })
const fontMono = Geist_Mono({ subsets: ["latin"], variable: "--font-mono" })

export const metadata: Metadata = {
  title: { default: "Restaurant Management System", template: "%s · RMS" },
  description:
    "Point of sale, kitchen, inventory and back office for restaurants.",
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(
        "antialiased",
        fontMono.variable,
        geist.variable,
        khmer.variable
      )}
      style={
        {
          "--font-sans": "var(--font-latin), var(--font-khmer), sans-serif",
        } as React.CSSProperties
      }
    >
      <body className="font-sans">
        <TooltipProvider>
          <ThemeProvider>
            {children}
            <DialogHost />
            <Toaster richColors position="top-right" />
          </ThemeProvider>
        </TooltipProvider>
      </body>
    </html>
  )
}

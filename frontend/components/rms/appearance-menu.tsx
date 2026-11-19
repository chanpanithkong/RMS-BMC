"use client"

import * as React from "react"
import { Check, Monitor, Moon, Palette, RotateCcw, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ACCENTS, TEXT_SIZES, appearance } from "@/lib/rms/appearance"
import { cn } from "@/lib/utils"

const THEMES = [
  { id: "light", label: "Light", icon: Sun },
  { id: "dark", label: "Dark", icon: Moon },
  { id: "system", label: "System", icon: Monitor },
] as const
const SIZE_CLASS = { sm: "text-xs", md: "text-sm", lg: "text-lg", xl: "text-xl" } as const

const noop = () => () => {}
/** True only after hydration, so theme-dependent UI doesn't mismatch the server render. */
const useMounted = () => React.useSyncExternalStore(noop, () => true, () => false)

export function AppearanceMenu() {
  const { theme, setTheme } = useTheme()
  const a = React.useSyncExternalStore(appearance.subscribe, appearance.get, appearance.server)
  const mounted = useMounted()
  const active = mounted ? (theme ?? "system") : undefined
  const swatch = ACCENTS.find((x) => x.id === a.accent)?.swatch

  return (
    <Popover>
      <PopoverTrigger render={<Button variant="ghost" size="icon" className="relative" aria-label="Appearance" />}>
        <Palette />
        <span
          aria-hidden
          className="absolute right-1 bottom-1 size-2 rounded-full ring-2 ring-background"
          style={{ background: swatch }}
        />
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="font-semibold">Appearance</p>
            <p className="text-xs text-muted-foreground">Saved in this browser</p>
          </div>
          <Button
            variant="ghost"
            size="xs"
            onClick={() => {
              setTheme("system")
              appearance.reset()
            }}
          >
            <RotateCcw />
            Reset
          </Button>
        </div>

        <p className="mt-4 mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">Theme</p>
        <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-2">
          {THEMES.map((t) => {
            const on = active === t.id
            return (
              <button
                key={t.id}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => setTheme(t.id)}
                className={cn(
                  "flex flex-col items-center gap-1 rounded-lg border px-2 py-2.5 text-sm transition-colors",
                  on ? "border-primary bg-primary/10 font-medium text-foreground ring-1 ring-primary" : "text-muted-foreground hover:bg-muted"
                )}
              >
                <t.icon className="size-4" />
                {t.label}
              </button>
            )
          })}
        </div>

        <p className="mt-4 mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">Accent colour</p>
        <div role="radiogroup" aria-label="Accent colour" className="flex flex-wrap gap-2.5">
          {ACCENTS.map((c) => {
            const on = a.accent === c.id
            return (
              <button
                key={c.id}
                type="button"
                role="radio"
                aria-checked={on}
                aria-label={c.label}
                title={c.label}
                onClick={() => appearance.set({ accent: c.id })}
                className={cn(
                  "flex size-8 items-center justify-center rounded-full text-white transition-transform hover:scale-105",
                  on && "ring-2 ring-foreground/70 ring-offset-2 ring-offset-popover"
                )}
                style={{ background: c.swatch }}
              >
                {on && <Check className="size-4" />}
              </button>
            )
          })}
        </div>

        <p className="mt-4 mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">Text size</p>
        <div role="radiogroup" aria-label="Text size" className="grid grid-cols-4 gap-1 rounded-lg bg-muted p-1">
          {TEXT_SIZES.map((s) => {
            const on = a.text === s.id
            return (
              <button
                key={s.id}
                type="button"
                role="radio"
                aria-checked={on}
                aria-label={s.label}
                title={s.label}
                onClick={() => appearance.set({ text: s.id })}
                className={cn(
                  "flex h-9 items-end justify-center rounded-md pb-1.5 font-semibold leading-none transition-colors",
                  SIZE_CLASS[s.id],
                  on ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
              >
                A
              </button>
            )
          })}
        </div>
        <p className="mt-1.5 text-center text-xs text-muted-foreground">{TEXT_SIZES.find((s) => s.id === a.text)?.label}</p>
      </PopoverContent>
    </Popover>
  )
}

/**
 * Per-browser appearance: accent colour and text size (the theme itself is handled by next-themes).
 * Applied as data attributes on <html>; globals.css maps them to colour tokens and the root font size.
 * A tiny inline script in the root layout applies the saved choice before the first paint (no flash).
 */
export const ACCENTS = [
  { id: "terracotta", label: "Terracotta", swatch: "oklch(0.52 0.165 38)" },
  { id: "teal", label: "Teal", swatch: "oklch(0.5 0.09 185)" },
  { id: "blue", label: "Blue", swatch: "oklch(0.52 0.17 255)" },
  { id: "violet", label: "Violet", swatch: "oklch(0.52 0.19 295)" },
  { id: "rose", label: "Rose", swatch: "oklch(0.55 0.19 10)" },
  { id: "green", label: "Green", swatch: "oklch(0.5 0.13 150)" },
] as const
export const TEXT_SIZES = [
  { id: "sm", label: "Small" },
  { id: "md", label: "Default" },
  { id: "lg", label: "Large" },
  { id: "xl", label: "Extra large" },
] as const
export type Accent = (typeof ACCENTS)[number]["id"]
export type TextSize = (typeof TEXT_SIZES)[number]["id"]
export interface Appearance {
  accent: Accent
  text: TextSize
}

export const DEFAULT_APPEARANCE: Appearance = { accent: "terracotta", text: "md" }
const KEY = "rms.appearance"
const listeners = new Set<() => void>()
let current: Appearance | null = null

function read(): Appearance {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "null")
    return {
      accent: ACCENTS.some((a) => a.id === v?.accent) ? v.accent : DEFAULT_APPEARANCE.accent,
      text: TEXT_SIZES.some((t) => t.id === v?.text) ? v.text : DEFAULT_APPEARANCE.text,
    }
  } catch {
    return DEFAULT_APPEARANCE
  }
}

function apply(a: Appearance) {
  const el = document.documentElement
  el.dataset.accent = a.accent
  el.dataset.text = a.text
}

export const appearance = {
  get: (): Appearance => (current ??= read()),
  server: (): Appearance => DEFAULT_APPEARANCE,
  subscribe(fn: () => void) {
    listeners.add(fn)
    return () => listeners.delete(fn)
  },
  set(patch: Partial<Appearance>) {
    current = { ...appearance.get(), ...patch }
    try {
      localStorage.setItem(KEY, JSON.stringify(current))
    } catch {
      // private mode or blocked storage: still applies for this page view
    }
    apply(current)
    listeners.forEach((fn) => fn())
  },
  reset() {
    try {
      localStorage.removeItem(KEY)
    } catch {}
    current = DEFAULT_APPEARANCE
    apply(current)
    listeners.forEach((fn) => fn())
  },
}

/** Runs before hydration (inline in the root layout). Keep it dependency-free. */
export const APPEARANCE_BOOT = `try{var a=JSON.parse(localStorage.getItem("${KEY}")||"null")||{},d=document.documentElement;d.dataset.accent=a.accent||"terracotta";d.dataset.text=a.text||"md"}catch(e){}`

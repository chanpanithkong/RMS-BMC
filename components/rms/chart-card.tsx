"use client"

import * as React from "react"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from "recharts"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"

export interface Series {
  key: string
  label: string
}
type Datum = Record<string, string | number>

/** Line or bar chart with a table alternative, as SRS §15.3 requires for every chart. */
export function ChartCard({
  title,
  description,
  data,
  xKey,
  series,
  type = "bar",
  horizontal,
  format = (v: number) => v.toLocaleString("en-US"),
  height = 240,
}: {
  title: string
  description?: string
  data: Datum[]
  xKey: string
  series: Series[]
  type?: "bar" | "line" | "area"
  horizontal?: boolean
  format?: (v: number) => string
  height?: number
}) {
  const [asTable, setAsTable] = React.useState(false)
  const config = Object.fromEntries(
    series.map((s, i) => [
      s.key,
      { label: s.label, color: `var(--chart-${i + 1})` },
    ])
  ) as ChartConfig
  const legend =
    series.length > 1 ? <ChartLegend content={<ChartLegendContent />} /> : null
  const tooltip = (
    <ChartTooltip
      content={
        <ChartTooltipContent
          formatter={(v, name) => (
            <div className="flex w-full justify-between gap-4">
              <span className="text-muted-foreground">
                {config[String(name)]?.label}
              </span>
              <span className="tabular font-medium">{format(Number(v))}</span>
            </div>
          )}
        />
      }
    />
  )
  const axisY = (
    <YAxis
      tickLine={false}
      axisLine={false}
      width={52}
      tickFormatter={(v) => format(Number(v))}
      fontSize={11}
    />
  )
  const axisX = (
    <XAxis
      dataKey={xKey}
      tickLine={false}
      axisLine={false}
      tickMargin={8}
      minTickGap={16}
      fontSize={11}
    />
  )
  const grid = <CartesianGrid vertical={false} strokeOpacity={0.5} />

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2">
        <div>
          <CardTitle>{title}</CardTitle>
          {description && (
            <CardDescription className="mt-0.5">{description}</CardDescription>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={asTable}
          onClick={() => setAsTable(!asTable)}
        >
          {asTable ? "Chart" : "Table"}
        </Button>
      </CardHeader>
      <CardContent>
        {asTable ? (
          <div
            className="overflow-auto rounded-lg border"
            style={{ maxHeight: height }}
          >
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted">
                <tr>
                  <th className="p-2 text-left font-medium">
                    {xKey === "label" ? "Period" : xKey}
                  </th>
                  {series.map((s) => (
                    <th key={s.key} className="p-2 text-right font-medium">
                      {s.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.map((d, i) => (
                  <tr key={i} className="border-t">
                    <td className="p-2">{d[xKey]}</td>
                    {series.map((s) => (
                      <td key={s.key} className="tabular p-2 text-right">
                        {format(Number(d[s.key]))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : horizontal ? (
          <ChartContainer config={config} className="w-full" style={{ height }}>
            <BarChart
              data={data}
              layout="vertical"
              margin={{ left: 8, right: 12 }}
              barCategoryGap={4}
            >
              <CartesianGrid horizontal={false} strokeOpacity={0.5} />
              <XAxis
                type="number"
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => format(Number(v))}
                fontSize={11}
              />
              <YAxis
                type="category"
                dataKey={xKey}
                tickLine={false}
                axisLine={false}
                width={118}
                fontSize={11}
                interval={0}
              />
              {tooltip}
              {series.map((s) => (
                <Bar
                  key={s.key}
                  dataKey={s.key}
                  fill={`var(--color-${s.key})`}
                  radius={[0, 4, 4, 0]}
                  maxBarSize={14}
                />
              ))}
            </BarChart>
          </ChartContainer>
        ) : (
          <ChartContainer config={config} className="w-full" style={{ height }}>
            {type === "bar" ? (
              <BarChart data={data} barGap={2}>
                {grid}
                {axisX}
                {axisY}
                {tooltip}
                {legend}
                {series.map((s) => (
                  <Bar
                    key={s.key}
                    dataKey={s.key}
                    fill={`var(--color-${s.key})`}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={22}
                  />
                ))}
              </BarChart>
            ) : type === "area" ? (
              <AreaChart data={data}>
                {grid}
                {axisX}
                {axisY}
                {tooltip}
                {legend}
                {series.map((s) => (
                  <Area
                    key={s.key}
                    dataKey={s.key}
                    type="monotone"
                    stroke={`var(--color-${s.key})`}
                    strokeWidth={2}
                    fill={`var(--color-${s.key})`}
                    fillOpacity={0.12}
                  />
                ))}
              </AreaChart>
            ) : (
              <LineChart data={data}>
                {grid}
                {axisX}
                {axisY}
                {tooltip}
                {legend}
                {series.map((s) => (
                  <Line
                    key={s.key}
                    dataKey={s.key}
                    type="monotone"
                    stroke={`var(--color-${s.key})`}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4 }}
                  />
                ))}
              </LineChart>
            )}
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}

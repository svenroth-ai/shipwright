# shadcn/ui Block Patterns

> Official shadcn/ui blocks as implementation reference.
> Source: github.com/shadcn-ui/ui/apps/v4/registry/bases/base/blocks/
> Preview: ui.shadcn.com/blocks
> Upstream commit: 720ccca65343
> Last synced: 2026-04-05

**Usage:** Read the Index first. Load ONLY the section(s) matching your current implementation need.

---

## Index

| Section | Pattern | When to use |
|---------|---------|-------------|
| A | Dashboard Layout | Full-page dashboard with sidebar, stats, chart, table |
| B | Auth / Login | Login, signup, email-only auth pages |
| C1 | Cards: Stat/Metric | KPI cards with value + trend + badge |
| C2 | Cards: Chart | Cards with embedded charts (area, bar, pie) |
| C3 | Cards: List/Table | Cards containing data tables or transaction lists |
| C4 | Cards: Form | Cards wrapping form inputs |
| C5 | Cards: Settings | Cards with toggles, checkboxes, notification preferences |
| C6 | Cards: Empty State | Cards shown when no data exists |
| C7 | Cards: Progress | Cards with progress indicators or pie charts |
| C8 | Cards: Profile | Cards with avatar, bio, form fields |
| D | Layout Patterns | Common Tailwind grid/flex patterns |

---

## Section A — Dashboard Layout

Official block: `dashboard-01`

```tsx
// Page structure: Sidebar + Inset + Header + Content
<SidebarProvider style={{ "--sidebar-width": "calc(var(--spacing) * 72)" }}>
  <AppSidebar variant="inset" />
  <SidebarInset>
    <SiteHeader />
    <div className="flex flex-1 flex-col">
      <div className="@container/main flex flex-1 flex-col gap-2">
        <div className="flex flex-col gap-4 py-4 md:gap-6 md:py-6">
          <SectionCards />          {/* Stats grid */}
          <div className="px-4 lg:px-6">
            <ChartAreaInteractive /> {/* Chart */}
          </div>
          <DataTable data={data} /> {/* Table */}
        </div>
      </div>
    </div>
  </SidebarInset>
</SidebarProvider>
```

Key patterns:
- `@container/main` for container queries
- `gap-4 py-4 md:gap-6 md:py-6` for content spacing
- `px-4 lg:px-6` for horizontal page padding

---

## Section B — Auth / Login

Official blocks: `login-01` through `login-05`

| Variant | Layout | Use when |
|---------|--------|----------|
| `login-01` | Centered form, full height | Simple, minimal auth |
| `login-02` | Two columns: form + cover image | Marketing-oriented login |
| `login-03` | Centered form, muted background | Branded, professional |
| `login-04` | Form + image in one card | Compact, visual |
| `login-05` | Email-only, centered | Magic link / passwordless |

Common login form structure:
```tsx
<Card>
  <CardHeader>
    <CardTitle>Login</CardTitle>
    <CardDescription>Enter your email to sign in</CardDescription>
  </CardHeader>
  <CardContent>
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="email">Email</FieldLabel>
        <Input id="email" type="email" placeholder="m@example.com" />
      </Field>
      <Field>
        <FieldLabel htmlFor="password">Password</FieldLabel>
        <Input id="password" type="password" />
      </Field>
    </FieldGroup>
  </CardContent>
  <CardFooter className="flex-col gap-2">
    <Button className="w-full">Sign in</Button>
    <Separator />
    <Button variant="outline" className="w-full">Sign in with Google</Button>
  </CardFooter>
</Card>
```

---

## Section C1 — Cards: Stat/Metric

Official block: `dashboard-01/section-cards`

```tsx
// Stats grid: responsive 1 → 2 → 4 columns
<div className="grid grid-cols-1 gap-4 px-4 lg:px-6 @xl/main:grid-cols-2 @5xl/main:grid-cols-4">
  <Card className="@container/card">
    <CardHeader>
      <CardDescription>Total Revenue</CardDescription>
      <CardTitle className="text-2xl font-semibold tabular-nums @[250px]/card:text-3xl">
        $1,250.00
      </CardTitle>
      <CardAction>
        <Badge variant="outline">
          <TrendingUpIcon data-icon="inline-start" />
          +12.5%
        </Badge>
      </CardAction>
    </CardHeader>
    <CardFooter className="flex-col items-start gap-1.5 text-sm">
      <div className="line-clamp-1 flex gap-2 font-medium">
        Trending up this month <TrendingUpIcon className="size-4" />
      </div>
      <div className="text-muted-foreground">Visitors for the last 6 months</div>
    </CardFooter>
  </Card>
</div>
```

Key patterns:
- `@container/card` for container query on card
- `tabular-nums` for aligned numeric values
- `CardAction` with `Badge variant="outline"` for trend indicator
- `CardFooter` with `text-sm` + `text-muted-foreground` for secondary info

---

## Section C2 — Cards: Chart

Official block: `preview/analytics-card`

```tsx
<Card className="mx-auto w-full max-w-sm" size="sm">
  <CardHeader>
    <CardTitle>Analytics</CardTitle>
    <CardDescription>
      418.2K Visitors <Badge>+10%</Badge>
    </CardDescription>
    <CardAction>
      <Button variant="outline" size="sm">View Analytics</Button>
    </CardAction>
  </CardHeader>
  <ChartContainer config={chartConfig} className="aspect-[1/0.35]">
    <AreaChart data={chartData} margin={{ left: 0, right: 0 }}>
      <ChartTooltip cursor={false}
        content={<ChartTooltipContent indicator="line" hideLabel />} />
      <Area dataKey="visitors" type="linear"
        fill="var(--color-visitors)" fillOpacity={0.4}
        stroke="var(--color-visitors)" />
    </AreaChart>
  </ChartContainer>
</Card>
```

Key patterns:
- `Card size="sm"` for compact chart cards
- `ChartContainer` wraps Recharts, uses `ChartConfig` for theming
- `aspect-[1/0.35]` for chart aspect ratio
- Colors via CSS variables: `var(--color-visitors)`, `var(--chart-1)`

---

## Section C3 — Cards: List/Table

Official block: `preview-02/recent-transactions`

```tsx
<Card>
  <CardHeader>
    <CardTitle>Recent Transactions</CardTitle>
    <CardDescription>Your latest account activity.</CardDescription>
    <CardAction>
      <Button variant="outline" size="sm">View All</Button>
    </CardAction>
  </CardHeader>
  <CardContent>
    <Table>
      <TableBody>
        <TableRow>
          <TableCell className="w-10">
            <div className="flex size-10 items-center justify-center rounded-lg bg-muted">
              <CoffeeIcon className="size-4 shrink-0" />
            </div>
          </TableCell>
          <TableCell>
            <div className="flex flex-col">
              <span className="font-medium">Blue Bottle Coffee</span>
              <span className="text-sm text-muted-foreground">Food & Drink</span>
            </div>
          </TableCell>
          <TableCell className="text-sm text-muted-foreground">Today, 10:24 AM</TableCell>
          <TableCell className="text-right">
            <span className="text-sm font-semibold tabular-nums">-$6.50</span>
          </TableCell>
          <TableCell className="w-8">
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" />}>
                <MoreHorizontalIcon />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem>View details</DropdownMenuItem>
                <DropdownMenuItem>Categorize</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>
  </CardContent>
</Card>
```

Key patterns:
- `CardAction` with "View All" button
- Icon in `size-10 rounded-lg bg-muted` container
- Two-line cell: `font-medium` name + `text-sm text-muted-foreground` subtitle
- `tabular-nums` for monetary values
- Row-level `DropdownMenu` for actions

---

## Section C4 — Cards: Form

Official block: `preview/shipping-address`

```tsx
<Card>
  <CardHeader>
    <CardTitle>Shipping Address</CardTitle>
    <CardDescription>Where should we deliver?</CardDescription>
  </CardHeader>
  <CardContent>
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="street">Street address</FieldLabel>
        <Input id="street" placeholder="123 Main Street" />
      </Field>
      <FieldGroup className="grid grid-cols-2">
        <Field>
          <FieldLabel htmlFor="city">City</FieldLabel>
          <Input id="city" placeholder="San Francisco" />
        </Field>
        <Field>
          <FieldLabel htmlFor="state">State</FieldLabel>
          <Select>
            <SelectTrigger id="state" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="CA">California</SelectItem>
                <SelectItem value="NY">New York</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </Field>
      </FieldGroup>
      <Field orientation="horizontal">
        <Checkbox id="save" defaultChecked />
        <FieldLabel htmlFor="save" className="font-normal">Save as default</FieldLabel>
      </Field>
    </FieldGroup>
  </CardContent>
  <CardFooter>
    <Button variant="outline" size="sm">Cancel</Button>
    <Button size="sm" className="ml-auto">Save</Button>
  </CardFooter>
</Card>
```

Key patterns:
- `FieldGroup` nests: outer stack + inner `grid grid-cols-2` for side-by-side
- `SelectItem` inside `SelectGroup` (mandatory)
- `Field orientation="horizontal"` for checkboxes
- `CardFooter` with `ml-auto` to push primary action right

---

## Section C5 — Cards: Settings

Official block: `preview-02/notification-settings`

```tsx
<Card>
  <CardHeader>
    <CardTitle>Notifications</CardTitle>
    <CardDescription>Manage your notification preferences.</CardDescription>
  </CardHeader>
  <CardContent>
    <FieldGroup>
      <Field orientation="horizontal">
        <Checkbox id="transactions" defaultChecked />
        <FieldContent>
          <FieldLabel htmlFor="transactions">Transaction alerts</FieldLabel>
          <FieldDescription>Deposits, withdrawals, and transfers.</FieldDescription>
        </FieldContent>
      </Field>
      <Field orientation="horizontal">
        <Checkbox id="security" defaultChecked />
        <FieldContent>
          <FieldLabel htmlFor="security">Security alerts</FieldLabel>
          <FieldDescription>Login attempts and account changes.</FieldDescription>
        </FieldContent>
      </Field>
    </FieldGroup>
  </CardContent>
  <CardFooter>
    <Button size="sm" className="ml-auto">Save preferences</Button>
  </CardFooter>
</Card>
```

Key patterns:
- `Field orientation="horizontal"` with `Checkbox` + `FieldContent` (label + description)
- Use `Switch` instead of `Checkbox` for on/off toggles in settings pages
- `FieldContent` wraps `FieldLabel` + `FieldDescription` for two-line layout

---

## Section C6 — Cards: Empty State

Official block: `preview/no-team-members`

```tsx
<Card>
  <CardContent>
    <Empty className="h-56 border">
      <EmptyHeader>
        <EmptyMedia>
          <AvatarGroup className="grayscale">
            <Avatar size="lg">
              <AvatarImage src="..." alt="@user" />
              <AvatarFallback>CN</AvatarFallback>
            </Avatar>
          </AvatarGroup>
        </EmptyMedia>
        <EmptyTitle>No team members</EmptyTitle>
        <EmptyDescription>
          Invite team members to start collaborating.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        <Button size="sm">Invite members</Button>
      </EmptyContent>
    </Empty>
  </CardContent>
</Card>
```

Key patterns:
- `Empty` inside `Card > CardContent`
- `EmptyMedia` for visual (icon, avatar group, illustration)
- `EmptyContent` for CTA button
- Fixed height: `h-56` for consistent card sizing

---

## Section C7 — Cards: Progress

Official block: `preview-02/savings-progress`

```tsx
<Card>
  <CardContent>
    <ChartContainer config={chartConfig} className="mx-auto aspect-square max-h-[220px]">
      <PieChart>
        <ChartTooltip cursor={false} content={<ChartTooltipContent hideLabel />} />
        <Pie data={chartData} dataKey="value" nameKey="name"
          innerRadius={60} strokeWidth={5}>
          <Label content={({ viewBox }) => (
            <text x={viewBox.cx} y={viewBox.cy} textAnchor="middle">
              <tspan className="fill-foreground text-3xl font-bold">$24,000</tspan>
              <tspan x={viewBox.cx} dy="1.5rem" className="fill-muted-foreground">
                of $30,000
              </tspan>
            </text>
          )} />
        </Pie>
      </PieChart>
    </ChartContainer>
    <Separator />
    <div className="flex justify-between text-sm">
      <span className="text-muted-foreground">Target: $30,000</span>
      <span className="font-medium">80% complete</span>
    </div>
  </CardContent>
</Card>
```

Key patterns:
- Donut chart: `PieChart` with `innerRadius`
- Center label via Recharts `Label` with custom render
- `Separator` between chart and summary
- Summary row: `flex justify-between text-sm`

---

## Section C8 — Cards: Profile

Official block: `preview/github-profile`

```tsx
<Card className="mx-auto w-full max-w-md">
  <CardHeader>
    <CardTitle>Profile</CardTitle>
    <CardDescription>Manage your profile information.</CardDescription>
  </CardHeader>
  <CardContent>
    <form id="profile">
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="name">Name</FieldLabel>
          <Input id="name" placeholder="shadcn" />
          <FieldDescription>Your name as it appears on your profile.</FieldDescription>
        </Field>
        <Field>
          <FieldLabel htmlFor="bio">Bio</FieldLabel>
          <Textarea id="bio" placeholder="Tell us about yourself" />
        </Field>
        <Field>
          <FieldLabel htmlFor="visibility">Visibility</FieldLabel>
          <NativeSelect id="visibility">
            <NativeSelectOption value="public">Public</NativeSelectOption>
            <NativeSelectOption value="private">Private</NativeSelectOption>
          </NativeSelect>
        </Field>
      </FieldGroup>
    </form>
  </CardContent>
  <CardFooter>
    <Button form="profile" type="submit" size="sm" className="ml-auto">
      Update profile
    </Button>
  </CardFooter>
</Card>
```

Key patterns:
- `max-w-md` for narrow profile cards
- `FieldDescription` for helper text under inputs
- `Textarea` for multi-line input
- `NativeSelect` for simple dropdowns (no JS)
- `form="profile"` on submit button to connect to form outside CardFooter

---

## Section D — Layout Patterns (Tailwind)

### Stats Grid (responsive)
```
grid grid-cols-1 gap-4 @xl:grid-cols-2 @5xl:grid-cols-4
```

### Page Content Stack
```
flex flex-1 flex-col gap-4 py-4 md:gap-6 md:py-6
```

### Card Grid
```
grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3
```

### Page Horizontal Padding
```
px-4 lg:px-6
```

### Sidebar Layout
```
SidebarProvider > AppSidebar + SidebarInset > SiteHeader + content
```

### Centered Card (Auth/Settings)
```
flex min-h-svh items-center justify-center p-4
```

### Max-Width Container
```
mx-auto max-w-7xl px-6
```

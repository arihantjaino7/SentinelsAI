# 60 — The diff preview UI

> **Status:** done. `FixPlanPanel.tsx` shows a "Check for automatic fix →"
> button on every fixable finding; clicking it fetches, previews, and can
> save a real diff from `backend/remediation/`.

## What we built

A new component, `components/fixes/FixPlanPanel.tsx`, rendered above the
existing AI fix panel on the report page. It has its own button because
checking for a fix means Sentinels re-reads a file from GitHub right that
second — doing that automatically for every finding on the page the moment
it loads would burn through GitHub's rate limit before anyone looked at
even one.

## The one big idea: one variable that can only be one shape at a time

A panel like this has several very different things to show — a button,
a spinner, an error, or the diff itself — and only one of them is ever true
at once. The tempting way to write that in React is a pile of booleans:

```ts
const [loading, setLoading] = useState(false);
const [error, setError] = useState<string | null>(null);
const [plan, setPlan] = useState<FixPlan | null>(null);
```

The problem: nothing stops `loading` and `error` from both being true at
the same time, even though that combination makes no sense. TypeScript has
a better shape for "exactly one of these, ever" — a **discriminated
union**: one variable, several possible shapes, each tagged with a `kind`
field that says which one it currently is.

A tiny example with nothing to do with this project — a traffic light can
only ever be one color:

```ts
type Light = { kind: "red" } | { kind: "yellow" } | { kind: "green" };

function describe(light: Light): string {
  if (light.kind === "red") return "stop";
  if (light.kind === "green") return "go";
  return "slow down"; // TypeScript knows this must be "yellow"
}
```

Once TypeScript sees `light.kind === "red"` return early, it knows every
later branch *cannot* be red anymore — it narrows the type for you. That's
the exact mechanism `FixPlanPanel` uses:

```ts
type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "unavailable" }
  | { kind: "preview"; plan: FixPlan }
  | { kind: "saving"; plan: FixPlan }
  | { kind: "saved"; plan: FixPlan }
  | { kind: "error"; message: string };
```

Only the `"preview"` / `"saving"` / `"saved"` states carry a `plan` — and
because of that, the component can never accidentally try to render a diff
it doesn't have yet. That's a bug an "everything's a separate boolean"
version couldn't rule out at all; here it simply can't happen.

## The actual code

```tsx
async function check() {
  setState({ kind: "loading" });
  try {
    const plan = await fetchFixPlan(scanId, findingKey);
    setState(plan ? { kind: "preview", plan } : { kind: "unavailable" });
  } catch (err) {
    setState({ kind: "error", message: /* ... */ "" });
  }
}
```

- `fetchFixPlan` hits the new `GET .../fix/plan` route — a live preview,
  nothing saved yet.
- `null` back from the backend means "no deterministic fixer for this
  finding," which is a completely normal outcome, not a failure — it's
  shown as its own `"unavailable"` state, not lumped in with `"error"`.
- `"Save fix plan"` calls `POST .../fix/plan`, which persists the plan so
  it survives a refresh and gets bundled into the downloadable zip.

The diff itself is just `patch.diff.split("\n")` mapped into one `<div>`
per line, styled by checking how the line starts (`+`, `-`, or `@@`) — the
same "look at the first character" trick a unified diff was built on in
the last note, now used to color it back in on screen.

## Try it

- Open a repo scan's `/agents/repo-config` page and click **Check for
  automatic fix →** on the "No .gitignore file found" finding.
- Click **Save fix plan**, then **Download patch bundle** — the file that
  downloads is a zip of every plan saved for that scan so far.
- In `FixPlanPanel.tsx`, try adding an eighth fake state to the `State`
  type without handling it anywhere — TypeScript will complain the moment
  you use it, before you ever run the app.

## Words worth knowing

- **Discriminated union** — one type that's really several shapes, each
  tagged by a shared field (here, `kind`) so TypeScript always knows which
  one it's looking at.
- **Narrowing** — TypeScript shrinking what a variable's type could be
  after a check like `if (state.kind === "preview")`.

---

**Next:** nothing queued yet — Stage B (actually opening a pull request on
GitHub) is the natural follow-up, once it's picked up.

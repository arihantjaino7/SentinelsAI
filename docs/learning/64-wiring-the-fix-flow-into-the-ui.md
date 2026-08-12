# 64 — Wiring the fix flow into the UI

> **Status:** done. `app/settings/page.tsx`, `components/fixes/FixApplyPanel.tsx`,
> `lib/api.ts` (Stage B + C calls), plus two small edits: `FixPlanPanel` mounts
> the new panel, and the scan nav gained a Settings link. `tsc --noEmit` and
> ESLint clean; verified in a real browser against the real repository.

## What we built

Stages B and C existed as endpoints nobody could reach. Now:

```
finding → Check for automatic fix → diff → Save
        → Preview pull request (dry run) → Open pull request
        → [you merge it on GitHub] → Verify → 64 → 72
```

Plus `/settings`, which had been a 404 the install flow redirected to.

## The one big idea: the UI mirrors what the backend refuses

Every button here exists because of a rule, and every message is the backend's
own words rather than a friendly rewrite of them.

The clearest case. Click Verify while the pull request is still open and you
get, verbatim:

> PULL REQUEST #1 HAS NOT BEEN MERGED YET. MERGE IT FIRST — VERIFYING NOW WOULD
> ONLY RE-OBSERVE THE ORIGINAL PROBLEM.

That's a 409 from the API, printed as-is. The temptation is to soften it into
"Not ready yet" — which would hide *why*, and the why is the whole point.

## State that survives its own errors

First instinct for a component with phases is one variable:

```tsx
type State = { kind: "open"; application } | { kind: "error"; message };
```

It breaks the moment a request fails. Going to `{kind: "error"}` throws away
the pull request we already knew about — so a failed Verify would erase the PR
link from the screen. The user's fix would look like it vanished.

So state is split by *question*, not by phase:

```tsx
const [phase, setPhase] = useState<Phase>("loading");          // what's in flight
const [application, setApplication] = useState<FixApplication | null>(null);  // is there a PR
const [preview, setPreview] = useState<FixApplyPreview | null>(null);        // pending dry run
const [verification, setVerification] = useState<VerificationResult | null>(null);
const [notice, setNotice] = useState<Notice | null>(null);     // what to say right now
```

A 409 sets `notice` and leaves `application` alone. Which is exactly what you
saw in the screenshot above: the error and the pull request, together.

The tiny standalone version of the mistake:

```js
let state = { kind: "loaded", items: [1, 2, 3] };
state = { kind: "error", message: "oops" };   // the items are gone
```

versus

```js
let items = [1, 2, 3];
let error = "oops";        // both true at once, which is the reality
```

## `useState` vs `useEffect`, in one paragraph each

**`useState`** gives a component memory. `const [x, setX] = useState(0)` hands
back the current value and a setter; calling the setter re-renders the component
with the new value. Plain variables can't do this — they'd reset every render.

**`useEffect`** is for reaching *outside* React: fetching, timers,
subscriptions. It runs after the render, and its dependency array says when to
run again. The panel uses exactly one, to ask "has this finding already been
through the flow?":

```tsx
useEffect(() => {
  let cancelled = false;
  fetchFixApplications(scanId)
    .then((rows) => { if (!cancelled) { /* setState here */ } })
    .catch(() => { /* and here */ });
  return () => { cancelled = true; };
}, [scanId, findingKey, adopt]);
```

Two details worth copying:

- **The `cancelled` flag.** If the user navigates away before the request
  lands, the `.then` still fires — setting state on a component that's gone.
  The returned function is the *cleanup*, run when the effect is torn down, and
  it flips the flag so the late answer is dropped.
- **`setState` goes inside the callback, never in the effect body.** This
  project's ESLint config enforces it (`react-hooks/set-state-in-effect`); my
  first version called an `async` helper directly and got flagged. Setting state
  synchronously in an effect makes React render, run the effect, render
  again — a cascade.

## Nothing fetches on page load

`FixApplyPanel` only mounts after you click "Check for automatic fix", and only
then does it call `GET /scans/{id}/fix/applications`. That's deliberate: an
agent page can list a dozen findings, and a fetch per finding on load would
burn GitHub's rate limit before you read one of them. Same reasoning
`FixPlanPanel` already used for its manual trigger.

## One click, but never a silent write

The apply endpoint refuses a plan that was never saved (rule 6: what gets
pushed must be something a person could look at). Rather than adding a "you
must press Save first" error, the preview button saves as its first step:

```tsx
await saveFixPlan(scanId, findingKey);
const result = await applyFix(scanId, [findingKey], true);   // dry run
```

That's safe because saving writes nothing to GitHub, the diff is already on
screen above, and a dry-run preview stands between this and any write. The one
thing that *can* write to a repository still takes its own separate,
deliberate click on "Open pull request".

And in `lib/api.ts`, `applyFix`'s `dryRun` parameter defaults to `true` —
mirroring the backend's default, for the same reason: the dangerous shape has to
be typed out.

## An error class that remembers the status code

The older API helpers throw a plain `Error` with the message. That's fine when
every failure means the same thing. It isn't here — *why* a write was refused
decides what the UI should offer:

```ts
export class ApiError extends Error {
  readonly status: number;
}
```

- **403** → "Sentinels has no repository access for `arihantjaino7`" plus a link
  to `/settings`. Retrying is useless; connecting is the fix.
- **409** → a quiet informational line (already applied, or not merged yet).
  Not red, because nothing is broken.
- anything else → red.

`err instanceof ApiError && err.status === 403` is how the component tells them
apart. Without the status, all three would be one indistinguishable red string.

## A union whose branches overlap

`POST /fix/apply` returns a preview *or* a result, and every field the result
requires also exists on the preview. TypeScript can't guess which arrived, so
there's an explicit type guard on a field only one of them has:

```ts
export function isApplyPreview(v: FixApplyPreview | FixApplyResult): v is FixApplyPreview {
  return "pr_title" in v;
}
```

`v is FixApplyPreview` is a **type predicate**: inside an `if (isApplyPreview(r))`
block, TypeScript now treats `r` as a preview and lets you read `r.patches`.
It's the same problem that made the backend route declare `response_model=None`
(note 62) — the shapes overlap, so something has to discriminate them by hand.

## "Already fixed it yourself?"

The backend allows verifying a finding with no pull request of ours behind it —
someone may have patched it manually. The first UI draft had no way to ask for
that, so a real capability was invisible. Now the idle state has a quiet second
action, and the result carries its own honesty:

> No fix application was recorded for this finding, so nothing was closed out.

That's also the path I could exercise for real before anything was merged: it
re-ran `repo-config` against the live repository and reported **64 → 64, no
change** — correct, because the pull request wasn't merged yet. A verification
that lied about an unmerged fix would have shown up right there.

## Try it

- `/settings` → connect a repository, then Disconnect. Read the last paragraph
  on that page: disconnecting stops Sentinels using the grant, it does not
  uninstall the App on GitHub. Two different things, said plainly.
- On a repo scan's agent page, click "Check for automatic fix" → "Preview pull
  request". Watch the network tab: `POST /fix/apply` with `dry_run: true`, and
  no row added to `fix_applications`.
- Break the split-state idea on purpose: in `FixApplyPanel`, make `fail()` also
  call `setApplication(null)`. Click Verify on an unmerged PR and watch the pull
  request link disappear — that's the bug the five-`useState` shape avoids.

## Words worth knowing

- **Hook** — a function starting with `use` that gives a component memory
  (`useState`) or a way to reach outside React (`useEffect`).
- **Cleanup function** — what an effect returns; runs on teardown, which is how
  a late `fetch` answer gets ignored.
- **Type predicate** — `x is T`, a function that teaches TypeScript which branch
  of a union it's holding.
- **Dry run** — every check, no writes. The default here and on the backend.

---

**Next:** merge the pull request on GitHub, then hit Verify and watch the delta
go positive — the last step of PLAN-v5's definition of done.

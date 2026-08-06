# A13 — Next.js up

> **Status:** done. `npm run dev --prefix frontend` serves a styled input
> screen at `localhost:3000`, using the palette and fonts from
> [`../DESIGN.md`](../DESIGN.md). Nothing is interactive yet — that's next.

This is the first frontend note, and you're new to both JavaScript and
React, so it starts from scratch.

## What we built

Three files: `frontend/app/page.tsx` (the screen you see — a heading, a
sentence, a text box, a button), `frontend/app/layout.tsx` (the wrapper
every page sits inside — loads the fonts, sets up `<html>`/`<body>`), and
`frontend/app/globals.css` (where the design's colors and fonts become real
CSS values). The button doesn't do anything yet — that's next note's job.

## The one big idea: a component is just a function that returns UI

That's the whole idea React is built on. A **component** is a plain
JavaScript function. It takes some data in, and it returns a description of
what should appear on screen.

```jsx
function Greeting() {
  return <p>Good morning.</p>;
}
```

That `<p>Good morning.</p>` sitting inside a JavaScript function is called
**JSX** — it looks like HTML, but it isn't a string and isn't real HTML. It's
JavaScript syntax that gets converted into plain function calls before the
browser ever sees it, so you can treat it like any other value: put it in a
variable, return it, pass it around.

One hard rule: a component's name must start with a capital letter
(`Greeting`, not `greeting`) — that's how React tells "my component" apart
from a real HTML tag like `<p>`.

Where does the URL come from? In FastAPI you wrote `@app.get("/health")` —
the string *is* the URL. Next.js does the same job with folders instead: a
file at `app/page.tsx` becomes `/`, a file at `app/report/page.tsx` would
become `/report`. The folder path literally *is* the route. This is called
the **App Router**.

## Second idea: Tailwind — styling written right where it's used

Normal CSS: give something a name, then describe it somewhere else.

```css
.notice { padding: 1rem; font-size: 0.875rem; }
```
```html
<div class="notice">Closed Sundays.</div>
```

Tailwind skips the naming step — you list the descriptions directly as
classes:

```html
<div className="p-4 text-sm">Closed Sundays.</div>
```

`p-4` is padding, `text-sm` is font size. It looks noisy at first, but you
never have to go hunting in a second file to find out how something is
styled — it's right there on the element. (JSX uses `className` instead of
`class`, because `class` is already a reserved JavaScript word.)

## The actual code

```jsx
// frontend/app/layout.tsx — the wrapper around every page
export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="font-body min-h-full flex flex-col">{children}</body>
    </html>
  );
}
```

`children` is whatever page is currently being shown — the layout doesn't
know or care which one, it just drops it into that spot.

```jsx
// frontend/app/page.tsx — the actual screen at "/"
export default function Home() {
  return (
    <main className="flex flex-1 items-center justify-center px-6 py-24">
      <h1 className="font-display text-5xl sm:text-6xl">
        Every site leaves<br />a record.
      </h1>
      <input className="border-b border-rule bg-transparent pb-3 font-mono text-lg" />
      <button type="button" className="glass px-6 py-3 font-mono text-xs uppercase">
        Inspect
      </button>
    </main>
  );
}
```

`export default` is required on every `page.tsx` and `layout.tsx` — it's how
Next.js knows which function to render. The button is `type="button"` on
purpose, so it can't accidentally submit or reload the page before it's
wired up.

Colors and fonts come from `globals.css` the same way:

```css
@theme {
  --color-ink: #0e0e0d;
}
```

Declaring `--color-ink` here automatically gives you Tailwind classes like
`bg-ink` and `text-ink` — no extra config file needed.

## Try it

- Rename `Home` to `home` (lowercase) in `page.tsx` — the page breaks. React
  decides "component or HTML tag" purely from that first letter.
- Open the page and view source (Ctrl+U). The heading text is already in
  the raw HTML — nothing had to run in the browser to produce it.
- Change `--color-ink` in `globals.css` to a different hex and refresh — the
  whole background changes from one line.

## A few words worth knowing

- **Component** — a function that returns UI. Must start with a capital
  letter.
- **JSX** — HTML-like syntax inside JavaScript; not a string, not real HTML.
- **App Router** — Next.js routing where a file's folder path *is* the URL.
- **Tailwind utility class** — a class that does one styling job (`p-4`,
  `text-sm`), written directly on the element instead of in a separate file.
- **`export default`** — marks the one main thing a file exports; required
  on every page/layout file.

---

**Next:** A14 — making the button actually do something.

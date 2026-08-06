# How to use these notes

One note per achievement (see [`../ROADMAP.md`](../ROADMAP.md)). Written *alongside*
the code, not after — so if the code exists, the note explaining it exists too.

## What's in every note

Each note follows the same five sections:

### 1. What we built, in one paragraph
Plain English. No jargon. If you read only this, you still know what changed.

### 2. New concepts
Every idea the code introduces, each with a **tiny standalone example** — 3–10 lines
you can paste into a file and run on its own, with no rest-of-the-project needed.
The example is always about something ordinary, *not* about security scanning, so the
concept stays separable from our project.

### 3. The actual code, walked through
Our real code, in chunks, with the reasoning for each decision — including the
choices we *rejected* and why.

### 4. Try this
Small experiments: break it on purpose, change a value, see what happens. This is
where it actually sticks.

### 5. Words you now know
A short glossary of the terms introduced, so you can search them later.

---

## A worked sample of the style

Here's the level of explanation to expect. Say the code contained this line:

```python
findings: list[Finding] = Field(default_factory=list)
```

The note would explain it like this:

> **Concept: mutable default arguments**
>
> In Python, a default value is created **once**, when the function or class is first
> defined — not each time it's used. For immutable values (numbers, strings) that's
> harmless. For a mutable value like a list, it's a classic bug: every instance ends up
> sharing *the same list*.
>
> Standalone example — run this and watch it go wrong:
>
> ```python
> def add_topping(topping, pizza=[]):   # the bug: one list, shared forever
>     pizza.append(topping)
>     return pizza
>
> print(add_topping("cheese"))   # ['cheese']          — fine
> print(add_topping("olives"))   # ['cheese', 'olives'] — wrong! expected ['olives']
> ```
>
> The second call was supposed to start fresh, but it inherited the first call's list.
>
> The fix is to build a *new* list each time:
>
> ```python
> def add_topping(topping, pizza=None):
>     if pizza is None:
>         pizza = []          # a brand-new list, every call
>     pizza.append(topping)
>     return pizza
> ```
>
> `Field(default_factory=list)` is Pydantic's version of exactly that fix. `list` here
> is the *function* — not `list()`, the result of calling it. Pydantic calls it fresh for
> every new object, so each `AgentResult` gets its own findings list. In our code, this is
> what stops the Headers agent's findings from leaking into the TLS agent's results.

That's the standard: **the concept, an ordinary example, the mistake it prevents,
then where it lands in our code.**

---

## Reading order

Notes are numbered to match achievements, and each assumes the ones before it. Read in
order the first time. After that they work fine as reference — jump to whichever one
covers what you've forgotten.

## If something isn't clear

Say so, and name the specific line. Vagueness in these notes is a bug in them, not a
gap in you — I'll rewrite the section rather than re-explain it verbally.

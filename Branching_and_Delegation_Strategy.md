# ChemSentry — Branching & Team Delegation Strategy

Two things this document answers: how code moves from a laptop into `main` without
stepping on anyone else's work, and who is responsible for what when something needs
a decision. Read alongside `setup.md` (environment) and `CLAUDE.md` (technical
constraints).

---

## Part I — Branching Strategy

### 1. Model: GitHub Flow, not GitFlow

One long-lived branch (`main`), short-lived feature branches, PR review before merge.
No `develop` branch, no release branches — a 10-week, 4-person project doesn't need
GitFlow's overhead, and `main` staying always-demoable matters more here than a
staged release pipeline.

```
main ────●────●────●────●────●────●────●──── (always working, always demoable)
           \        \        \
            feature/  feature/ feature/
            m1-...    m2-...   m3-...
                 \        \        \
                  ●───●───●   PR → review → merge
```

### 2. Branch naming

```
feature/<member>-<short-description>     feature/m2-tfidf-ranking
fix/<short-description>                  fix/regex-cas-number-boundary
eval/<short-description>                 eval/retrieval-benchmark-v1
docs/<short-description>                 docs/architecture-diagram-update
```

Member prefix on `feature/` branches only — it's what makes `git log --all --oneline`
readable when four people are working in parallel, and it makes commit history
legible for the viva's individual-contribution check without anyone needing to
explain it.

### 3. Branch protection on `main` (set this up Week 3, in repo Settings → Branches)

- Require a pull request before merging — no direct pushes, including from admins
- Require at least **1 approving review**
- Require status checks to pass (lint + tests) before merge
- **Require 2 approving reviews** specifically for changes touching `safety/` or
  `agents/protocols/` — these are the shared, high-risk surfaces (the deterministic
  safety-state logic, and the MCP schemas every agent depends on). A rule in GitHub's
  branch protection can scope this with a `CODEOWNERS` file (see §6).
- Require branches to be up to date with `main` before merging

### 4. Merge strategy: **merge commit**, not squash

Squash-and-merge collapses a branch's history into one commit under the PR author.
That's convenient, but it quietly erases the day-to-day commit trail that makes
individual contribution visible. Use **"Create a merge commit"** as the repo's
default merge method — every commit keeps its own author and timestamp, and the PR
itself still gives you a clean unit of review.

### 5. Commit messages

Short, imperative, prefixed by type:

```
feat: add k-gram index builder for chemical name resolution
fix: correct CAS number regex boundary on multi-digit prefixes
test: add coverage for Jaccard conflict detection edge cases
docs: update evaluation results table for Week 5 benchmark run
refactor: extract section-splitting logic into its own module
```

This isn't ceremony — a consistent prefix makes `git log` skimmable when you're
writing the report's contribution section in Week 9, and it's a five-second habit.

### 6. `CODEOWNERS` — shared-surface protection

Add a `.github/CODEOWNERS` file so changes to shared code automatically request the
right reviewers:

```text
/agents/protocols/   @m2-github-handle @m3-github-handle @m4-github-handle
/safety/             @m3-github-handle @m2-github-handle
/docs/architecture.md @all-four-handles
```

This is what actually enforces the "2 reviewers on shared surfaces" rule from §3 —
GitHub won't let a PR touching those paths merge without sign-off from the people it
affects.

### 7. Milestone tags

Tag `main` at each graded checkpoint, so you have a reproducible snapshot rather than
"whatever `main` happened to be that day":

```bash
git tag -a v0.1-mid-eval -m "Mid-evaluation submission, Week 6"
git tag -a v1.0-final -m "Final submission, Week 10"
git push origin --tags
```

Useful for the video recording too — record against the tagged commit, not a moving
target.

### 8. Freeze windows

The two days before Week 6 and Week 10: no new feature branches merge, only fixes to
things breaking the demo. Decide this as a team in advance rather than discovering it
mid-panic the night before mid-eval.

### 9. Worked example — a normal day

```bash
git checkout main && git pull
git checkout -b feature/m2-index-elimination
# ...work, commit as you go...
git push -u origin feature/m2-index-elimination
# open PR on GitHub, tag reviewer per CODEOWNERS or the rotation in Part II §2
# address review comments as new commits on the same branch
# once approved + CI green → merge commit → delete branch
```

---

## Part II — Team Delegation Strategy

### 1. Ownership (recap, now with decision authority attached)

| | Owns | Final say on |
|---|---|---|
| **M1** | Crawler, extraction, preprocessing, indexing | Corpus format, tokenizer behaviour |
| **M2** | Retrieval cascade, ranking, evaluation suite | What counts as a passing benchmark |
| **M3** | Reconciliation, safety states, classifier, Apriori, LLM layer | Safety-state logic, RAI boundary enforcement |
| **M4** | Agent C, IoT, security, gateway, UI, deployment | Infra, deployment, API contracts exposed to the frontend |

"Final say" means: if there's a disagreement inside that domain and the team can't
resolve it in five minutes, that person's call is the tiebreaker. It does not mean
working alone — see the review rotation below.

### 2. Cross-review rotation

A fixed ring, so review load is predictable and everyone ends up reading someone
else's code regularly (this is what makes the Week 5 cross-layer explainers actually
useful instead of theoretical):

```
M1 reviews M2  →  M2 reviews M3  →  M3 reviews M4  →  M4 reviews M1
```

Each person is a **primary reviewer** for one other slice and can be pulled in as a
secondary reviewer anywhere. Shared-surface PRs (`safety/`, `agents/protocols/`)
route through `CODEOWNERS`, not the rotation.

### 3. Decision rights for cross-cutting changes

Some changes touch more than one person's slice by nature — an API contract change
between Agent A and the gateway, a database schema change, a change to the MCP tool
signatures. For these:

1. Open an issue *before* opening a PR, tagged `cross-cutting`
2. Whoever's proposing it states what changes and why, in the issue
3. Every affected owner gets 24 hours to object or approve async
4. If no resolution in 24 hours, raise it at the next sync rather than letting it
   block silently

### 4. Weekly cadence

- **One sync per week**, ideally right after your lab session since you're already
  together — 20 minutes is enough if the board (Issues/Projects) is kept current
  between syncs
- **Async standup** in whatever chat tool you use — one line each, three questions:
  what you finished, what you're starting, what's blocking you
- **PR review SLA: within 48 hours.** A PR sitting unreviewed for a week is a
  bottleneck disguised as busy-ness — if you can't review within 48h, say so in the
  PR rather than letting it go silent

### 5. Definition of done

A task isn't done when the code runs once on your machine. It's done when:

- [ ] Code is committed and pushed to a feature branch
- [ ] At least one test exists for it (in `tests/`)
- [ ] It's referenced in the relevant lab/lecture in a docstring or comment, per
  `CLAUDE.md`'s coding standard
- [ ] PR is opened, reviewed, and merged via merge commit
- [ ] If it changes retrieval behaviour, the evaluation suite has been re-run and
  `evaluation/results/` is updated

### 6. If someone falls behind

Say it early, in the weekly sync, not in Week 9. The fix is almost always
redistribution, not blame — M2's slice is the heaviest by design (§1 of the per-member
plan), so it's the most likely place this happens. Two mitigations already built in:
the cross-review rotation means a second person already has partial context on every
slice, and the `feature/` branch naming makes it easy to see at a glance whose work
is stalled versus whose is moving.

### 7. Communication norms

- **GitHub Issues** — the task board and the source of truth for what's being worked
  on (see the earlier task-organisation plan)
- **A shared chat channel** — for the async standup and quick questions; not for
  decisions on cross-cutting changes, which belong in an issue so there's a record
- **The weekly sync** — for anything that's been stuck async for more than a day

Keep decisions in writing (issues, PR comments) rather than only in chat — six weeks
from now, when you're writing the report's methodology section, a paper trail of
*why* a decision was made is worth far more than someone's memory of a conversation.

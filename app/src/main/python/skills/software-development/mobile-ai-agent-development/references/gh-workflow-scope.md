# GitHub `workflow` Scope Trap — OAuth Tokens Can't Push Workflow Files

## Symptom

Pushing a repo that contains `.github/workflows/*.yml` via a `gh` OAuth token fails:

```
! [remote rejected] main -> main (refusing to allow an OAuth App to create or
update workflow `.github/workflows/build.yml` without `workflow` scope)
```

Even `gh api` PUT to a workflow path returns **HTTP 404** — NOT 403. GitHub
deliberately hides the path so it looks like a repo/path bug. A control test
(root-level `test.txt`) succeeds, which makes the workflow-path 404 extra
confusing. `gh api GET` on `.github/workflows/` (list) works fine — only writes
are gated.

## Root Cause

`gh auth login` default scopes: `gist, read:org, repo`. Workflow files are
executable code (they run on GitHub's runners), so GitHub requires the
`workflow` scope on the OAuth token. `auth status` shows the scopes.

## Fix — device-code refresh (keep the process ALIVE)

```bash
gh auth refresh -h github.com -s workflow,delete_repo
```

Critical: this prints a one-time code and waits for the user to visit
https://github.com/login/device. **The gh process must stay alive until the
user enters the code.** Running it in foreground with a short `timeout=8`
kills the process and the code dies — the user enters it, nothing happens,
and the token never gains the scope. Run it as a background process
(`terminal(background=true)`), read the code from the output, hand it to the
user, then poll. Codes expire in ~15 min.

## Workaround that needs no scope at all

Create/update workflow files via the GitHub **web UI** (Add file → Create new
file → commit). The user can do this in their browser while logged in. Keep
`.github/workflows/` out of local `git push` (add to `.git/info/exclude` or
just don't stage it).

## Related: accidental workflow deletion

`git rm --cached .github/workflows/android.yml` stages a deletion that a later
`git commit` happily pushes even without `workflow` scope (deleting a workflow
file is allowed; only creating/updating is gated). Result: CI silently stops
running. Always verify the workflows dir still exists on GitHub after
interleaved commits: `gh api repos/<owner>/<repo>/contents/.github/workflows`.

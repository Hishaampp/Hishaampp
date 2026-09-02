# Setup

1. Create the repo — **it must be named exactly your username**:
   ```
   gh repo create Hishaampp --public --clone
   ```
   (or create it empty on github.com — the special name `Hishaampp/Hishaampp`
   is what makes GitHub show its README on your profile page)

2. Copy every file from this folder into that repo, preserving paths:
   ```
   .github/workflows/refresh-stats.yml
   scripts/generate_stats.py
   fonts/jbm-regular.woff2
   fonts/jbm-bold.woff2
   fonts/OFL.txt
   README.md
   .gitignore
   ```

3. Commit and push:
   ```
   git add -A
   git commit -m "profile: self-generating stats"
   git push
   ```

4. Trigger the first run by hand — don't wait for the 05:17 UTC cron:
   Repo → **Actions** tab → **refresh stats** → **Run workflow**.

   It needs no secrets — the built-in `GITHUB_TOKEN` GitHub injects into
   every workflow run is enough (that's also *why* it only sees your
   **public** repos, which is exactly what `privacy: PUBLIC` in the query
   assumes).

5. After it finishes (~10–20s), refresh your profile page
   (`github.com/Hishaampp`). The four SVGs will be sitting in the repo root
   and the README will render them.

## Things to check the first time

- **Branch protection.** If `main` has any protection rules, the Action's
  push in step 4 will fail silently in the job log — you'll see a
  permission error on `git push`. Either allow the `github-actions[bot]`
  actor to push, or point the workflow at a rule-free branch.
- **Actions must be enabled** for the repo (Settings → Actions → General →
  Allow all actions). Fresh repos usually have this on by default.
- **A brand-new profile README can be cached.** If it doesn't show up on
  your profile after the run, open `README.md` in the web UI and hit edit
  → cancel — that forces a cache refresh.
- **Timezone of the cron.** `17 5 * * *` is 05:17 **UTC**. Adjust in
  `.github/workflows/refresh-stats.yml` if you want it to land at a
  particular local time.

## What's not included yet

This is Part 2 from the guide — the stats graphics only. The ASCII
portrait (Part 1) needs a source photo from you: side-lit, tight crop,
1200px+. Send one over and I'll build that piece too, plus the SVG
section headings from Part 3 if you want the fuller look.

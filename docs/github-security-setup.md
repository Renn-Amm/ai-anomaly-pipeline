# GitHub Branch Protection & Security Setup

This document lists every setting to apply after pushing the repo to GitHub.
Follow them in order — they take about 10 minutes.

---

## 1. Branch Protection Rules (Settings → Branches → Add rule)

### `main` branch

| Setting | Value |
|---|---|
| Require a pull request before merging | ✅ |
| Required approvals | 1 |
| Dismiss stale PR approvals when new commits are pushed | ✅ |
| Require status checks to pass before merging | ✅ |
| Required status checks | `lint`, `test (3.12)`, `security`, `docker-build` |
| Require branches to be up to date before merging | ✅ |
| Require conversation resolution before merging | ✅ |
| Do not allow bypassing the above settings | ✅ |
| Allow force pushes | ❌ |
| Allow deletions | ❌ |

### `develop` branch  
Same as above, but only 1 required approval.

---

## 2. GitHub Environments (Settings → Environments)

### staging
- Add protection rule: require 1 reviewer
- Add secret: `STAGING_DEPLOY_KEY`

### production
- Add protection rule: require 2 reviewers
- Add secret: `PROD_DEPLOY_KEY`
- Deployment branches: Tags matching `v*.*.*`

---

## 3. Repository Secrets (Settings → Secrets and variables → Actions)

| Secret | Value |
|---|---|
| `STAGING_DEPLOY_KEY` | SSH private key for staging server |
| `PROD_DEPLOY_KEY` | SSH private key for production server |

> `GITHUB_TOKEN` is provided automatically — do NOT add it manually.

---

## 4. Dependabot (Settings → Code security → Dependabot)

Enable all of:
- Dependabot alerts
- Dependabot security updates
- Dependabot version updates

Create `.github/dependabot.yml` (already included in this repo).

---

## 5. Code Scanning (Settings → Code security → Code scanning)

- Enable CodeQL for Python
- Run on push and pull_request

---

## 6. Secret Scanning (Settings → Code security)

- Enable secret scanning
- Enable push protection (blocks commits containing detected secrets)

---

## 7. Rulesets (optional, if using GitHub Enterprise)

Add an organization-level ruleset that enforces the branch protection
settings above across all repos automatically.

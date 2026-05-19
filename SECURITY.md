# Security

## Exposed credentials (google-stuff)

If `google-stuff` was ever committed or pushed to GitHub, treat these as **compromised** and rotate immediately:

1. **Google Cloud Console** → APIs & Services → Credentials → your OAuth client → reset **client secret**
2. Update `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in server `.env`
3. Generate a new `SECRET_KEY` in `.env` and sign in again (invalidates sessions)
4. If `AUTH_PASSWORD` was only in that file, set a new `AUTH_PASSWORD_HASH` via `scripts/hash_password.py`

## Prevention

- `google-stuff`, `.env`, `secrets/`, and `*client_secret*.json` are gitignored
- Use `.env` on the server only; copy from `.env.example`

## Remove secrets from git history

If secrets were pushed, after rotating credentials rewrite history and force-push:

```bash
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch google-stuff" \
  --prune-empty --tag-name-filter cat -- --all
rm -rf .git/refs/original/
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push origin --force --all
```

Coordinate with anyone else who cloned the repo before force-pushing.

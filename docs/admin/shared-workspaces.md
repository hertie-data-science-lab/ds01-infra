# Shared Collaborative Workspaces

Shared workspaces let several users work on the **same files** — a shared codebase, a
common dataset, joint results — on the host and inside their GPU containers. They live
under `/home/shared/<name>` and are managed with the `shared-workspace` admin command.

They are the collaborative counterpart to a user's private `~/workspace/<project>`: the
same "mount it into a container" workflow, but with multiple members instead of one owner.

---

## Managing workspaces

```bash
# Create a workspace and grant its first members (usernames = AD accounts)
sudo shared-workspace create pragmata-workspace \
    h.baker@hertie-school.lan d.dimmery@hertie-school.lan l.ruiz@hertie-school.lan

# Add / remove a collaborator later
sudo shared-workspace add-member pragmata-workspace a.n.other@hertie-school.lan
sudo shared-workspace remove-member pragmata-workspace a.n.other@hertie-school.lan

# Inspect
shared-workspace list                        # all workspaces + member counts
shared-workspace list pragmata-workspace     # members of one
```

`create` / `add-member` / `remove-member` require root (they write under `/home` and
change ACLs); `list` does not. The command lives at `scripts/admin/shared-workspace`.

---

## How access works — and why ACLs, not a group

Each member is granted access with a **per-user POSIX ACL** (`setfacl -m u:<user>:rwX`),
plus a matching **default ACL** so new files inherit the same grants. Access is
deliberately *not* modelled as a shared Unix group. Two hard constraints on DS01 force
this choice:

1. **Containers drop secondary groups.** A container runs as the user's real
   `--user uid:gid` with no user-namespace remapping, and only the **primary** gid is
   passed in. A `setgid` directory owned by a shared group would therefore be silently
   **unwritable inside containers**, because the container process isn't a member of that
   group. ACL `user:` entries key on the **uid**, which *is* propagated, so they work
   identically on the host and in the container.
2. **The host umask is `077`.** New files default to owner-only. A directory **default
   ACL** is the only mechanism that keeps new files readable/writable by the other members
   regardless of umask; `setgid` alone cannot (the group-write bit would be masked off).

The directory itself is `2770 datasciencelab:ds-admin` (setgid for consistent group
ownership, no access for `other`); members reach it purely via their ACL entries.

---

## Why `/home/shared` survives the home-privacy enforcement

DS01 keeps personal homes private: `/etc/profile.d/ds01-home-enforce.sh` runs
`chmod 700 "$HOME"` on every login, and `fix-home-permissions.sh` /
`existing-users-permissions.sh` can sweep `/home/*` back to `0700`. `/home/shared` is
exempt from all of these:

- The login hook only ever touches a **real user's own `$HOME`** — `/home/shared` is
  nobody's home, so it is never touched.
- Both sweep scripts skip `shared` explicitly (alongside `lost+found`).
- `config/permissions-manifest.sh` re-asserts `/home/shared` as `root:ds-admin 0755` on
  every deploy and every 15 minutes, so the root self-heals if anything disturbs it. The
  manifest manages the **root only** and never recurses into projects (their ACLs are
  dynamic and owned by `shared-workspace`).

---

## Using a workspace in a container

Mount it as the container workspace at launch; it appears at `/workspace`, read/write:

```bash
container-deploy <project> --workspace /home/shared/<name>
```

(A future `--shared <name>` convenience flag may remove the need to type the full path.)

---

## Verifying / troubleshooting

```bash
# What ACLs are on a workspace?
getfacl /home/shared/<name>

# Can a specific member reach it? (run as that user)
sudo -u <user> bash -c 'cd /home/shared/<name> && touch _t && rm _t && echo OK'

# The home sweep must NOT flag it:
sudo bash scripts/maintenance/fix-home-permissions.sh --check   # no issue for /home/shared
```

- *A member can't write a file another member created* → confirm the workspace has a
  **default** ACL (`getfacl` shows `default:user:<uid>:rwx`). Files created before that
  member was added won't carry their entry — re-run `add-member` (it applies recursively).
- *Access works on the host but not in the container* → confirm you mounted the path with
  `--workspace`; the container sees `/workspace`, not `/home/shared`.

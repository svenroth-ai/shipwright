#!/usr/bin/env bash
# Sync Shipwright marketplace from GitHub and refresh all plugin caches.
# Usage: bash scripts/update-marketplace.sh
#
# Works for:
#   - Developers: run after 'git push' to sync local install (full file sync)
#   - End-users: run any time to get latest updates
#
# The script does a FULL FILE SYNC from the marketplace clone into each
# plugin's installed cache directory. This ensures local development changes
# are always reflected, regardless of version number changes.
set -euo pipefail

# True if lock directory $1 currently records $2 as its holder — read its
# own pid file and compare, rather than trusting that a path still refers to
# whatever its caller once created there. A failed stale-lock restore (round
# 9 of this review) can leave a DIFFERENT process's live lock sitting at a
# path this process once owned; without this check, that process's own
# eventual cleanup (`rm -rf "$lock"`, unconditional and by path alone) would
# delete the new owner's lock out from under it, letting a THIRD contender
# in and cascading the exact corruption locking exists to prevent (Tier-3
# review, PR #796 round 10). Every deletion of a NAMED (non-private) lock
# path must go through this, never a bare `rm -rf "$lock"`.
_lock_is_owned_by() {
    [ "$(cat "$1/pid" 2>/dev/null || echo "")" = "$2" ]
}

# _atomic_sync_dir (below) holds at most one lock at a time — its calls are
# sequential, never parallel, within this script. A single tracked path is
# therefore enough for a script-wide EXIT trap to release whatever lock this
# process currently holds if it dies mid-sync (errexit, Ctrl-C, kill): without
# this, a lock acquired then never released via the function's own normal
# cleanup would deadlock every future sync of that $dst forever. Guarded by
# `_lock_is_owned_by` for the reason in its own comment above.
_CURRENT_SYNC_LOCK=""
trap '[ -n "$_CURRENT_SYNC_LOCK" ] && _lock_is_owned_by "$_CURRENT_SYNC_LOCK" "$$" && rm -rf "$_CURRENT_SYNC_LOCK" 2>/dev/null; true' EXIT

# True if $1 names a Windows/MSYS PID that is still alive — used to tell a
# leftover from a process that crashed mid-sync apart from one a CONCURRENT,
# still-running sync still owns (Tier-3 review, PR #796: blindly sweeping by
# name alone can delete another active sync's own staging/backup/lock dirs).
_pid_is_alive() {
    [ -n "$1" ] && kill -0 "$1" 2>/dev/null
}

# A backup/staging leftover whose PID suffix equals OUR OWN "$$" can only be
# read as "still live" by a bare `_pid_is_alive` check -- but we are running
# this exact function for the first time this invocation and have not yet
# created anything at that name, so if something is already sitting there, a
# dead process's PID has been recycled onto us. Treating that as "live"
# skipped recovering it as the orphaned $dst backup it actually is, and the
# later unguarded `rm -rf "$old"` right before the swap then permanently
# destroyed it -- the only remaining copy of the previous destination
# (Tier-3 review, PR #796 round 22, data-loss finding). Every leftover-PID
# liveness check for OUR OWN sibling paths (staging/old/lock/find-list) must
# go through this, never `_pid_is_alive` directly.
_leftover_pid_is_alive() {
    [ "$1" != "$$" ] && _pid_is_alive "$1"
}

# A random, high-entropy per-CLAIM identity — a pid alone is not one: the OS
# recycles pid numbers, so a genuinely different, later claim can coincide
# with an earlier one's pid by pure chance. Every "$lock/pid" write below is
# paired with one of these into "$lock/token", and the ABA mismatch check
# compares BOTH, not the pid alone (Tier-3 review, PR #796 round 15).
_new_claim_token() {
    printf '%s-%s-%s' "$$" "$RANDOM" "$RANDOM"
}

# `while read < <(find ...)` never surfaces `find`'s own exit status: the
# process substitution runs in a background subshell the calling command's
# `$?` (and `set -e`) know nothing about, so a `find` that dies partway
# through (permission error, interrupted scan) is silently indistinguishable
# from one that legitimately enumerated everything and found nothing more —
# the while loop just sees EOF either way and the caller sees success (Tier-3
# review, PR #796 round 17). Writing the listing into a real FILE first, with
# `find`'s own exit status checked directly on that write, closes this: every
# `_atomic_sync_dir` enumeration below goes through here and its caller must
# treat a non-zero return as "abort before touching $staging/$dst", never
# "proceed with whatever was enumerated so far".
_find0_to_file() {
    local outfile="$1" desc="$2"
    shift 2
    if ! find "$@" -print0 > "$outfile"; then
        echo "  [!!] enumerating $desc failed" >&2
        return 1
    fi
}

MARKETPLACE_NAME="shipwright"
MARKETPLACE_DIR="$HOME/.claude/plugins/marketplaces/shipwright"
INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
HTTPS_URL="https://github.com/svenroth-ai/shipwright.git"

# All plugins in the marketplace
PLUGINS=(
    shipwright-run shipwright-project shipwright-design shipwright-plan
    shipwright-build shipwright-test shipwright-deploy shipwright-changelog
    shipwright-compliance shipwright-security shipwright-iterate shipwright-preview
    shipwright-adopt shipwright-grade
)

echo "=== Shipwright Marketplace Update ==="

# Check claude CLI is available
if ! command -v claude &>/dev/null; then
    echo "Error: 'claude' CLI not found. Install Claude Code first."
    exit 1
fi

# Resolve a Python interpreter. A bare ``python`` does not exist on
# Ubuntu/Debian/macOS (only ``python3``); under ``set -e`` the command
# substitutions below would then resolve to nothing and abort the entire
# sync silently (deep-audit F37). Probe python3 → python → py, in order.
#
# Probe by TEST-RUNNING ``--version``, not just ``command -v``: on Windows
# ``python3`` is usually the Microsoft Store App-Execution-Alias *stub* —
# ``command -v`` finds it, but invoking it prints "Python was not found" and
# exits 49, so a ``command -v``-only probe selects a non-working interpreter
# and the first ``$(python3 -c …)`` below then aborts the whole sync under
# ``set -euo pipefail`` (F37 fixed POSIX but regressed Windows). Requiring a
# successful ``--version`` makes the stub fall through to the real interpreter.
PYTHON_BIN=""
for _candidate in python3 python py; do
    if command -v "$_candidate" &>/dev/null && "$_candidate" --version >/dev/null 2>&1; then
        PYTHON_BIN="$_candidate"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "Error: no Python interpreter found (tried python3, python, py)."
    echo "       Install Python 3.11+ and re-run."
    exit 1
fi

# Sync $src into $dst as an ATOMIC directory swap, not a file-by-file
# overwrite of the live target. A live Claude Code session's Stop hook can
# import from $dst (e.g. `lib.campaign_wave`) at any instant; the previous
# implementation copied newly-added files into $dst one at a time via a long
# -running `find | while read` loop, so a brand-new module was simply ABSENT
# from the live cache for the entire loop's duration, until `find`'s
# traversal reached it — a concurrent `import lib.campaign_wave` in that
# window raised ModuleNotFoundError even though the file existed in the repo
# and the marketplace clone (iterate-2026-09-24-stop-hook-cache-race).
# Building the merged tree in a staging dir first and swapping it in with two
# back-to-back `mv`s (each a single atomic rename syscall) shrinks that
# exposure from "however long the copy takes" to the gap between two
# syscalls — no reader ever observes a tree with some files updated and
# others still missing.
_atomic_sync_dir() {
    local src="$1" dst="$2" label="$3" prune="${4:-prune}"
    local staging="${dst}.sync-new.$$"
    local old="${dst}.sync-old.$$"
    local lock="${dst}.sync.lock"
    # A SIBLING of $dst, like $staging/$old above — never inside $staging
    # itself. $staging IS the tree being published: a legitimate source file
    # or directory literally named the same as a listing (e.g. a plugin
    # shipping its own ".find-files") would collide with it there, either
    # losing real source content to a `find` listing overwriting it or, on
    # Windows, hard-failing outright (NTFS generally refuses to
    # overwrite/replace a file another handle still has open for reading —
    # Tier-3 review, PR #796 round 20). Reused sequentially across this one
    # invocation's several enumerations, never concurrently, so one path
    # suffices; swept below alongside $staging/$old/$lock's own leftovers.
    local findlist="${dst}.find-list.$$"

    # A first-ever sync to a not-yet-existing target (e.g. a brand new cache
    # root, or a plugin mirror directory before its first copy) has no parent
    # directory yet. The lock below is a SIBLING of $dst, so `mkdir "$lock"`
    # needs that parent to already exist; without this it exits under
    # `set -e` before ever reaching the `mkdir -p "$staging"` that would
    # otherwise have created the whole tree (Tier-3 review, PR #796 round 4).
    mkdir -p "$(dirname "$dst")"

    # Serialize concurrent syncs of the SAME $dst (Tier-3 review, PR #796):
    # without this, two runs race the final mv-swap below and can interleave
    # it, and the leftover sweep just below could delete an ACTIVE run's own
    # staging/old dirs, not just a dead one's. `mkdir "$lock"` is the ONLY
    # claim step here (no separate "build under a private name, then mv -T
    # into place" — an earlier revision used that for the same reason `-T`
    # exists: GNU `mv` treats an existing directory target as "move INTO it"
    # rather than "replace it", and `-T` disables that. But `-T` is a GNU
    # extension BSD's (macOS) `mv` lacks, so every lock attempt failed there
    # and every sync timed out — round 6 of this review; `mkdir` alone needs
    # no flags on any platform, though it re-opens the exact window `mv -T`
    # closed: the lock exists but its PID isn't written yet. Rather than
    # papering over that with another rename trick, an UNREADABLE pid below
    # is treated as "still being installed", never as stale — only a pid that
    # reads back as a genuinely dead process is ever reclaimed. `ln -s`,
    # which would sidestep the window entirely (its target string IS the
    # payload, set atomically at creation), was tried and rejected: it fails
    # outright without admin/Developer Mode on Windows, which end-users on
    # this very toolchain are known to run without (see the existing
    # symlink-then-copy-fallback a few dozen lines below).
    # `_CURRENT_SYNC_LOCK` is set the instant `mkdir` succeeds, not after the
    # PID write just below — if THIS process dies (errexit, Ctrl-C) in that
    # gap, the script-wide EXIT trap still owns cleanup and removes it, so no
    # future run ever sees an empty-PID lock from a trappable exit at all
    # (Tier-3 review, PR #796 round 7). That trap can't fire on an
    # untrappable kill (SIGKILL, OOM), though, so an empty PID that persists
    # past a bounded grace period — `_EMPTY_LOCK_GRACE_S` retries, not the
    # dead-PID path above since there IS no PID to check liveness of — is
    # reclaimed the same atomic way: a legitimate installer's `echo` follows
    # its `mkdir` by microseconds, so seconds of silence is already a strong
    # dead-installer signal, not a slow one.
    local _EMPTY_LOCK_GRACE_S=5
    local waited=0 holder_pid="" holder_token="" empty_pid_waits=0 _lock_foreign_entry
    while true; do
        if mkdir "$lock" 2>/dev/null; then
            _CURRENT_SYNC_LOCK="$lock"
            if (set -C; echo "$$" > "$lock/pid") 2>/dev/null \
                && (set -C; _new_claim_token > "$lock/token") 2>/dev/null; then
                break
            fi
            # Lost the race: this process was merely PAUSED (OS scheduling
            # under load, not a crash) between claiming the empty "$lock"
            # directory above and writing its own pid. In that gap, another
            # contender's grace-period reclamation (`_EMPTY_LOCK_GRACE_S`
            # below) can come and go, replacing "$lock" with its own live
            # claim before this process resumes — a plain `echo ... >
            # "$lock/pid"` would then silently overwrite that live claim's
            # pid with this process's own, letting BOTH processes believe
            # they hold the lock and sync the same $dst concurrently
            # (Tier-3 review, PR #796 round 12). `set -C` (noclobber) turns
            # the write itself into the ownership check: it is a shell
            # BUILTIN redirection, not an external tool, so it is exactly as
            # portable across GNU/BSD/Windows Git Bash as `mkdir` itself, and
            # it fails atomically if "$lock/pid" already exists — which it
            # never could at this point unless a replacement claim beat us
            # to it.
            #
            # The PID write can also succeed and the TOKEN write still fail
            # — the earlier reasoning that a non-empty "$lock/pid" makes
            # "$lock" un-reclaimable does not hold: a THIRD process can have
            # already read this same "$lock"'s pid as EMPTY (before our
            # write landed), reached its own grace-period reclaim, and
            # completed `mv "$lock" "$discard"` — stealing the whole
            # directory, pid file and all — before our own token write runs.
            # Finding our now-nonempty pid a mismatch against what it
            # originally observed, that reclaimer treats it as a live claim
            # worth protecting and RESTORES it via a fresh `mkdir "$lock"`,
            # which can already carry an (empty) token file by the time our
            # own noclobber token write reaches it — failing it, even though
            # our pid write genuinely succeeded (Tier-3 review, PR #796
            # round 24). Whichever write failed, "$lock" (whatever directory
            # instance it currently names) is safe to clean up if and only
            # if it is still stamped with OUR OWN pid — the same guarded
            # check the normal release site and the EXIT trap already use,
            # never a bare `rm -rf "$lock"` by name alone. If it is not ours
            # (the original pid-write-failure case above), there is nothing
            # of ours to release. Cleaning up promptly here, rather than
            # abandoning it, is what lets our own very next `mkdir "$lock"`
            # attempt below succeed immediately instead of every future
            # claimant — including this same process's own retry — reading
            # a live-looking pid and waiting out the full 120s timeout for
            # nothing.
            if _lock_is_owned_by "$lock" "$$"; then
                rm -rf "$lock" 2>/dev/null || true
            fi
            _CURRENT_SYNC_LOCK=""
            continue
        fi
        # `mkdir "$lock"` also fails when "$lock" exists but is NOT a
        # directory (a foreign plain file happening to sit at this sibling
        # path). Without this check, `cat "$lock/pid"`/`"$lock/token"` both
        # silently fail on a non-directory path and read back as empty —
        # indistinguishable from a legitimate installer's pid-write gap — so
        # after the grace period below the empty-pid reclaim path would `mv`
        # that foreign file to "$discard", re-read it (also empty, so
        # "matching"), and `rm -rf` it outright: deleting an unrelated file
        # that was never a lock at all (Tier-3 review, PR #796 round 23,
        # data-loss finding). Abort instead of guessing what it is or how it
        # got there.
        if [ -e "$lock" ] && [ ! -d "$lock" ]; then
            echo "  [!!] ${label}: \"$lock\" exists but is not a directory — refusing to treat a foreign file as a stale lock" >&2
            return 1
        fi
        # An unrelated DIRECTORY happening to occupy this exact sibling path
        # is just as foreign as an unrelated file (the check above), and a
        # bare "is it a directory" test cannot tell them apart: a legitimate
        # lock this script created is always empty or contains only "pid"
        # and/or "token" plain files, nothing else. Without this, a foreign
        # directory with no readable pid (no pid file at all, or one holding
        # unrelated content) reads exactly like a real installer's pid-write
        # gap, proceeds through the same empty-pid grace-period reclaim, and
        # ends in `rm -rf "$discard"` — destroying whatever that directory
        # actually held (Tier-3 review, PR #796 round 25, data-loss
        # finding). Reject anything with an unexpected entry the same way
        # the non-directory case above does, rather than trying to recover
        # arbitrary foreign content into our own lock shape.
        if [ -d "$lock" ]; then
            _lock_foreign_entry=$(find "$lock" -mindepth 1 -maxdepth 1 \( ! -type f -o \( ! -name pid ! -name token \) \) 2>/dev/null | head -1)
            if [ -n "$_lock_foreign_entry" ]; then
                echo "  [!!] ${label}: \"$lock\" exists but does not look like a lock this script created (unexpected entry: $_lock_foreign_entry) — refusing to treat it as reclaimable" >&2
                return 1
            fi
        fi
        holder_pid=$(cat "$lock/pid" 2>/dev/null || echo "")
        holder_token=$(cat "$lock/token" 2>/dev/null || echo "")
        if [ -n "$holder_pid" ]; then
            empty_pid_waits=0
        else
            empty_pid_waits=$((empty_pid_waits + 1))
        fi
        if { [ -n "$holder_pid" ] && ! _pid_is_alive "$holder_pid"; } \
            || [ "$empty_pid_waits" -ge "$_EMPTY_LOCK_GRACE_S" ]; then
            # Two contenders can both decide the same lock is reclaimable
            # here. A bare `rm -rf "$lock"` deletes by name only — if the
            # other contender wins the race, installs its own live lock, and
            # THIS process's rm then runs, it deletes that live lock out from
            # under a process that still believes it holds it (Tier-3
            # review, PR #796 round 3). `mv "$lock" "$discard"` claims
            # WHATEVER currently sits at "$lock" atomically — but that is not
            # necessarily the stale instance just read above: another
            # reclaimer can remove it and a genuinely fresh, live lock can
            # install at the same path in the gap between that read and this
            # mv, and this mv would then silently steal ITS lock instead
            # (Tier-3 review, PR #796 round 8 — an ABA race: the path is
            # occupied at claim time, but not necessarily by what was
            # observed). Re-reading the claimed instance's own pid and
            # comparing it to what was just read closes the common case: an
            # unchanged pid confirms the same instance, safe to discard; a
            # changed one means a live replacement was grabbed by mistake,
            # so it is put back for its rightful owner instead of deleted.
            # The pid alone is not a unique instance identity, though — the
            # OS recycles pid numbers, so a genuinely different live
            # replacement can coincidentally carry the SAME pid the stale
            # instance had, matching on pid alone and getting deleted as if
            # it were the same stale claim (Tier-3 review, PR #796 round 15).
            # The high-entropy token paired with every pid write closes that:
            # requiring BOTH to match makes an accidental collision on pid
            # alone no longer enough to call it "the same instance".
            # $discard must be a fresh path every time it is computed, not
            # merely distinct within THIS process's own reclaim attempts:
            # round 13 deliberately leaves $discard behind when a restore
            # fails (see the comment past this whole `if`), and a leftover
            # from a LONG-DEAD prior run can persist past the leftover sweep
            # below if that sweep's own pid-liveness check is fooled the
            # same way round 15 closed above — pid reuse. A later, unrelated
            # process assigned that exact recycled pid would then compute
            # the SAME name an earlier round's sequence-number-based scheme
            # (round 14) always started from "1" for, and a bare (non `-T`)
            # `mv "$lock" "$discard"` onto an existing directory target
            # moves the source INSIDE it instead of failing (the round-11
            # nesting gotcha yet again) — so this process could then inspect
            # or delete that old leftover's content instead of the lock it
            # just claimed (Tier-3 review, PR #796 round 16). Folding a
            # random per-attempt token into the name (the SAME
            # `_new_claim_token` used for the lock's own identity, round 15)
            # replaces the predictable sequence number, and checking the
            # candidate is genuinely free before committing to it — retrying
            # with a fresh token on the vanishingly unlikely collision rather
            # than trusting a single random draw — is the "ensure absent,
            # retry on collision" half of that same review. The token sits
            # BEFORE "$$", not after: the leftover sweep below
            # (`_leftover_pid_is_alive "${leftover##*.}"`) reads the PID from
            # the LAST dot-segment of every "*.sync.lock.*" path, and that
            # must keep meaning "$$", never the token.
            local discard="" _discard_try _discard_candidate
            for _discard_try in 1 2 3 4 5; do
                _discard_candidate="${lock}.stale.$(_new_claim_token).$$"
                if [ ! -e "$_discard_candidate" ]; then
                    discard="$_discard_candidate"
                    break
                fi
            done
            if [ -z "$discard" ]; then
                # Every candidate in a row was already taken (in practice:
                # never) — treat it the same as losing the reclaim race
                # outright rather than force a claim onto an occupied name.
                empty_pid_waits=0
                continue
            fi
            if mv "$lock" "$discard" 2>/dev/null; then
                local claimed_pid claimed_token
                claimed_pid=$(cat "$discard/pid" 2>/dev/null || echo "")
                claimed_token=$(cat "$discard/token" 2>/dev/null || echo "")
                if [ "$claimed_pid" = "$holder_pid" ] && [ "$claimed_token" = "$holder_token" ]; then
                    rm -rf "$discard" 2>/dev/null || true
                elif mkdir "$lock" 2>/dev/null; then
                    # Restoring via a fresh `mkdir` claim, never a
                    # directory-to-directory `mv "$discard" "$lock"` — that
                    # does NOT reliably fail when "$lock" already exists
                    # again (a genuinely different process re-claimed it in
                    # the gap between our own claiming mv above and this
                    # restore): a plain (non `-T`) `mv` onto an existing
                    # directory target MOVES the source INSIDE it instead of
                    # failing, nesting the mismatched claim under the new
                    # live lock rather than restoring it to the top level —
                    # exactly the "move into an existing directory" gotcha
                    # `-T` exists for, and `-T` is the GNU-only flag round 6
                    # already rejected for breaking every lock attempt on
                    # BSD (Tier-3 review, PR #796 round 11). `mkdir "$lock"`
                    # gives the same all-or-nothing signal portably: it
                    # fails if and only if something already occupies
                    # "$lock" again, with no directory-nesting side effect
                    # either way. Only the pid FILE is moved (not the whole
                    # $discard directory) since a plain-file `mv` onto a
                    # path that does not yet exist has no such ambiguity.
                    # `set -C` (noclobber), not a plain `mv`/`>`: this
                    # `mkdir` reopens the SAME empty-window race the initial
                    # claim above closes — if THIS restore is itself paused
                    # between its own `mkdir "$lock"` and this write, a
                    # further reclaimer can replace "$lock" again in the
                    # gap, and an unconditional overwrite would silently
                    # clobber ITS pid too (Tier-3 review, PR #796 round 12).
                    # A failed write here means this restore attempt itself
                    # lost the race; the freshly mkdir'd "$lock" is
                    # therefore no longer ours to populate, but it is also
                    # not safe to delete (round 9) since ownership can no
                    # longer be confirmed either way — leave it exactly as
                    # noclobber left it. $discard is only cleaned up once
                    # its content has actually been preserved into "$lock"
                    # below (see the round-13 comment past this whole `if`
                    # for why an unconditional cleanup here is unsafe). The
                    # token is restored the same noclobber way right after
                    # the pid (round 15): once the pid write above succeeds,
                    # this restore is provably alive and non-empty, so
                    # nobody else can replace "$lock" before the token write
                    # runs — a failure here can only mean the pid write
                    # itself lost the race, same as before.
                    if (set -C; cat "$discard/pid" > "$lock/pid") 2>/dev/null \
                        && (set -C; cat "$discard/token" > "$lock/token") 2>/dev/null; then
                        rmdir "$discard" 2>/dev/null || rm -rf "$discard" 2>/dev/null || true
                    fi
                fi
            fi
            # No unconditional `else`/cleanup of $discard beyond the two
            # success paths above: if "$lock" is occupied again by the time
            # this restore's own `mkdir` runs, or a further contender's
            # noclobber write races ahead of ours, $discard may still hold
            # a live replacement lock this process's earlier claiming `mv`
            # accidentally stole from its rightful owner (Tier-3 review,
            # PR #796 round 13). Deleting it in either case would destroy
            # that owner's only remaining trace with no way to recover it.
            # Left in place, it is a path unique to THIS process's own pid
            # ($$), so the leftover sweep a few lines below (matching
            # "${dst}".sync.lock.*) reaps it automatically once THIS
            # process — never the stolen claim's own owner — is confirmed
            # dead, not sooner.
            empty_pid_waits=0
            continue
        fi
        if [ "$waited" -ge 120 ]; then
            echo "  [!!] ${label}: timed out waiting for pid ${holder_pid:-unknown} to finish syncing $dst" >&2
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done

    # An interrupted swap (crash between the two `mv`s below) can leave $dst
    # MISSING with its only backup sitting in a dead process's $old — recover
    # it before the sweep just below would otherwise discard the last copy of
    # the previous destination outright (Tier-3 review, PR #796 round 2).
    #
    # Recover unconditionally, WITHOUT gating on whether the orphan's PID
    # suffix is currently alive (Tier-3 review, PR #796 round 26, data-loss
    # finding): ".sync-old.*" is only ever created by the swap further below,
    # which itself only ever runs while holding "$lock" for this exact $dst.
    # By the time we reach here we already hold that same lock, so no other
    # process can be a legitimate CONCURRENT owner of this $dst's
    # ".sync-old.*" right now — regardless of whether its PID suffix happens
    # to have been reused by some unrelated, currently-alive process
    # elsewhere on the system. A PID-liveness check here reads that
    # coincidence as "still owned", skips the recovery, and silently drops
    # noprune's mirror-owned content from that backup when $dst is
    # republished from $src alone. Holding "$lock" is the ownership identity
    # PID reuse cannot confuse; a raw pid check on the orphan's name is not.
    if [ ! -d "$dst" ]; then
        for orphan in "${dst}".sync-old.*; do
            [ -d "$orphan" ] || continue
            mv "$orphan" "$dst"
            break
        done
    fi

    # A prior run killed mid-swap (Ctrl-C, timeout) leaves its own PID-named
    # staging/old dirs, an abandoned stale-lock claim (died between the
    # claiming `mv` and its `rm -rf`), or an un-removed enumeration listing
    # (died between `_find0_to_file` writing it and this function's own
    # `rm -f` right after reading it, round 20) behind forever — nothing else
    # ever matches that PID again to clean them up. `.sync.lock.*` catches
    # the stale-lock case — the bare "$lock" itself has no trailing PID
    # suffix, so this glob can never match a currently-installed live lock.
    # Self-heal by sweeping DEAD-process leftovers for this $dst before
    # starting a fresh one; the lock above already rules out a live
    # concurrent holder, but a name-only match here would still be blind to
    # that distinction on its own.
    for leftover in "${dst}".sync-new.* "${dst}".sync-old.* "${dst}".sync.lock.* "${dst}".find-list.*; do
        [ -e "$leftover" ] || continue
        if ! _leftover_pid_is_alive "${leftover##*.}"; then
            rm -rf "$leftover" 2>/dev/null || true
        fi
    done
    rm -rf "$staging"
    mkdir -p "$staging"

    # Pre-create the directory skeleton from $src's own tree in ONE pass,
    # instead of a per-file `mkdir -p "$(dirname "$target")"` — that idiom
    # forks a subshell for the `$(...)`, an external `dirname`, AND `mkdir`,
    # i.e. up to 3 process spawns PER FILE. Over shared/'s ~1800 files that
    # measured as the dominant cost of a 180+ second hang on Windows Git
    # Bash, where each spawn is a full CreateProcess call. `${dir#$src/}` is
    # a bash builtin substitution — no subprocess at all.
    # Exclusions must match the file-copy loop below EXACTLY (`-name` for the
    # dir itself, `-path .../name/*` for anything nested under it) — a looser
    # pattern here (e.g. `*/.git*` without the trailing slash) also matches
    # unrelated names like `.github`, leaving a directory the file loop still
    # expects to exist uncreated (`cp: ... No such file or directory`).
    # `-mindepth 1` excludes $src itself: `find` always yields the search root
    # first, and `${dir#$src/}` (no trailing slash on $src to match against)
    # leaves THAT one entry unstripped, mkdir'ing the whole absolute source
    # path as a bogus nested directory inside staging every run (Tier-3
    # review, PR #796 round 2).
    _find0_to_file "$findlist" "directories under $src" "$src" -mindepth 1 -type d \
        -not -name "__pycache__" -not -path "*/__pycache__/*" \
        -not -name ".venv" -not -path "*/.venv/*" \
        -not -name ".pytest_cache" -not -path "*/.pytest_cache/*" \
        -not -name ".git" -not -path "*/.git/*" || return 1
    while IFS= read -r -d '' dir; do
        mkdir -p "$staging/${dir#$src/}"
    done < "$findlist"
    rm -f "$findlist"

    # __pycache__/.venv/.pytest_cache: bulk `cp -r` per matched top-level dir
    # (found via `-prune`, so a nested one under `.venv` isn't independently
    # matched and double-copied) — these can be tens of thousands of tiny
    # files, far too slow to copy one at a time on Windows.
    if [ -d "$dst" ]; then
        _find0_to_file "$findlist" "cache directories under $dst" "$dst" \
            \( -name "__pycache__" -o -name ".venv" -o -name ".pytest_cache" \) -prune || return 1
        while IFS= read -r -d '' cache_dir; do
            local rel="${cache_dir#$dst/}"
            mkdir -p "$(dirname "$staging/$rel")"
            cp -r "$cache_dir" "$staging/$rel"
        done < "$findlist"
        rm -f "$findlist"
    fi

    # Single pass over $src, comparing each file directly against the LIVE
    # $dst — NOT a staging seed copied in first. An earlier revision seeded
    # every existing file into staging, then diffed $src against that seed
    # here: a full second copy-and-compare pass over the entire tree, for
    # nothing, on top of the per-file mkdir cost above. Unchanged files are
    # linked (not copied) from $dst: content is already verified identical,
    # so `cp -l` skips the read+write I/O and just adds a directory entry.
    local added=0 changed=0 removed=0
    _find0_to_file "$findlist" "files under $src" "$src" -type f \
        -not -path "*/__pycache__/*" \
        -not -path "*/.venv/*" \
        -not -path "*/.pytest_cache/*" \
        -not -path "*/.git/*" \
        -not -name "*.pyc" \
        -not -name ".python-version" || return 1
    while IFS= read -r -d '' file; do
        local rel_path="${file#$src/}"
        local target_file="$staging/$rel_path"
        local dst_file="$dst/$rel_path"

        if [ ! -f "$dst_file" ]; then
            cp "$file" "$target_file"
            ((added++)) || true
        elif ! diff -q --strip-trailing-cr "$file" "$dst_file" > /dev/null 2>&1; then
            cp "$file" "$target_file"
            ((changed++)) || true
        else
            cp -l "$dst_file" "$target_file" 2>/dev/null || cp "$dst_file" "$target_file"
        fi
    done < "$findlist"
    rm -f "$findlist"

    # Files present in the old target but absent from $src (renamed/deleted
    # upstream) were never copied into staging above, so nothing needs
    # deleting here — this just counts them for the summary line ($prune=prune
    # only; excluded-by-name files like .python-version are CORRECTLY dropped
    # here too, per the "must not be distributed" contract the exclusion list
    # exists for). For $prune=noprune (the Windows real-dir plugin mirror,
    # which must preserve EVERY mirror-owned file the old pure-copy behavior
    # always kept), the check is against $staging, not $src: a file can exist
    # in $src yet still be missing from staging because the copy loop's own
    # name filters (.python-version, *.pyc) excluded it — checking $src alone
    # wrongly treated "present in source" as "already handled" and silently
    # dropped such files even though noprune's contract has no distribution
    # policy to justify that (Tier-3 review, PR #796 round 3).
    if [ -d "$dst" ]; then
        _find0_to_file "$findlist" "files under $dst" "$dst" -type f \
            -not -path "*/__pycache__/*" \
            -not -path "*/.venv/*" \
            -not -path "*/.pytest_cache/*" || return 1
        while IFS= read -r -d '' dst_file; do
            local rel="${dst_file#$dst/}"
            if [ "$prune" = "prune" ]; then
                if [ ! -f "$src/$rel" ]; then
                    ((removed++)) || true
                fi
            elif [ ! -f "$staging/$rel" ]; then
                local target="$staging/$rel"
                mkdir -p "$(dirname "$target")"
                cp "$dst_file" "$target"
            fi
        done < "$findlist"
        rm -f "$findlist"
    fi

    # These two `mv`s are the swap itself, and "$dst" genuinely does not
    # exist on any path between them — no single rename() can atomically
    # replace a NON-EMPTY directory (this is a kernel-level constraint, not
    # a shell one), so a plain-directory publish is structurally a two-step
    # rename no matter how it is written. The only way to close that gap
    # entirely is symlink indirection (publish by atomically repointing a
    # stable symlink at a new, versioned target) — already tried and
    # rejected earlier in this review (round 6): `ln -s` fails outright
    # without admin/Developer Mode on Windows, which this tool's own
    # end-users are known to run without, so it cannot be the general
    # mechanism here (Tier-3 review, PR #796 round 18).
    # Accepted as a documented, bounded risk rather than fixed: the window
    # is two back-to-back renames with no I/O or computation between them
    # (microseconds, at most low milliseconds for the `mv` process spawns on
    # Windows), and this script itself only runs when a developer manually
    # triggers a sync — not on every session. A reader would have to import
    # from "$dst" in that exact instant. Every current reader under
    # shared/scripts/hooks/ is a best-effort Stop/SessionStart hook bound by
    # this project's own "never blocks, always exits 0" contract (ADR-042):
    # a transient miss surfaces at worst as one hook's traceback on stderr,
    # self-heals on the very next hook invocation seconds later, and leaves
    # no corrupted or lost state — the interrupted-swap recovery a few dozen
    # lines above this function already handles the strictly worse case (a
    # crash mid-swap, not just a reader glancing at the wrong instant).
    # `generate_handoff_on_stop.py`'s `_import_lib_with_retry` is the pattern
    # to copy for any NEW reader that is provably exposed to this window
    # more than incidentally — not something to retrofit into every reader
    # pre-emptively for a race this narrow.
    rm -rf "$old" 2>/dev/null || true
    if [ -d "$dst" ]; then
        mv "$dst" "$old"
    fi
    mv "$staging" "$dst"
    rm -rf "$old" 2>/dev/null || true

    # `_lock_is_owned_by` guard: see its own comment near the top of this
    # file for why a bare `rm -rf "$lock"` here is unsafe. `|| true`: under
    # `set -e`, an unguarded `&&` chain used as a standalone statement (not
    # an `if` condition) aborts the whole script the moment the ownership
    # check itself returns false — which is the expected, non-error outcome
    # in the rare race this guards against, not a failure to propagate.
    _lock_is_owned_by "$lock" "$$" && rm -rf "$lock" 2>/dev/null || true
    _CURRENT_SYNC_LOCK=""

    if [ "$changed" -gt 0 ] || [ "$added" -gt 0 ] || [ "$removed" -gt 0 ]; then
        echo "  [OK] ${label}: ${added} added, ${changed} updated, ${removed} removed"
    else
        echo "  [OK] ${label}: up to date"
    fi
}

# Resolve a plugin's installed cache path from installed_plugins.json (empty
# when the plugin is not installed). Single source of truth for the three
# lookups below. Uses $PYTHON_BIN (never a bare `python` — F37).
_install_path() {
    "$PYTHON_BIN" -c "
import json, sys, os
try:
    ip = os.path.expanduser('~/.claude/plugins/installed_plugins.json')
    data = json.load(open(ip))
    entries = data.get('plugins', {}).get(sys.argv[1], [])
    print(entries[0]['installPath'].replace(chr(92), '/') if entries else '')
except Exception:
    print('')
" "$1" 2>/dev/null
}

# Step 1: Update marketplace clone from GitHub
# Try the built-in command first; fall back to manual git pull if SSH fails
echo ""
echo "Fetching latest from GitHub..."
if claude plugin marketplace update "$MARKETPLACE_NAME" 2>/dev/null; then
    echo "[OK] Marketplace synced via CLI"
else
    echo "[!!] CLI marketplace update failed (likely SSH issue), using git pull fallback..."
    if [ -d "$MARKETPLACE_DIR/.git" ]; then
        # Ensure remote uses HTTPS (not SSH)
        git -C "$MARKETPLACE_DIR" remote set-url origin "$HTTPS_URL" 2>/dev/null || true
        git -C "$MARKETPLACE_DIR" fetch origin main
        git -C "$MARKETPLACE_DIR" reset --hard origin/main
    else
        git clone "$HTTPS_URL" "$MARKETPLACE_DIR"
    fi
    echo "[OK] Marketplace synced via git"
fi

# Verify the clone actually reached origin/main's true tip. The CLI path
# above can exit 0 without a guaranteed fresh fetch (its internal update
# mechanism is opaque to this script) — trusting that blindly let a file that
# "landed on main just ahead of the sync run" go missing from the cache
# after a reported-successful sync, because Steps 2-3 below copy whatever is
# in $MARKETPLACE_DIR without ever checking it against the real remote.
# Cross-check regardless of which branch above ran, and force a hard sync
# when the clone lags, BEFORE any file is copied.
if [ -d "$MARKETPLACE_DIR/.git" ]; then
    # `|| true` on each: under `set -euo pipefail` an offline `ls-remote` (or a
    # `rev-parse` on a corrupt clone) would otherwise abort the whole sync here
    # instead of degrading to "skip this check" like every other advisory probe
    # in this script.
    remote_head=$( (git ls-remote "$HTTPS_URL" refs/heads/main 2>/dev/null | cut -f1) || true)
    local_head=$(git -C "$MARKETPLACE_DIR" rev-parse HEAD 2>/dev/null || echo "")
    if [ -n "$remote_head" ] && [ "$remote_head" != "$local_head" ]; then
        echo "[!!] Marketplace clone lagging origin/main (${local_head:-none} != $remote_head), forcing hard sync..."
        git -C "$MARKETPLACE_DIR" remote set-url origin "$HTTPS_URL" 2>/dev/null || true
        git -C "$MARKETPLACE_DIR" fetch origin main
        git -C "$MARKETPLACE_DIR" reset --hard origin/main
    fi
fi

# Step 2: Full file sync from marketplace into installed plugin caches
# Reads the installed cache path from installed_plugins.json so we always
# write to the correct version directory (e.g. 0.2.0), not whatever version
# is in the source plugin.json.
echo ""
echo "Full sync: marketplace → plugin caches..."

installed=0
synced=0
skipped=0
errors=0

for plugin in "${PLUGINS[@]}"; do
    src_dir="$MARKETPLACE_DIR/plugins/$plugin"
    plugin_key="${plugin}@${MARKETPLACE_NAME}"

    # Check if plugin source exists in marketplace
    if [ ! -d "$src_dir" ]; then
        echo "  [!!] ${plugin}: source not found in marketplace, skipping"
        ((errors++)) || true
        continue
    fi

    # Resolve the installed cache path; INSTALL the plugin first when it is
    # registered in the marketplace but not yet installed, so this script brings
    # EVERY registered plugin into the cache instead of silently skipping a
    # not-yet-installed one (the opt-in shipwright-grade lead magnet was left
    # `not_in_cache` forever otherwise). Install is non-fatal under `set -e`: an
    # offline / headless run that can't install just skips that plugin.
    cache_target=$(_install_path "$plugin_key")

    if [ -z "$cache_target" ] || [ ! -d "$cache_target" ]; then
        echo "  [..] ${plugin}: not installed — installing from marketplace..."
        if claude plugin install "$plugin_key" >/dev/null 2>&1; then
            cache_target=$(_install_path "$plugin_key")
            ((installed++)) || true
        fi
    fi

    if [ -z "$cache_target" ] || [ ! -d "$cache_target" ]; then
        echo "  [--] ${plugin}: install unavailable (offline/CLI), skipping"
        ((skipped++)) || true
        continue
    fi

    # `.python-version` is EXCLUDED on purpose (iterate-2026-08-01-pin-python-311).
    # Each plugin dir carries one so a contributor's `cd plugins/x && uv run pytest
    # tests/` uses the 3.11 this repo's CI judges pushes with. That is a MONOREPO
    # fact. Shipping it would make it an END-USER one: skills invoke `uv run --project
    # {plugin_root}` (shipwright-plan/skills/plan/SKILL.md, 5 sites), and uv honours a
    # version file in the --project dir - measured, 3.12.13 -> 3.11.15. Consumers
    # declare `>=3.11` and must keep resolving whatever satisfies that; forcing an
    # interpreter download on them, or failing where downloads are blocked, is not
    # this repo's call to make. (Enforced inside `_atomic_sync_dir`'s find call.)
    _atomic_sync_dir "$src_dir" "$cache_target" "$plugin"
    ((synced++)) || true
done

# Step 3: Sync shared/ directory into cache root
# Plugins reference {plugin_root}/../../shared/ which resolves to cache/shipwright/shared/
# Without this, all finalization scripts (record_event, artifact_sync, etc.) are unreachable.
echo ""
echo "Syncing shared/ directory..."
SHARED_SRC="$MARKETPLACE_DIR/shared"
SHARED_TARGET="$HOME/.claude/plugins/cache/shipwright/shared"

if [ -d "$SHARED_SRC" ]; then
    _atomic_sync_dir "$SHARED_SRC" "$SHARED_TARGET" "shared"
else
    echo "  [!!] shared/ not found in marketplace"
fi

# Step 4: Create plugins/ directory with symlinks for cross-plugin references
# Several plugins reference siblings via {plugin_root}/../../plugins/shipwright-run/
# In the cache, plugins live at cache/shipwright/shipwright-run/0.2.0/ (flat, no plugins/ subdir).
# We create cache/shipwright/plugins/shipwright-X -> ../shipwright-X/<version>/ symlinks
# so that ../../plugins/shipwright-run resolves correctly.
echo ""
echo "Creating cross-plugin symlinks..."
PLUGINS_LINK_DIR="$HOME/.claude/plugins/cache/shipwright/plugins"
mkdir -p "$PLUGINS_LINK_DIR"

links_created=0
links_updated=0
dirs_synced=0

# Helper: atomic copy from $1 to $2, preserving directory structure.
# Used when $link_path exists as a real directory (e.g. Windows where ln -s
# silently degrades to copy/junction, or end-users on older script versions
# that mirrored via copy). Without this, runtime resolves stale code.
sync_dir_from_to() {
    _atomic_sync_dir "$1" "$2" "$(basename "$2")" noprune >/dev/null
}

for plugin in "${PLUGINS[@]}"; do
    plugin_key="${plugin}@${MARKETPLACE_NAME}"

    # Get the installed cache path (Step 2 installed any missing ones already).
    cache_target=$(_install_path "$plugin_key")

    if [ -z "$cache_target" ] || [ ! -d "$cache_target" ]; then
        continue
    fi

    link_path="$PLUGINS_LINK_DIR/$plugin"

    # Three cases: existing symlink (re-point if wrong), existing real dir
    # (file-copy fallback), or missing (try symlink, fall back to copy).
    if [ -L "$link_path" ]; then
        current_target=$(readlink "$link_path")
        if [ "$current_target" != "$cache_target" ]; then
            rm "$link_path"
            ln -s "$cache_target" "$link_path"
            ((links_updated++)) || true
        fi
    elif [ -d "$link_path" ]; then
        # Real directory (Windows or legacy install) — file-copy sync.
        sync_dir_from_to "$cache_target" "$link_path"
        ((dirs_synced++)) || true
    elif [ ! -e "$link_path" ]; then
        if ln -s "$cache_target" "$link_path" 2>/dev/null; then
            ((links_created++)) || true
        else
            # Symlink creation failed (likely Windows non-admin) — copy instead.
            sync_dir_from_to "$cache_target" "$link_path"
            ((dirs_synced++)) || true
        fi
    fi
done

if [ "$links_created" -gt 0 ] || [ "$links_updated" -gt 0 ] || [ "$dirs_synced" -gt 0 ]; then
    echo "  [OK] ${links_created} symlinks created, ${links_updated} updated, ${dirs_synced} dirs file-synced"
else
    echo "  [OK] all plugin mirrors up to date"
fi

# Clean up stale version dirs (e.g. 0.0.0 from failed syncs)
echo ""
echo "Cleaning stale cache directories..."
cleaned=0
for plugin in "${PLUGINS[@]}"; do
    plugin_key="${plugin}@${MARKETPLACE_NAME}"
    cache_base="$HOME/.claude/plugins/cache/shipwright/$plugin"

    if [ ! -d "$cache_base" ]; then
        continue
    fi

    # Get installed version
    installed_version=$("$PYTHON_BIN" -c "
import json, sys, os
try:
    ip = os.path.expanduser('~/.claude/plugins/installed_plugins.json')
    data = json.load(open(ip))
    key = sys.argv[1]
    entries = data.get('plugins', {}).get(key, [])
    print(entries[0]['version'] if entries else '')
except Exception:
    print('')
" "$plugin_key" 2>/dev/null)

    if [ -z "$installed_version" ]; then
        continue
    fi

    # Remove version dirs that aren't the installed version
    for version_dir in "$cache_base"/*/; do
        version_name="$(basename "$version_dir")"
        if [ "$version_name" != "$installed_version" ]; then
            rm -rf "$version_dir"
            echo "  Removed stale: ${plugin}/${version_name}"
            ((cleaned++)) || true
        fi
    done
done

if [ "$cleaned" -eq 0 ]; then
    echo "  No stale directories found"
fi

echo ""
echo "=== Done. ${installed} installed, ${synced} synced, ${skipped} skipped, ${errors} errors ==="
echo "=== Restart Claude Code session to activate changes ==="

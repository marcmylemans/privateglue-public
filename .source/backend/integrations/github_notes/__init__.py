"""GitHub notes sync: keep PrivateGlue's markdown notes in a GitHub repository.

One direction per run, chosen in the settings:

* push: PrivateGlue to GitHub. Changed notes go into ONE commit per sync through the Git
  Data API (tree + commit + move the branch). Unchanged notes cost no write because the
  local git blob sha is compared with the sha GitHub lists in the folder's tree.
* pull: GitHub to PrivateGlue. ``.md`` files at the top level of the repo folder are written
  into the notes folder. Only files whose sha differs are downloaded.

Nothing is ever deleted, on either side. There is no two-way merge.

This is the one integration that writes outside PrivateGlue (to the configured repo folder),
and on pull it writes note files, never anything outside the notes folder.
"""
import base64
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from backend.integrations import Field, Integration, IntegrationError, SyncResult
from backend.integrations.http import DEFAULT_TIMEOUT
from backend.routes import notes as notes_routes

# Where notes live. Tests point this at a temporary folder.
NOTES_DIR = notes_routes.NOTES_DIR
META_SUFFIX = ".meta.json"           # tags and device links: "<note>.md.meta.json" next to the note
MAX_FILE_BYTES = 1024 * 1024         # per file, both directions
API_VERSION = "2022-11-28"           # supported on github.com until 2028-03-10 and on GitHub Enterprise Server
DEFAULT_API = "https://api.github.com"
WHAT = "GitHub"

PUSH, PULL = "push", "pull"
_REPO_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*)/[A-Za-z0-9._-]+$")


# --- helpers -------------------------------------------------------------------------------

def git_blob_sha(data):
    """The sha git (and GitHub) gives a file with these bytes: sha1 of "blob <len>\\0<data>"."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _check_note_name(name):
    """Return None when ``name`` is a valid note file name as PrivateGlue itself would save it,
    otherwise a short reason. Uses the same rules as the notes pages."""
    try:
        normalized = notes_routes.normalize_note_filename(name)
    except ValueError as exc:
        return str(exc)
    if normalized != name:
        return f"name is not allowed in PrivateGlue (it would have to be '{normalized}')"
    return None


def _note_path(root, filename):
    """Same check as backend.routes.notes.get_note_path, but with the folder passed in so tests
    can use a temporary folder. Raises ValueError for anything that resolves outside ``root``."""
    resolved = os.path.realpath(os.path.join(root, filename))
    notes_root = os.path.realpath(root)
    if os.path.commonpath([notes_root, resolved]) != notes_root:
        raise ValueError("Invalid note path.")
    return resolved


def _clean_meta(raw):
    """Turn a downloaded .meta.json into exactly what PrivateGlue writes itself
    (see save_metadata in backend/routes/notes.py). Raises ValueError when it is not usable."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("not valid JSON")
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    tags = data.get("tags", [])
    device_ids = data.get("device_ids", [])
    if not isinstance(tags, list) or not isinstance(device_ids, list):
        raise ValueError("tags and device_ids must be lists")
    clean = {
        "tags": [t.strip() for t in tags if isinstance(t, str) and t.strip()],
        "device_ids": [int(d) for d in device_ids
                       if not isinstance(d, bool) and str(d).isdigit()],
    }
    return json.dumps(clean, indent=2).encode("utf-8")


def _write_atomic(path, data):
    """Write via a hidden temp file in the same folder, so a crash never leaves half a note."""
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".pg-sync-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def parse_repo(value):
    """Accept "owner/name" or a GitHub URL; return "owner/name" or raise IntegrationError."""
    repo = (value or "").strip()
    repo = re.sub(r"^https?://[^/]+/", "", repo)
    repo = repo.strip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not _REPO_RE.match(repo):
        raise IntegrationError("Repository must look like owner/name, for example acme/it-notes.")
    return repo


def parse_folder(value):
    """Folder inside the repo, as a list of path parts ([] means the repo root)."""
    parts = [p for p in (value or "").strip().replace("\\", "/").split("/") if p]
    for part in parts:
        if part in (".", "..", ".git"):
            raise IntegrationError("Folder in the repository may not contain '.', '..' or .git parts.")
    return parts


class _Api:
    """Tiny GitHub REST client. Every call has a timeout; errors become IntegrationError
    messages without the token."""

    def __init__(self, config):
        self.base = (config.get("api_url") or DEFAULT_API).strip().rstrip("/")
        if not self.base.startswith(("https://", "http://")):
            raise IntegrationError("API address must start with https://")
        self.repo = parse_repo(config.get("repository"))
        self.verify = config.get("verify_tls", True)
        token = (config.get("access_token") or "").strip()
        if not token:
            raise IntegrationError("Missing settings: Access token")
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "PrivateGlue-notes-sync",
        }

    def call(self, method, path, *, json=None, params=None, allow=()):
        """Return (status, data). Statuses in ``allow`` are returned instead of raised."""
        url = f"{self.base}/repos/{self.repo}{path}"
        try:
            resp = requests.request(method, url, headers=self.headers, json=json, params=params,
                                    verify=self.verify, timeout=DEFAULT_TIMEOUT)
        except requests.exceptions.SSLError:
            raise IntegrationError(
                f"Could not verify the TLS certificate of {WHAT}. Use a trusted certificate "
                "or turn off certificate verification in the settings.")
        except requests.exceptions.ConnectionError:
            raise IntegrationError(f"Could not connect to {WHAT}. Check the API address and that "
                                   "it is reachable from this container.")
        except requests.exceptions.Timeout:
            raise IntegrationError(f"{WHAT} did not answer within {DEFAULT_TIMEOUT} seconds.")
        except requests.exceptions.RequestException as exc:
            raise IntegrationError(f"Request to {WHAT} failed: {type(exc).__name__}")

        status = resp.status_code
        data = None
        if resp.content:
            try:
                data = resp.json()
            except ValueError:
                data = None
        if status < 400 or status in allow:
            if status < 400 and resp.content and data is None:
                raise IntegrationError(f"{WHAT} did not return JSON. Check the API address.")
            return status, data

        self._raise_rate_limit(resp, data)
        if status == 401:
            raise IntegrationError(f"{WHAT} rejected the access token (HTTP 401). "
                                   "It may be wrong, expired or revoked.")
        if status == 403:
            raise IntegrationError(
                f"{WHAT} refused access to {self.repo} (HTTP 403). Check that the token has "
                "access to this repository with Contents permission (read and write for push).")
        if status == 404:
            raise IntegrationError(
                f"{WHAT} answered 404 for {self.repo}. Check the repository name and that the "
                "token has access to this repository.")
        if status == 409:
            raise IntegrationError(f"The repository {self.repo} is empty or not ready yet (HTTP 409).")
        raise IntegrationError(f"{WHAT} answered with an error (HTTP {status}){_gh_message(data)}.")

    @staticmethod
    def _raise_rate_limit(resp, data):
        if resp.status_code not in (403, 429):
            return
        headers = resp.headers or {}
        message = str((data or {}).get("message", "")) if isinstance(data, dict) else ""
        remaining = headers.get("x-ratelimit-remaining")
        retry_after = headers.get("retry-after")
        if remaining == "0":
            when = ""
            try:
                reset = datetime.fromtimestamp(int(headers.get("x-ratelimit-reset")), tz=timezone.utc)
                when = f" Try again after {reset.strftime('%Y-%m-%d %H:%M')} UTC."
            except (TypeError, ValueError):
                pass
            raise IntegrationError(f"{WHAT} rate limit reached (HTTP {resp.status_code}).{when}")
        if retry_after or resp.status_code == 429 or "rate limit" in message.lower():
            wait = f" Try again in {retry_after} seconds." if retry_after and retry_after.isdigit() \
                else " Try again in a few minutes."
            raise IntegrationError(f"{WHAT} secondary rate limit reached (HTTP {resp.status_code}).{wait}")


def _gh_message(data):
    if isinstance(data, dict) and data.get("message"):
        return ": " + str(data["message"])[:200]
    return ""


# --- the integration -----------------------------------------------------------------------

class GitHubNotes(Integration):
    key = "github_notes"
    name = "GitHub notes sync"
    description = ("Keeps your notes as markdown files in a GitHub repository: back them up "
                   "with history (push) or edit them on GitHub (pull).")
    icon = "github"
    docs = "github_notes.md"
    fields = [
        Field("repository", "Repository", required=True, placeholder="owner/name",
              help="The repository as owner/name, for example acme/it-notes."),
        Field("branch", "Branch", default="main", placeholder="main"),
        Field("folder", "Folder in the repository", default="notes", placeholder="notes",
              help="Notes are kept in this folder. Leave empty to use the top of the repository."),
        Field("access_token", "Access token", kind="password", required=True,
              help="Fine-grained personal access token for this one repository with "
                   "Contents: Read and write (Read-only is enough for pull)."),
        Field("direction", "Direction", kind="select", default=PUSH, choices=[
            (PUSH, "Push: PrivateGlue to GitHub (backup and history)"),
            (PULL, "Pull: GitHub to PrivateGlue (GitHub is where you edit)"),
        ], help="One direction only. Nothing is ever deleted on either side."),
        Field("include_meta", "Include tags and device links", kind="checkbox", default=True,
              help="Also sync the small <note>.md.meta.json file PrivateGlue keeps next to each note."),
        Field("api_url", "API address", kind="url", default=DEFAULT_API,
              placeholder=DEFAULT_API,
              help="Change only for GitHub Enterprise Server: https://<your-server>/api/v3"),
        Field("verify_tls", "Verify the TLS certificate", kind="checkbox", default=True),
    ]

    # --- shared ----------------------------------------------------------------------------
    @staticmethod
    def _branch(config):
        branch = (config.get("branch") or "main").strip()
        if not branch or ".." in branch or branch.startswith("/") or any(c in branch for c in " ~^:?*[\\"):
            raise IntegrationError("Branch name is not valid.")
        return branch

    @staticmethod
    def _notes_dir():
        if not os.path.isdir(NOTES_DIR):
            raise IntegrationError(f"The notes folder {NOTES_DIR} does not exist.")
        return NOTES_DIR

    def _head(self, api, branch):
        """Return (commit_sha, root_tree_sha) of the branch, or None for an empty repository.
        Raises IntegrationError when the branch does not exist."""
        status, data = api.call("GET", f"/git/ref/heads/{quote(branch, safe='/')}", allow=(404, 409))
        if status == 409:
            return None
        if status == 404 or not isinstance(data, dict) or data.get("object", {}).get("type") != "commit":
            # Tell "no such branch" apart from "empty repository" (no branches at all). A 404
            # here means the repository itself is not visible to the token.
            status, branches = api.call("GET", "/branches", params={"per_page": 1}, allow=(409,))
            if status == 409 or branches == []:
                return None
            raise IntegrationError(f"Branch '{branch}' does not exist in {api.repo}. Create it on GitHub "
                                   "or change the branch in the settings.")
        commit_sha = data["object"]["sha"]
        _, commit = api.call("GET", f"/git/commits/{commit_sha}")
        try:
            return commit_sha, commit["tree"]["sha"]
        except (TypeError, KeyError):
            raise IntegrationError(f"{WHAT} returned an unexpected answer for commit {commit_sha[:7]}.")

    def _folder_entries(self, api, root_tree, folder_parts, result):
        """{file name: tree entry} at the top of the repo folder, or None when it does not exist.
        Walks one tree level at a time (non-recursive), so large repositories are never listed."""
        tree_sha = root_tree
        for part in folder_parts:
            _, tree = api.call("GET", f"/git/trees/{tree_sha}")
            match = next((e for e in (tree or {}).get("tree", [])
                          if e.get("path") == part and e.get("type") == "tree"), None)
            if match is None:
                return None
            tree_sha = match["sha"]
        _, tree = api.call("GET", f"/git/trees/{tree_sha}")
        if (tree or {}).get("truncated"):
            result.errors.append("GitHub returned an incomplete file list for the folder (too many files); "
                                 "some notes may have been skipped.")
        return {e["path"]: e for e in (tree or {}).get("tree", []) if e.get("path")}

    # --- test ------------------------------------------------------------------------------
    def test(self, config):
        api = _Api(config)
        branch = self._branch(config)
        direction = config.get("direction") or PUSH
        _, repo = api.call("GET", "")
        repo = repo if isinstance(repo, dict) else {}
        head = self._head(api, branch)
        if head is None:
            if direction == PUSH:
                raise IntegrationError(
                    f"Connected to {api.repo}, but the repository is empty. Add a first file on "
                    "GitHub (for example a README) so there is a branch to commit to.")
            return f"Connected to {api.repo}. The repository is empty, so a pull has nothing to import yet."

        message = f"Connected to {repo.get('full_name') or api.repo}, branch '{branch}' found."
        perms = repo.get("permissions")
        if direction == PUSH:
            if isinstance(perms, dict) and perms.get("push") is False:
                raise IntegrationError(message + " Your GitHub account has no write access to this "
                                       "repository, so push cannot work.")
            if isinstance(perms, dict) and perms.get("push"):
                message += (" Your account can write here. The token itself needs Contents: Read and "
                            "write; the first sync confirms that.")
            else:
                message += " Could not read write permissions; the first sync will show if writing works."
        else:
            message += " Pull only needs read access."
        return message

    # --- sync ------------------------------------------------------------------------------
    def sync(self, config):
        api = _Api(config)
        branch = self._branch(config)
        folder = parse_folder(config.get("folder"))
        notes_dir = self._notes_dir()
        include_meta = bool(config.get("include_meta", True))
        if (config.get("direction") or PUSH) == PULL:
            return self._pull(api, branch, folder, notes_dir, include_meta)
        return self._push(api, branch, folder, notes_dir, include_meta)

    def _read_local(self, notes_dir, name, result):
        """Bytes of a local file, or None (with a line in result.errors) when it cannot be used."""
        try:
            path = _note_path(notes_dir, name)
        except ValueError:
            result.errors.append(f"{name}: skipped, path is outside the notes folder")
            return None
        if not os.path.isfile(path):
            return None
        size = os.path.getsize(path)
        if size > MAX_FILE_BYTES:
            result.errors.append(f"{name}: skipped, larger than {MAX_FILE_BYTES // 1024} KB")
            return None
        with open(path, "rb") as f:
            data = f.read()
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            result.errors.append(f"{name}: skipped, not UTF-8 text")
            return None
        return data

    def _push(self, api, branch, folder, notes_dir, include_meta):
        result = SyncResult()
        head = self._head(api, branch)
        if head is None:
            raise IntegrationError(
                f"The repository {api.repo} is empty. Add a first file on GitHub (for example a "
                "README) so there is a branch to commit to, then sync again.")
        commit_sha, root_tree = head
        remote = self._folder_entries(api, root_tree, folder, result) or {}
        prefix = "/".join(folder) + "/" if folder else ""

        changes = []        # tree entries to write
        for name in sorted(os.listdir(notes_dir)):
            if not name.endswith(".md"):
                continue
            problem = _check_note_name(name)
            if problem:
                result.errors.append(f"{name}: skipped, {problem}")
                continue
            files = [name] + ([name + META_SUFFIX] if include_meta else [])
            note_state = None
            for fname in files:
                data = self._read_local(notes_dir, fname, result)
                if data is None:
                    if fname == name:
                        break           # no usable note: skip its metadata too
                    continue
                existing = remote.get(fname)
                if existing and existing.get("type") != "blob":
                    result.errors.append(f"{fname}: skipped, the repository has a folder with this name")
                    if fname == name:
                        break
                    continue
                if existing and existing.get("sha") == git_blob_sha(data):
                    note_state = note_state or "unchanged"
                    continue
                changes.append({"path": prefix + fname, "mode": "100644", "type": "blob",
                                "content": data.decode("utf-8")})
                if fname == name and not existing:
                    note_state = "created"
                elif note_state != "created":
                    note_state = "updated"
            if note_state == "created":
                result.created += 1
            elif note_state == "updated":
                result.updated += 1
            elif note_state == "unchanged":
                result.skipped += 1

        changed = result.created + result.updated
        if not changes:
            result.message = "Nothing to push, GitHub is up to date"
            return result

        # One tree, one commit, one branch move: three writes however many notes changed,
        # which keeps well inside GitHub's content creation limits.
        _, tree = api.call("POST", "/git/trees", json={"base_tree": root_tree, "tree": changes})
        _, commit = api.call("POST", "/git/commits", json={
            "message": f"PrivateGlue notes sync: {changed} changed",
            "tree": tree["sha"],
            "parents": [commit_sha],
        })
        status, data = api.call("PATCH", f"/git/refs/heads/{quote(branch, safe='/')}",
                                json={"sha": commit["sha"], "force": False}, allow=(409, 422))
        if status in (409, 422):
            raise IntegrationError(
                f"Branch '{branch}' changed on GitHub while syncing{_gh_message(data)}. Nothing was "
                "written. Run the sync again.")
        result.message = f"Pushed commit {commit['sha'][:7]} to {api.repo} ({branch})"
        return result

    def _pull(self, api, branch, folder, notes_dir, include_meta):
        result = SyncResult()
        head = self._head(api, branch)
        if head is None:
            result.message = f"The repository {api.repo} is empty, nothing to pull"
            return result
        _, root_tree = head
        remote = self._folder_entries(api, root_tree, folder, result)
        if remote is None:
            result.message = f"Folder '{'/'.join(folder)}' does not exist on branch '{branch}', nothing to pull"
            return result

        for name in sorted(remote):
            entry = remote[name]
            if not name.endswith(".md") or entry.get("type") != "blob":
                continue                     # subfolders, metadata (handled below) and other files
            if entry.get("mode") not in ("100644", "100755"):
                result.errors.append(f"{name}: skipped, not a regular file (symlink or submodule)")
                continue
            problem = _check_note_name(name)
            if problem:
                result.errors.append(f"{name}: skipped, {problem}")
                continue
            try:
                note_path = _note_path(notes_dir, name)
            except ValueError:
                result.errors.append(f"{name}: skipped, path is outside the notes folder")
                continue
            existed = os.path.exists(note_path)
            try:
                wrote_note = self._pull_file(api, entry, note_path, None)
            except ValueError as exc:
                result.errors.append(f"{name}: skipped, {exc}")
                continue

            wrote_meta = False
            meta_entry = remote.get(name + META_SUFFIX)
            if include_meta and meta_entry and meta_entry.get("type") == "blob":
                try:
                    wrote_meta = self._pull_file(api, meta_entry,
                                                 _note_path(notes_dir, name + META_SUFFIX), _clean_meta)
                except ValueError as exc:
                    result.errors.append(f"{name + META_SUFFIX}: skipped, {exc}")

            if not existed:
                result.created += 1
            elif wrote_note or wrote_meta:
                result.updated += 1
            else:
                result.skipped += 1
        result.message = f"Pulled from {api.repo} ({branch})"
        return result

    def _pull_file(self, api, entry, path, transform):
        """Download one blob into ``path`` when it differs. Returns True when the file was written.
        Raises ValueError with a short reason when the file has to be skipped."""
        if (entry.get("size") or 0) > MAX_FILE_BYTES:
            raise ValueError(f"larger than {MAX_FILE_BYTES // 1024} KB")
        local = None
        if os.path.isfile(path):
            with open(path, "rb") as f:
                local = f.read()
            if git_blob_sha(local) == entry.get("sha"):
                return False             # same content, no download needed
        _, blob = api.call("GET", f"/git/blobs/{entry['sha']}")
        blob = blob if isinstance(blob, dict) else {}
        try:
            if blob.get("encoding", "base64") != "base64":
                raise ValueError
            data = base64.b64decode(blob.get("content") or "", validate=False)
        except (ValueError, TypeError):
            raise ValueError("GitHub returned content that could not be decoded")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"larger than {MAX_FILE_BYTES // 1024} KB")
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("not UTF-8 text")
        if transform is not None:
            data = transform(data)
        if local == data:
            return False
        _write_atomic(path, data)
        return True


INTEGRATION = GitHubNotes()

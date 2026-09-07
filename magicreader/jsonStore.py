"""Crash-safe JSON storage for the files under data/.

The app rewrites these files whenever the web UI changes bands, sequences or
settings. Writing in place means a power cut mid-write leaves a truncated file,
and a truncated file makes loadFromFile() fail, which makes run() return False,
which makes the service exit(-1) and restart every 5 seconds forever.

Every write here goes to a temp file in the same directory, is fsync'd, and is
then swapped in with os.replace() - which is atomic on POSIX. The previous
contents are kept as <name>.bak so a bad file can still be recovered.
"""
import json
import os
import shutil
import tempfile

# Absolute paths, so the app no longer depends on being started from the repo
# root. Layout: <repo>/magicreader/jsonStore.py -> <repo>/data
APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(APP_DIR)
DATA_DIR = os.path.join(REPO_DIR, 'data')

DEFAULT_SUFFIX = '.default.json'
BACKUP_SUFFIX = '.bak'


def dataPath(filename: str) -> str:
    """Returns the absolute path to a file in the data directory."""
    return os.path.join(DATA_DIR, filename)


def isReadableJson(path: str) -> bool:
    """Returns True if path exists and parses as JSON."""
    try:
        with open(path, 'r') as file:
            json.load(file)
        return True
    except Exception:
        return False


def saveJsonAtomic(path: str, data, indent: int = 4) -> bool:
    """Writes data to path as JSON atomically. Returns True on success."""
    directory = os.path.dirname(os.path.abspath(path)) or '.'
    temp_path = None
    try:
        os.makedirs(directory, exist_ok=True)
        # Temp file must share a filesystem with the target for os.replace()
        # to be atomic, so create it in the same directory.
        handle, temp_path = tempfile.mkstemp(dir=directory, prefix='.tmp-')
        # mkstemp() creates the file 0600. Carry over the mode of the file we
        # are replacing so the swap does not silently tighten permissions;
        # fall back to the normal umask-derived mode for a brand new file.
        try:
            if os.path.exists(path):
                os.chmod(temp_path, os.stat(path).st_mode & 0o7777)
            else:
                umask = os.umask(0)
                os.umask(umask)
                os.chmod(temp_path, 0o666 & ~umask)
        except Exception as e:
            print(f"WARNING: Could not set permissions on {path}: {e}", flush=True)
        with os.fdopen(handle, 'w') as file:
            json.dump(data, file, indent=indent)
            file.write('\n')
            file.flush()
            # Force the data to disk before the rename, otherwise a power cut
            # can leave the renamed file present but empty.
            os.fsync(file.fileno())
        # Keep the last known-good copy before swapping in the new file. Only
        # back up a file that still parses - otherwise recovering from a
        # corrupt file and then saving would overwrite the good .bak with the
        # corrupt content, leaving no usable copy at all.
        if os.path.exists(path):
            if isReadableJson(path):
                try:
                    shutil.copy2(path, path + BACKUP_SUFFIX)
                except Exception as e:
                    print(f"WARNING: Could not back up {path}: {e}", flush=True)
            else:
                print(f"WARNING: {path} is not valid JSON - keeping the existing backup", flush=True)
        os.replace(temp_path, path)
        temp_path = None
        # fsync the directory so the rename itself survives a power cut.
        try:
            dir_handle = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(dir_handle)
            finally:
                os.close(dir_handle)
        except Exception as e:
            print(f"WARNING: Could not fsync {directory}: {e}", flush=True)
        return True
    except Exception as e:
        print(f"ERROR writing {path}: {e}", flush=True)
        return False
    finally:
        # Never leave a temp file behind if anything above failed.
        if temp_path is not None and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def loadJson(path: str, useBackup: bool = True):
    """Loads JSON from path, falling back to the .bak copy. Returns None if both fail."""
    candidates = [path]
    if useBackup:
        candidates.append(path + BACKUP_SUFFIX)
    for index, candidate in enumerate(candidates):
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, 'r') as file:
                data = json.load(file)
            if index > 0:
                print(f"WARNING: {path} was unreadable - recovered from {candidate}", flush=True)
            return data
        except Exception as e:
            print(f"ERROR reading {candidate}: {e}", flush=True)
    return None


def seedDataFileFromDefault(filename: str) -> bool:
    """Creates data/<filename> from data/<name>.default.json if it is missing.

    Runtime data files are not tracked in git - the repo ships .default.json
    templates instead, so pulling an update never collides with local edits
    made through the web UI.
    """
    target = dataPath(filename)
    if os.path.exists(target):
        return True
    default = dataPath(os.path.splitext(filename)[0] + DEFAULT_SUFFIX)
    if not os.path.exists(default):
        print(f"ERROR: No data file or default template for {filename}", flush=True)
        return False
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        shutil.copyfile(default, target)
        print(f"Created {target} from default template", flush=True)
        return True
    except Exception as e:
        print(f"ERROR seeding {target} from {default}: {e}", flush=True)
        return False


def seedAllDataFiles(filenames) -> bool:
    """Seeds every missing runtime data file. Returns True if all are present."""
    return all([seedDataFileFromDefault(name) for name in filenames])

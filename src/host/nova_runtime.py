"""The pinned NovaLang runtime: the one place the host loads the interpreter.

NovaLang is vendored as a git submodule at vendor/Nova_Lang, pinned to
PINNED_COMMIT. assert_pinned() is the startup check: the interpreter must
report PINNED_VERSION (Nova_Lang/novalang.py:88, ``__version__``), and when
the submodule is a git checkout its HEAD must be PINNED_COMMIT. Every entry
point (the app, tools/run_tests.py) calls it before running any NovaLang.
"""

import os
import shutil
import subprocess
import sys

PINNED_VERSION = "2.0.0"
PINNED_COMMIT = "bd5d502611fd5749046382b54fb9f91fc58d1e47"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NOVA_DIR = os.path.join(REPO_ROOT, "vendor", "Nova_Lang")
NOVA_SCRIPT = os.path.join(NOVA_DIR, "novalang.py")


class NovaPinError(RuntimeError):
    """The vendored NovaLang is missing or is not the pinned release."""


def load_novalang():
    """Import vendor/Nova_Lang/novalang.py and return the module."""
    if not os.path.isfile(NOVA_SCRIPT):
        raise NovaPinError(
            "NovaLang not found at {} - run `git submodule update --init`".format(NOVA_SCRIPT)
        )
    if NOVA_DIR not in sys.path:
        sys.path.insert(0, NOVA_DIR)
    import novalang
    return novalang


def submodule_commit():
    """HEAD of the submodule, or None when it is not a git checkout."""
    if not os.path.exists(os.path.join(NOVA_DIR, ".git")):
        return None
    if shutil.which("git") is None:
        raise NovaPinError("vendor/Nova_Lang is a git checkout but `git` is not installed")
    result = subprocess.run(
        ["git", "-C", NOVA_DIR, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        raise NovaPinError("could not read the submodule commit: " + result.stderr.strip())
    return result.stdout.strip()


def assert_pinned():
    """Fail unless the vendored NovaLang is exactly the pinned release."""
    version = getattr(load_novalang(), "__version__", None)
    if version != PINNED_VERSION:
        raise NovaPinError(
            "NovaLang {} is pinned, but vendor/Nova_Lang reports {!r}".format(PINNED_VERSION, version)
        )
    commit = submodule_commit()
    if commit is not None and commit != PINNED_COMMIT:
        raise NovaPinError(
            "vendor/Nova_Lang is at {}, but {} is pinned".format(commit, PINNED_COMMIT)
        )
    return version

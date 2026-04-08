"""
cli.py — Command-line entry point for obs-quickshare.

Commands:
  install    Full guided install (profile + scenes + shortcut + watcher config)
  uninstall  Remove profile, scene collection, and shortcut (keeps recordings)
  status     Show current config, encoder, and Drive mode
  watch      Start the file watcher in the foreground
  version    Print version and exit
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .detect import DetectionResult, run_detection
from .drive import describe_drive_mode
from .profile import profile_exists, write_profile
from .scenes import collection_exists, write_scene_collection
from .shortcut import shortcut_exists, write_shortcut
from .watcher import FileWatcher

# ANSI colours (disabled on Windows unless in Windows Terminal)
_USE_COLOUR = sys.stdout.isatty() and sys.platform != "win32"

def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOUR else text

def _green(t: str)  -> str: return _c(t, "32")
def _yellow(t: str) -> str: return _c(t, "33")
def _red(t: str)    -> str: return _c(t, "31")
def _bold(t: str)   -> str: return _c(t, "1")


def _print_banner() -> None:
    print(_bold("\nOBS QuickShare") + f"  v{__version__}")
    print("Open-source async screen recorder\n")


def _print_detection(result: DetectionResult) -> None:
    print(f"  OBS config : {result.config_root}")
    version_str = result.obs_version or "unknown"
    version_ok  = _green(version_str) if result.version_ok else _yellow(version_str + " (old)")
    print(f"  OBS version: {version_ok}")

    encoder_str = result.encoder.label
    hw_tag      = _green("hardware") if result.encoder.is_hardware else _yellow("software")
    print(f"  Encoder    : {encoder_str} [{hw_tag}]")

    print(f"  Staging dir: {result.staging_dir}")
    print(f"  Output dir : {result.output_dir}")
    print(f"  Drive sync : {describe_drive_mode(result.drive)}")

    if result.warnings:
        print()
        for w in result.warnings:
            print(_yellow(f"  ⚠  {w}"))
    print()


def _parse_capture_mode(value: str) -> tuple[str, str]:
    """Parse --capture-mode value into (mode, target).

    Accepted forms:
      display           → ("display", "")
      window            → ("window", "")
      app:<bundle-id>   → ("app", "<bundle-id>")
    """
    if value == "display":
        return ("display", "")
    if value == "window":
        return ("window", "")
    if value.startswith("app:"):
        target = value[4:].strip()
        if not target:
            raise ValueError(
                "--capture-mode app: requires a bundle ID, e.g. app:com.google.Chrome"
            )
        return ("app", target)
    raise ValueError(
        f"Unknown --capture-mode '{value}'. "
        "Use: display | window | app:<bundle-id>"
    )


def _confirm(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    try:
        answer = input(prompt + suffix).strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    if not answer:
        return default
    return answer in ("y", "yes")


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

def cmd_install(args: argparse.Namespace) -> int:
    _print_banner()

    # --- Detection ---
    print("Detecting system configuration …")
    try:
        result = run_detection(rclone_remote=args.rclone_remote)
    except RuntimeError as e:
        print(_red(f"Error: {e}"))
        return 1

    _print_detection(result)

    # --- Interactive confirmation (skipped with --yes) ---
    if not args.yes:
        print("The following will be created:")
        profile_path = result.config_root / "basic" / "profiles" / "QuickShare"
        scenes_path = result.config_root / "basic" / "scenes" / "QuickShare.json"
        print(f"  • OBS profile  : QuickShare  ({profile_path})")
        print(f"  • Scene coll.  : QuickShare  ({scenes_path})")
        print("  • Launcher     : OBS QuickShare  (platform shortcut)")
        print()
        if not _confirm("Proceed with installation?"):
            print("Aborted.")
            return 0

    # --- Profile ---
    already_exists = profile_exists(result.config_root)
    if already_exists and not args.force:
        print(_yellow("QuickShare profile already exists — skipping (use --force to overwrite)."))
    else:
        try:
            ini_path = write_profile(result, force=args.force)
            print(_green(f"✓ Profile written: {ini_path}"))
        except FileExistsError as e:
            print(_yellow(f"⚠  {e}"))

    # --- Scene collection ---
    try:
        capture_mode, capture_target = _parse_capture_mode(args.capture_mode)
    except ValueError as e:
        print(_red(f"Error: {e}"))
        return 1
    already_exists = collection_exists(result.config_root)
    if already_exists and not args.force:
        print(_yellow(
            "QuickShare scene collection already exists — skipping (use --force to overwrite)."
        ))
    else:
        try:
            json_path = write_scene_collection(
                result.config_root, force=args.force,
                capture_mode=capture_mode, capture_target=capture_target,
                include_webcam=args.webcam, include_mic=args.mic,
            )
            print(_green(f"✓ Scene collection written: {json_path}"))
        except FileExistsError as e:
            print(_yellow(f"⚠  {e}"))

    # --- Shortcut ---
    if shortcut_exists() and not args.force:
        print(_yellow("Launcher already exists — skipping (use --force to overwrite)."))
    else:
        try:
            sc_path = write_shortcut(force=args.force)
            print(_green(f"✓ Launcher created: {sc_path}"))
            print(
                "  (Tip: ~/Applications is your personal Applications folder. "
                "In Finder: Go → Home, then open Applications.)"
            )
            print(
                "  (Note: the first launch opens a Terminal window briefly — "
                "this is expected. Allow mic access if prompted; it is OBS "
                "requesting it through the shell launcher.)"
            )
        except FileExistsError as e:
            print(_yellow(f"⚠  {e}"))

    # --- Ensure output/staging dirs exist ---
    result.staging_dir.mkdir(parents=True, exist_ok=True)
    result.output_dir.mkdir(parents=True, exist_ok=True)

    # --- Summary ---
    print()
    print(_bold("Installation complete!"))
    print()
    print("Next steps:")
    print("  1. Open OBS Studio (or double-click the new launcher).")
    print("  2. The launcher will start recording immediately with the QuickShare profile.")
    print("  3. When you stop recording, OBS will remux to MP4 automatically.")
    print("  4. obs-quickshare will move the finished MP4 to:")
    print(f"     {describe_drive_mode(result.drive)}")
    print()
    print(f"  Run '{_bold('obs-quickshare watch')}' to start the file watcher in the background.")
    print()
    return 0


# ---------------------------------------------------------------------------
# set-capture
# ---------------------------------------------------------------------------

def cmd_set_capture(args: argparse.Namespace) -> int:
    """Rewrite only the scene collection — no profile/shortcut changes."""
    try:
        result = run_detection(rclone_remote=None)
    except RuntimeError as e:
        print(_red(f"Error: {e}"))
        return 1

    if not collection_exists(result.config_root):
        print(_red("QuickShare scene collection not found. Run 'obs-quickshare install' first."))
        return 1

    try:
        capture_mode, capture_target = _parse_capture_mode(args.capture_mode)
    except ValueError as e:
        print(_red(f"Error: {e}"))
        return 1

    json_path = write_scene_collection(
        result.config_root, force=True,
        capture_mode=capture_mode, capture_target=capture_target,
        include_webcam=args.webcam, include_mic=args.mic,
    )
    print(_green(f"✓ Scene collection updated: {json_path}"))
    print("  Restart OBS (or switch scene collections and back) to apply.")
    return 0


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------

def cmd_uninstall(args: argparse.Namespace) -> int:
    _print_banner()

    try:
        result = run_detection()
    except RuntimeError as e:
        print(_red(f"Error: {e}"))
        return 1

    if not args.yes:
        print("This will remove:")
        print(f"  • OBS profile    : {result.config_root / 'basic' / 'profiles' / 'QuickShare'}")
        print(f"  • Scene coll.    : {result.config_root / 'basic' / 'scenes' / 'QuickShare.json'}")
        print("  • Platform launcher")
        print()
        print(_yellow("Recordings will NOT be deleted."))
        print()
        if not _confirm("Proceed with uninstall?", default=False):
            print("Aborted.")
            return 0

    import shutil as _shutil

    profile_path = result.config_root / "basic" / "profiles" / "QuickShare"
    if profile_path.exists():
        _shutil.rmtree(profile_path)
        print(_green(f"✓ Removed profile: {profile_path}"))
    else:
        print("  Profile not found, skipping.")

    scenes_path = result.config_root / "basic" / "scenes" / "QuickShare.json"
    if scenes_path.exists():
        scenes_path.unlink()
        print(_green(f"✓ Removed scene collection: {scenes_path}"))
    else:
        print("  Scene collection not found, skipping.")

    # Shortcut removal
    import platform as _platform

    from .shortcut import _linux_shortcut_path, _macos_shortcut_path, _windows_shortcut_path
    system = _platform.system()
    if system == "Darwin":
        sc = _macos_shortcut_path()
    elif system == "Windows":
        sc = _windows_shortcut_path(use_lnk=True)
        if not sc.exists():
            sc = _windows_shortcut_path(use_lnk=False)
    else:
        sc = _linux_shortcut_path()

    if sc.exists():
        sc.unlink()
        print(_green(f"✓ Removed launcher: {sc}"))
    else:
        print("  Launcher not found, skipping.")

    print()
    print(_bold("Uninstall complete."))
    return 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def cmd_status(_args: argparse.Namespace) -> int:
    _print_banner()
    try:
        result = run_detection()
    except RuntimeError as e:
        print(_red(f"Error: {e}"))
        return 1

    _print_detection(result)

    profile_ok    = profile_exists(result.config_root)
    collection_ok = collection_exists(result.config_root)
    shortcut_ok   = shortcut_exists()

    def _tick(ok: bool) -> str:
        return _green("✓") if ok else _red("✗")

    print("Installed components:")
    print(f"  {_tick(profile_ok)}  OBS profile (QuickShare)")
    print(f"  {_tick(collection_ok)}  Scene collection (QuickShare)")
    print(f"  {_tick(shortcut_ok)}  Platform launcher")
    print()

    if not all([profile_ok, collection_ok, shortcut_ok]):
        print(_yellow("Run 'obs-quickshare install' to complete the setup."))
    else:
        print(_green("All components installed. You're ready to record!"))
    print()
    return 0


# ---------------------------------------------------------------------------
# watch
# ---------------------------------------------------------------------------

def cmd_watch(args: argparse.Namespace) -> int:
    try:
        result = run_detection(rclone_remote=getattr(args, "rclone_remote", None))
    except RuntimeError as e:
        print(_red(f"Error: {e}"))
        return 1

    print(_bold("[obs-quickshare] Watcher started"))
    print(f"  Staging : {result.staging_dir}")
    print(f"  Output  : {describe_drive_mode(result.drive)}")
    print("  Press Ctrl+C to stop.\n")

    watcher = FileWatcher(
        staging_dir=result.staging_dir,
        output_dir=result.output_dir,
        drive=result.drive,
    )

    try:
        watcher.start()
    except KeyboardInterrupt:
        print("\n[obs-quickshare] Watcher stopped.")
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obs-quickshare",
        description="One-click OBS recording workflow — open-source async screen recorder.",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version=f"obs-quickshare {__version__}",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # install
    p_install = sub.add_parser("install", help="Set up the QuickShare profile and launcher")
    p_install.add_argument("--yes", "-y", action="store_true",
                           help="Non-interactive: accept all defaults")
    p_install.add_argument("--force", "-f", action="store_true",
                           help="Overwrite existing profile / scene collection / shortcut")
    p_install.add_argument("--rclone-remote", metavar="NAME",
                           help="rclone remote name to use for Drive sync (Mode B)")
    p_install.add_argument(
        "--capture-mode", metavar="MODE", default="display",
        help=(
            "What to capture: 'display' (full screen, default), 'window' (OBS window picker), "
            "or 'app:<bundle-id>' (all windows of one app, e.g. app:com.google.Chrome). "
            "macOS only; ignored on Windows/Linux."
        ),
    )
    p_install.add_argument("--webcam", action="store_true",
                           help="Add a webcam PiP source (bottom-right corner)")
    p_install.add_argument("--mic", action="store_true",
                           help="Add a microphone audio source (system default device)")

    # set-capture
    p_set = sub.add_parser("set-capture",
                            help="Change capture mode / webcam / mic without reinstalling")
    p_set.add_argument(
        "capture_mode", metavar="MODE", nargs="?", default="display",
        help="display | window | app:<bundle-id>  (default: display)",
    )
    p_set.add_argument("--webcam", action="store_true",
                       help="Include webcam PiP source")
    p_set.add_argument("--mic", action="store_true",
                       help="Include microphone audio source")

    # uninstall
    p_uninstall = sub.add_parser("uninstall", help="Remove QuickShare config and launcher")
    p_uninstall.add_argument("--yes", "-y", action="store_true",
                              help="Non-interactive: skip confirmation prompt")

    # status
    sub.add_parser("status", help="Show installation status and detected config")

    # watch
    p_watch = sub.add_parser("watch", help="Start the post-processing file watcher")
    p_watch.add_argument("--rclone-remote", metavar="NAME",
                         help="rclone remote name (overrides auto-detected mode)")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args   = parser.parse_args(argv)

    dispatch = {
        "install":     cmd_install,
        "set-capture": cmd_set_capture,
        "uninstall":   cmd_uninstall,
        "status":      cmd_status,
        "watch":       cmd_watch,
    }

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    sys.exit(handler(args))


if __name__ == "__main__":
    main()

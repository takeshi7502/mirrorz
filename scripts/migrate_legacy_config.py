"""Prepare local configuration without importing it, contacting MongoDB or starting a bot."""

import argparse
import ast
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREDENTIAL_FILES = (
    "token.pickle",
    "credentials.json",
    "rclone.conf",
    ".netrc",
    "list_drives.txt",
    "shortener.txt",
    "categories.txt",
    "cookies.txt",
    "terabox.txt",
)


def read_settings(path):
    settings = {}
    for node in ast.parse(Path(path).read_text(encoding="utf-8-sig")).body:
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            raise ValueError(
                "Configuration must contain literal assignments only; it will not be executed."
            )
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError) as error:
            raise ValueError(
                "Configuration contains a nonliteral assignment; it will not be executed."
            ) from error
        for target in targets:
            if not isinstance(target, ast.Name):
                raise ValueError("Configuration keys must be simple variable names.")
            settings[target.id] = value
    return settings


def prepare_settings(settings):
    tree = ast.parse((ROOT / "bot/core/config_manager.py").read_text(encoding="utf-8"))
    config = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Config"
    )
    keys = {
        target.id
        for node in config.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    keys = {key for key in keys if not key.startswith(("USER_QUOTA_", "REFERRAL_"))}
    result = {key: value for key, value in settings.items() if key in keys}
    if not result.get("LEECH_LOG_CHAT") and settings.get("LEECH_DUMP_CHAT"):
        result["LEECH_LOG_CHAT"] = settings["LEECH_DUMP_CHAT"]
    result.setdefault("BASE_URL_MODE", "tunnel")
    result.setdefault("BASE_URL_LEGACY", settings.get("BASE_URL", ""))
    # A startup update from the old fork would overwrite the new implementation.
    result["UPSTREAM_REPO"] = ""
    result["UPSTREAM_BRANCH"] = "wzv3-takeshi"
    ignored = sorted(set(settings) - keys - {"LEECH_DUMP_CHAT"})
    return result, ignored


def migrate(source, output, *, write=False, copy_credentials=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    source_file = source / "config.py" if source.is_dir() else source
    source_dir = source_file.parent
    settings, ignored = prepare_settings(read_settings(source_file))
    copies = []
    if copy_credentials:
        copies.extend(
            (source_dir / name, output.parent / name)
            for name in CREDENTIAL_FILES
            if (source_dir / name).is_file()
        )
        accounts = source_dir / "accounts"
        if accounts.is_dir():
            copies.extend(
                (file, output.parent / file.relative_to(source_dir))
                for file in accounts.rglob("*.json")
                if file.is_file()
            )
    if output.exists():
        raise FileExistsError(
            "Destination config already exists; choose a new output path."
        )
    for src, dst in copies:
        if dst.exists() and src.read_bytes() != dst.read_bytes():
            raise FileExistsError(f"Destination credential already exists: {dst.name}")
    if write:
        output.parent.mkdir(parents=True, exist_ok=True)
        text = (
            "# Local settings migrated from the previous bot. Never commit this file.\n"
        )
        text += (
            "# Automatic source updates are disabled during migration validation.\n\n"
        )
        text += "".join(f"{key} = {value!r}\n" for key, value in settings.items())
        # Exclusive creation also protects against a file appearing after the preflight.
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        for src, dst in copies:
            if not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    return {
        "written": write,
        "settings_count": len(settings),
        "ignored_keys": ignored,
        "credential_files": [str(dst.relative_to(output.parent)) for _, dst in copies],
        "automatic_source_updates": "disabled",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, required=True, help="Old repository or config.py"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "config.py")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Create files; without this flag only report the plan",
    )
    parser.add_argument(
        "--copy-credentials",
        action="store_true",
        help="Also copy known credential files and service-account JSONs",
    )
    args = parser.parse_args()
    try:
        result = migrate(
            args.source,
            args.output,
            write=args.write,
            copy_credentials=args.copy_credentials,
        )
    except (OSError, ValueError, SyntaxError) as error:
        parser.exit(1, f"Migration failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

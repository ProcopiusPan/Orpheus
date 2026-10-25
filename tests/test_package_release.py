from pathlib import Path
import json
import os
import re
import shutil
import subprocess

from importlib.util import module_from_spec, spec_from_file_location


ROOT = Path(__file__).parents[1]
SPEC = spec_from_file_location("package_release", ROOT / "scripts/package_release.py")
package_release = module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(package_release)


def materialize_portable_package(destination: Path) -> None:
    for name, data in package_release.portable_blobs(ROOT, package_release.select_release_files(ROOT)).items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def test_release_selection_contains_portable_surface_without_private_state():
    names = {path.relative_to(ROOT).as_posix() for path in package_release.select_release_files(ROOT)}
    assert "service/orpheus_fact/git_facts.py" in names
    assert "service/orpheus_fact/stdio_mcp.py" in names
    assert "scripts/check_markdown.py" in names
    assert "scripts/fact_admin.py" in names
    assert "scripts/audit_fact_change.py" in names
    assert "scripts/orpheus_fact_stdio.py" in names
    assert "scripts/install_portable.ps1" in names
    assert "docs/安装便携包.md" in names
    assert "docs/快速开始.md" in names
    assert "docs/Zotero适配与使用.md" in names
    assert "plugins/orpheus/references/agent-orchestration.md" in names
    for relative in ("SKILL.md", "agents/openai.yaml", "references/evidence-and-updates.md",
                     "references/manuscript-validation.md", "references/readability-polish.md"):
        assert f"plugins/orpheus/skills/fact-paper-writing/{relative}" in names
    for role in ("compute", "reader", "researcher", "verifier"):
        assert f"plugins/orpheus/assets/agent-templates/orpheus-{role}.toml" in names
    assert "marketplace/marketplace.json" in names
    assert "tests/test_portable_smoke.py" in names
    assert "tests/test_git_facts.py" in names
    assert "tests/test_audit_fact_change.py" in names
    assert ".github/workflows/fact-integrity.yml" in names
    assert not any(name.startswith("scripts/install_service") or
                   name.startswith("scripts/update_service_model") or
                   name.startswith("scripts/upgrade_verifier") or
                   name.startswith("scripts/service_task_admin") for name in names)
    assert not any(name.startswith(".runtime/") for name in names)
    assert not any(Path(name).parts[0] in {"facts", "candidates", "reviews", "requests", "issues", "incidents", ".git"} for name in names)


def test_portable_blobs_scrub_development_mcp_path():
    blobs = package_release.portable_blobs(ROOT, package_release.select_release_files(ROOT))
    for data in blobs.values():
        for text in package_release.payload_texts(data):
            assert str(Path.home()) not in text
            assert str(Path.home()).replace("\\", "/") not in text
    names = set(blobs)
    assert not any(name.startswith(("facts/", "candidates/", "reviews/", "requests/", "issues/", "incidents/", ".git/")) for name in names)
    assert b"__GENERATED_BY_INSTALLER__" in blobs["plugins/orpheus/.mcp.json"]
    readme = blobs["README.md"].decode("utf-8")
    assert re.search(r"\[[^\]]+\]\(https://github\.com/[^/\s]+/[^/\s]+/releases/latest\)", readme)
    assert "scripts\\install_portable.ps1" in readme or "scripts/install_portable.ps1" in readme
    assert "ExecutionPolicy Bypass" in blobs["docs/快速开始.md"].decode("utf-8")
    orchestration = blobs["plugins/orpheus/references/agent-orchestration.md"].decode("utf-8")
    assert "模型继承政策" in orchestration
    assert "height 5" not in orchestration and "height 6" not in orchestration
    for role in ("compute", "reader", "researcher", "verifier"):
        template = blobs[f"plugins/orpheus/assets/agent-templates/orpheus-{role}.toml"].decode("utf-8")
        assert f'name = "orpheus-{role}"' in template
        assert "height 5" not in template and "height 6" not in template


def test_portable_extraction_scan_covers_utf8_utf16_and_private_fact_payload(tmp_path):
    blobs = package_release.portable_blobs(ROOT, package_release.select_release_files(ROOT))
    archive_path = tmp_path / "portable.zip"
    import zipfile
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, data in blobs.items():
            archive.writestr(name, data)
    markers = package_release.private_payload_markers(ROOT)
    with zipfile.ZipFile(archive_path) as archive:
        for name in archive.namelist():
            data = archive.read(name)
            assert not any(marker in text for text in package_release.payload_texts(data) for marker in markers), name
    live_fact_ids = {path.parent.name for path in (ROOT / "facts").glob("fact-*/v*.json")}
    assert live_fact_ids <= markers


def test_portable_installer_uses_empty_remote_probe_without_force_push():
    installer = (ROOT / "scripts/install_portable.ps1").read_text(encoding="utf-8")
    assert "ls-remote --heads --tags" in installer
    assert "git push --force" not in installer
    assert "--set-upstream" in installer
    assert "PersonalRoot" in installer
    assert "Write-AtomicJson" in installer
    assert "GIT_TERMINAL_PROMPT" in installer
    assert "plugin add --help" in installer
    assert "$SkipDependencyInstall" in installer
    assert "$SkipPluginInstall" in installer
    assert "$PluginName = \"orpheus\"" in installer
    assert "PluginName -notmatch" in installer
    assert '"plugins/" + $PluginName' in installer


def test_portable_installer_dry_run_isolated_from_user_state(tmp_path):
    if os.name != "nt":
        return
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        return
    probe = subprocess.run([pwsh, "-NoProfile", "-Command", "$PSVersionTable.PSVersion.ToString()"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if probe.returncode:
        return
    target = tmp_path / "portable-install"
    isolated_env = os.environ.copy()
    isolated_env["HOME"] = str(tmp_path / "home")
    isolated_env["USERPROFILE"] = str(tmp_path / "home")
    isolated_env["CODEX_HOME"] = str(tmp_path / "codex-home")
    result = subprocess.run([pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/install_portable.ps1"),
                            "-InstallPath", str(target), "-PersonalRoot", str(tmp_path / "personal"),
                            "-RemoteUrl", "https://example.invalid/empty.git", "-DryRun"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=isolated_env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DRY_RUN" in result.stdout
    assert "empty-remote probe" in result.stdout
    assert not target.exists()


def test_portable_installer_rejects_remote_credentials_before_writes(tmp_path):
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        return
    for remote in ("https://token@example.invalid/repo.git", "https://example.invalid/repo.git?token=x", "ssh://git@example.invalid/repo.git"):
        target = tmp_path / remote.split(":", 1)[0].replace("/", "-")
        result = subprocess.run(
            [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts/install_portable.ps1"),
             "-InstallPath", str(target), "-RemoteUrl", remote, "-DryRun"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert result.returncode != 0
        assert not target.exists()


def test_portable_installer_real_temp_install_without_network(tmp_path):
    if os.name != "nt":
        return
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        return
    package = tmp_path / "package"
    target = tmp_path / "installed"
    personal = tmp_path / "personal"
    materialize_portable_package(package)
    isolated_env = os.environ.copy()
    isolated_env["HOME"] = str(tmp_path / "home")
    isolated_env["USERPROFILE"] = str(tmp_path / "home")
    isolated_env["CODEX_HOME"] = str(tmp_path / "codex-home")
    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(package / "scripts/install_portable.ps1"),
         "-InstallPath", str(target), "-PersonalRoot", str(personal),
         "-SkipDependencyInstall", "-SkipPluginInstall", "-GitName", "Smoke User", "-GitEmail", "smoke@example.invalid"],
        cwd=package, capture_output=True, text=True, encoding="utf-8", errors="replace", env=isolated_env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (target / ".git").is_dir()
    branch = subprocess.run(["git", "-C", str(target), "branch", "--show-current"], capture_output=True, text=True, encoding="utf-8")
    assert branch.returncode == 0 and branch.stdout.strip() == "main"
    commit = subprocess.run(["git", "-C", str(target), "log", "-1", "--format=%s"], capture_output=True, text=True, encoding="utf-8")
    assert commit.returncode == 0 and "initialize portable Orpheus repository" in commit.stdout
    assert (target / "facts/README.md").exists()
    assert (target / "facts/MANIFEST.json").exists()
    assert not list((target / "facts").glob("fact-*"))
    mcp = json.loads((target / "plugins/orpheus/.mcp.json").read_text(encoding="utf-8-sig"))
    command = Path(mcp["mcpServers"]["orpheus-fact"]["command"])
    script = Path(mcp["mcpServers"]["orpheus-fact"]["args"][0])
    assert command.resolve() == (target / ".venv/Scripts/python.exe").resolve()
    assert script.resolve() == (target / "scripts/orpheus_fact_stdio.py").resolve()
    assert not personal.exists()
    writing = Path("plugins/orpheus/skills/fact-paper-writing")
    for source in (ROOT / writing).rglob("*"):
        if source.is_file():
            relative = source.relative_to(ROOT)
            assert (target / relative).read_bytes() == source.read_bytes()


def test_portable_installer_trial_is_side_by_side_with_existing_orpheus(tmp_path):
    if os.name != "nt":
        return
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        return
    package = tmp_path / "package"
    target = tmp_path / "trial"
    personal = tmp_path / "personal"
    materialize_portable_package(package)
    existing_plugin = personal / "plugins/orpheus"
    existing_plugin.mkdir(parents=True)
    (existing_plugin / "keep.txt").write_text("existing", encoding="utf-8")
    marketplace_path = personal / ".agents/plugins/marketplace.json"
    marketplace_path.parent.mkdir(parents=True)
    marketplace_path.write_text(json.dumps({
        "name": "personal", "interface": {"displayName": "Personal"},
        "unknownField": {"preserve": True},
        "plugins": [{"name": "orpheus", "source": {"source": "local", "path": "./plugins/orpheus"}}],
    }) + "\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "codex.cmd").write_text(
        "@echo off\nif \"%3\"==\"--help\" (echo --json & exit /b 0)\necho {\"status\":\"ok\"}\nexit /b 0\n",
        encoding="ascii",
    )
    isolated_env = os.environ.copy()
    isolated_env["PATH"] = str(fake_bin) + os.pathsep + isolated_env["PATH"]
    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(package / "scripts/install_portable.ps1"),
         "-InstallPath", str(target), "-PersonalRoot", str(personal), "-PluginName", "orpheus-trial",
         "-SkipDependencyInstall", "-GitName", "Trial User", "-GitEmail", "trial@example.invalid"],
        cwd=package, capture_output=True, text=True, encoding="utf-8", errors="replace", env=isolated_env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (existing_plugin / "keep.txt").read_text(encoding="utf-8") == "existing"
    assert not (target / "plugins/orpheus").exists()
    trial_plugin = target / "plugins/orpheus-trial"
    assert trial_plugin.is_dir()
    manifest = json.loads((trial_plugin / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "orpheus-trial"
    assert manifest["interface"]["displayName"] == "Orpheus (orpheus-trial)"
    assert manifest["version"].endswith(".orpheus-trial")
    mcp = json.loads((trial_plugin / ".mcp.json").read_text(encoding="utf-8-sig"))
    assert Path(mcp["mcpServers"]["orpheus-fact"]["args"][0]).resolve() == (target / "scripts/orpheus_fact_stdio.py").resolve()
    marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    assert marketplace["unknownField"] == {"preserve": True}
    entries = {entry["name"]: entry for entry in marketplace["plugins"]}
    assert entries["orpheus"]["source"]["path"] == "./plugins/orpheus"
    assert entries["orpheus-trial"]["source"]["path"] == "./plugins/orpheus-trial"


def test_portable_installer_rolls_back_plugin_and_marketplace_on_cli_failure(tmp_path):
    if os.name != "nt":
        return
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if not pwsh:
        return
    package = tmp_path / "package"
    target = tmp_path / "installed"
    personal = tmp_path / "personal"
    materialize_portable_package(package)
    marketplace_path = personal / ".agents/plugins/marketplace.json"
    marketplace_path.parent.mkdir(parents=True)
    original = {
        "name": "personal",
        "interface": {"displayName": "Personal"},
        "customField": {"keep": True},
        "plugins": [{"name": "other", "category": "Productivity"}],
    }
    original_bytes = (json.dumps(original, indent=2) + "\n").encode("utf-8")
    marketplace_path.write_bytes(original_bytes)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "codex.cmd").write_text(
        "@echo off\nif \"%3\"==\"--help\" (echo --json & exit /b 0)\nexit /b 17\n",
        encoding="ascii",
    )
    isolated_env = os.environ.copy()
    isolated_env["PATH"] = str(fake_bin) + os.pathsep + isolated_env["PATH"]
    result = subprocess.run(
        [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(package / "scripts/install_portable.ps1"),
         "-InstallPath", str(target), "-PersonalRoot", str(personal), "-SkipDependencyInstall",
         "-GitName", "Smoke User", "-GitEmail", "smoke@example.invalid"],
        cwd=package, capture_output=True, text=True, encoding="utf-8", errors="replace", env=isolated_env,
    )
    assert result.returncode != 0
    assert not target.exists()
    assert not (personal / "plugins/orpheus").exists()
    assert marketplace_path.read_bytes() == original_bytes

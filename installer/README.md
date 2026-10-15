# camcommand Windows installer

Builds a self-contained GUI installer so end users can install `camcommand`
**without Python, pip, or any dependencies** — everything is bundled into a
single `.exe`.

## What ends up on the user's machine

`Output\camcommand-setup.exe` is a normal Windows setup wizard that:

- Installs a standalone `camcommand.exe` (Python + pyserial frozen inside it).
- Adds the install folder to `PATH`, so `camcommand` works in any new terminal.
- Registers an entry in **Add or remove programs** with a working uninstaller
  (which also removes itself from `PATH`).

By default it installs **per-user** to `%LOCALAPPDATA%\Programs\camcommand`
with no UAC prompt. The user can choose "install for all users" on the
privileges page to install to `Program Files` (system `PATH`, requires admin).

The end user needs **no Python** — the runtime is baked into the exe.

## Rebuilding (on a dev machine)

Prerequisites on the build machine only:

- Python with camcommand installed: `pip install -e .` from the repo root
- PyInstaller: `pip install pyinstaller`
- Inno Setup 6: `winget install JRSoftware.InnoSetup`

Then:

```powershell
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```

The finished installer is written to `installer\Output\camcommand-setup.exe`.

## Files

| File             | Purpose                                                      |
| ---------------- | ----------------------------------------------------------- |
| `build.ps1`      | One command: freeze the exe + compile the installer.        |
| `entry.py`       | Tiny PyInstaller entry point → `camcommand.cli:main`.       |
| `camcommand.iss` | Inno Setup script (files, PATH, uninstaller).               |

Bump the version in **two** places when releasing: `pyproject.toml` and the
`MyAppVersion` define at the top of `camcommand.iss`.

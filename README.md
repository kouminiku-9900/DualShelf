# Portable Backup Tool

Windows 向けの portable バックアップツールです。`robocopy` を GUI から安全に扱う用途を想定しています。

## 開発実行

```powershell
python app/main.py
```

## テスト

```powershell
python -m unittest discover -s tests -v
```

## onedir ビルド

```powershell
.\build.ps1
```

現在のバージョンは `v0.3` です。ビルド後に実行するのは `dist_v0_3\Portable Backup Tool\Portable Backup Tool.exe` です。`build_*` 配下は PyInstaller の中間生成物なので直接起動しません。

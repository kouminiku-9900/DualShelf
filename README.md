# Portable Backup Tool

Portable Backup Tool は、Windows 向けの portable バックアップツールです。

`robocopy` をベースに、複数のソースフォルダを 1 つのバックアップ先へまとめて複製できます。写真、音楽、ゲーム資産、ドキュメントなどの個人データ保全を想定しています。

現在の公開バージョンは `v0.3` です。

## 主な機能

- 複数のバックアップ元フォルダを 1 ジョブに登録
- バックアップ先ルートを 1 つ指定してまとめて複製
- `append / mirror / snapshot` の 3 モード対応
- `mirror` 実行前に `robocopy /L` で dry-run を実施
- ミラーモードでは `MIRROR` の明示入力確認を要求
- 実行前確認ダイアログで対象、容量、接続状態を表示
- 実行中の進捗表示
- 実行中キャンセル対応
- 実行ログ保存
- ジョブ設定を JSON で保存
- PyInstaller による portable onedir 配布

## バックアップモード

### `append`

安全重視の追記バックアップです。

- 新規ファイルと更新ファイルをコピー
- 既存ファイルの削除反映はしない
- アーカイブ用途のデフォルト推奨モード

### `mirror`

元と先を一致させる完全同期です。

- 元で削除したファイルは先でも削除される
- 実行前に dry-run を表示
- 強い警告と `MIRROR` 入力確認が必須

### `snapshot`

日時付きフォルダへ保存する世代風バックアップです。

- 例: `F:\Backup\2026-03-22_153000\PSP`
- 過去時点を残したい用途向け
- 容量は多く消費する

## 使い方

1. アプリを起動
1. ジョブを新規作成
1. バックアップ元フォルダを 1 つ以上追加
1. バックアップ先ルートを指定
1. モード、除外設定、ログ設定を確認
1. 実行前確認ダイアログの内容を確認して開始

補足:

- 1 ジョブ内では、ソース末尾フォルダ名が重複する登録はできません
- ミラーモードは削除反映ありの危険操作です
- キャンセル時は「途中までコピーされた分は残る」中断扱いです

## ダウンロードと実行

配布物は GitHub Releases から取得できます。

- Release: [v0.3](https://github.com/kouminiku-9900/DualShelf/releases/tag/v0.3)
- 添付アセット: `Portable_Backup_Tool_v0.3_windows_x64.zip`

展開後に起動するのは `Portable Backup Tool.exe` です。`build_*` 配下は PyInstaller の中間生成物なので直接起動しません。

設定とログは EXE 配下の `data/` に保存されます。

## 開発実行

前提:

- Windows 10 / 11
- Python 3.10 以上
- `robocopy` が利用できる環境

実行:

```powershell
python app/main.py
```

## テスト

```powershell
python -m unittest discover -s tests -v
python -m compileall app tests
```

## onedir ビルド

`PyInstaller` をインストールしてからビルドします。

```powershell
python -m pip install pyinstaller
.\build.ps1
```

`v0.3` のビルド出力先:

```text
dist_v0_3\Portable Backup Tool\Portable Backup Tool.exe
```

## リポジトリ方針

このリポジトリには、配布と再ビルドに必要なものだけを含めています。

- `app/`
- `tests/`
- `build.ps1`
- `README.md`
- `THIRD_PARTY_NOTICES.md`
- `third_party_licenses/`

意図的に含めていないもの:

- `dist*`
- `build*`
- 実行ログ
- `.spec`
- 個人データ、検証用メディア、アーカイブ本体

## ライセンス

リポジトリ本体は [LICENSE](./LICENSE) の条件で公開しています。

Release 配布物には、PyInstaller によってバンドルされる以下のコンポーネントが含まれます。

- Python runtime
- Tcl/Tk runtime
- PyInstaller bootloader / runtime hooks

配布時の通知整理は以下にまとめています。

- [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)
- [third_party_licenses/](./third_party_licenses/)

各配布物には、必要なライセンス通知と本文を同梱してください。

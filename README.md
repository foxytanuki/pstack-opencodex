# pstack-opencodex

[pstack](https://github.com/cursor/plugins/tree/main/pstack)（Cursor公式版）を、opencodex経由のCodexで使うためのビルド用リポジトリです。原版は `upstream/` に無改変で置き、Codex向けの変更は `overlay/` にだけ持ちます。

| 場所 | 中身 |
|---|---|
| `UPSTREAM` | 取り込んだ原版のリポジトリ・パス・コミット |
| `upstream/` | `cursor/plugins/pstack` の完全なコピー。手で編集しない |
| `overlay/HARNESS.md` | Cursorのツール名・パス・モデル名をCodex/opencodexへ対応づける説明 |
| `overlay/patches/` | 文章の書き換えでは足りない修正（現在はLinux対応のみ） |
| `overlay/exclude` | Codexに相当機能がないため生成しないスキル（現在は `make-bot-ui`） |
| `overlay/pstack-models.example.md` | Codexのモデル一覧で解決できるモデル設定の例 |
| `dist/` | `build` の生成物。インストール先からsymlinkで参照する |

`build` は原版に次の変更だけを加えます。

- 各スキルの先頭に `dist/HARNESS.md` を読む1行を追加する（principle-* を除く）。
- 原版の `disable-model-invocation: true` を `agents/openai.yaml` の `allow_implicit_invocation: false` に変換する。
- `Poteto Mode` などの表示名を、`$poteto-mode` で呼べるディレクトリ名にそろえる。
- `overlay/patches/` を適用する。原版の該当行が変わっていたら停止する。

## 原版の更新を取り込む

```bash
python3 tools/pstack_opencodex.py sync          # 最新の原版を取得し、前回からの変更履歴を表示
git diff --stat upstream                    # 原版の差分を確認
python3 tools/pstack_opencodex.py build         # dist/ を再生成
python3 tools/pstack_opencodex.py check-models  # モデル設定が今のCodex一覧で解決できるか確認
git add -A && git commit -m "chore: sync pstack upstream to <sha>"
```

`sync --ref <sha>` で特定の版に固定できます。`check-models` は、原版で廃止・改名された役割の行も報告します。

## インストールと設定

```bash
python3 tools/pstack_opencodex.py build
python3 tools/pstack_opencodex.py install --target <repo>/.agents/skills   # 試行するリポジトリ
cp overlay/pstack-models.example.md ~/.codex/pstack-models.md          # または $setup-pstack で作成
python3 tools/pstack_opencodex.py check-models
```

全リポジトリで使う場合は `--target ~/.agents/skills` を指定します。`uninstall --target <dir>` は `dist/` を指すsymlinkだけを削除します。

モデル設定は `~/.codex/pstack-models.md` に置きます。このホストのCursor CLIが `~/.cursor/rules/` を読むため、Codex用のモデル名はそこに書きません。

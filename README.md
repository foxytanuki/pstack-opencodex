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

## 委譲前の診断

`check-models` はモデル名と推論レベルを確認し、カタログで `disabled` のモデルを拒否します。ClaudeやGrokへ実際に委譲できることは保証しません。別プロバイダーの子エージェントを使う前に、Python 3.11以降で次を実行します。親モデル名は実際の会話のモデルに合わせてください。

```bash
python3 tools/pstack_opencodex.py check-runtime --parent-model gpt-6.1-sol
```

診断は設定とカタログを読むだけです。Codexの `model_catalog_json` を優先し、プロファイルを使う場合は `--profile <name>` を指定します。`--role "how explainer"` などで使う役割だけを診断でき、未使用の役割による阻害を避けられます。`--catalog`、`--codex-config`、`--opencodex-config` で調査対象を明示でき、`--json` で機械可読の結果を出力できます。

| 終了コード | 結果 | 意味 |
| --- | --- | --- |
| 0 | CONFIGURATION_OK | 調べた設定に既知の阻害条件がない。実際の委譲成功は未検証 |
| 1 | BLOCKED | disabledモデル、暗号化タスクの非互換、入力ファイル不正など |
| 2 | INCONCLUSIVE | 既存会話の形式・ルートが不明、設定不一致、実験的対処の動作が未確認など |

既存会話のV1/V2形式は、ディスク上の設定から推定しません。実行中のクライアント・会話の証拠がある場合だけ `--session-surface v1` または `v2` を指定します。opencodexを導入した後やモデルカタログを更新した後は、既存Codexが古い情報を保持することがあります。opencodexの手順に従ってCodexを再起動し、新しい会話で最小の委譲を確認してください。

ネイティブChatGPTのV2親が作る暗号化タスクを、Claudeなどの子が読めない制約があります。[opencodex issue #92](https://github.com/lidge-jun/opencodex/issues/92) を参照してください。`unreadable_encrypted_agent_task` が出た場合、同じ会話でClaudeの別モデルを繰り返し試しても解決しません。V1が反映された新しい会話など、対応した経路で確認します。実験的な平文化・回復設定は自動で有効にしません。タイムアウトとHTTP 429も区別して記録します。

## 検証

```bash
python3 -m unittest discover -s tests -v
python3 tools/pstack_opencodex.py build
```

テストは一時ディレクトリの設定・カタログを使い、V1/V2、disabled、設定と既存会話の不一致、実験的対処、CLIの終了コードと設定を変更しないことを確認します。プロバイダーへの接続は行いません。

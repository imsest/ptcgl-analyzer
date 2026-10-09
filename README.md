# PTCGL 分析ノート — セットアップ手順書

PTCGL（ポケモンカードゲーム Live）のバトルログをAIが1ターンずつ評価し、形勢が傾いた場面で
「打つべきだった手」を教えてくれる自分用アプリです。費用は **0円**（Google の Gemini API 無料枠＋Streamlit の無料ホスティング）。

## できること

| タブ | 機能 |
|---|---|
| ⚔️ ログ解析 | ログを貼る → 各ターンを「優勢／やや優勢／互角／やや劣勢／劣勢」で評価、形勢グラフ表示、形勢が傾いたターンの最善手・代替手順、気になる局面の「深掘り」 |
| 📚 履歴 | 解析した試合の一覧、勝率、相手デッキ別の成績 |
| 🗂 デッキ | デッキ登録（PTCGLのエクスポートをそのまま貼る）、戦い方・展開方法の解説 |
| 🌐 環境 | 環境メモ（AIにGoogle検索で調べさせることも可）、環境を踏まえたデッキアドバイス |

> 評価は「プロの観戦解説」レベルの目安です。相手の手札など見えない情報があるため、確度（高/中/低）も一緒に表示します。

---

## ステップ0：全体の流れ（所要 30〜60分）

1. Python を入れる
2. このフォルダをパソコンに置く
3. 必要なライブラリを入れる
4. Gemini の APIキーを取る（無料）
5. 自分のパソコンで起動して動作確認
6. （任意）ネットに公開してスマホからも使えるようにする

まずは **ステップ5まで**（自分のPCで使う）を目指しましょう。ステップ6は慣れてからで大丈夫です。

---

## ステップ1：Python をインストール

### Windows
1. https://www.python.org/downloads/ を開き、黄色の「Download Python 3.x.x」をクリック
2. ダウンロードしたインストーラを実行
3. **最初の画面の下にある「Add python.exe to PATH」に必ずチェック** → 「Install Now」
4. 確認：スタートメニューで「PowerShell」を開き、次を入力して Enter
   ```
   python --version
   ```
   `Python 3.12.x` のように表示されればOK

### Mac
1. 同じく https://www.python.org/downloads/ からダウンロードしてインストール
2. 確認：「ターミナル」アプリを開き、次を入力
   ```
   python3 --version
   ```
   ※Macでは以降の `python` を `python3`、`pip` を `pip3` と読み替えてください。

---

## ステップ2：アプリのフォルダを置く

受け取った `ptcgl-analyzer.zip` を展開し、わかりやすい場所（例：ドキュメント）に置きます。
中身はこうなっています。

```
ptcgl-analyzer/
├─ app.py                      … 画面
├─ ptcg_core.py                … ログ解析・AI呼び出しの中身
├─ requirements.txt            … 必要なライブラリ一覧
├─ .streamlit/secrets.toml.example … APIキーの設定ひな形
└─ README.md                   … この説明書
```

> `.streamlit` は名前が「.」で始まるため、隠しフォルダになっていることがあります。
> Windows：エクスプローラーの「表示」→「隠しファイル」にチェック／Mac：Finderで `Command + Shift + .`

---

## ステップ3：ライブラリを入れる

PowerShell（Mac はターミナル）で、フォルダに移動してから実行します。

```
cd ~/Documents/ptcgl-analyzer
python -m venv .venv
```

仮想環境（このアプリ専用の部屋）を有効にします。

- Windows：
  ```
  .venv\Scripts\Activate.ps1
  ```
  「スクリプトの実行が無効」と出たら、一度だけ次を実行してから再度上のコマンド：
  ```
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```
- Mac：
  ```
  source .venv/bin/activate
  ```

行頭に `(.venv)` と出れば成功。続けてライブラリを入れます（数分かかります）。

```
pip install -r requirements.txt
```

---

## ステップ4：Gemini の APIキーを取る（無料）

1. https://aistudio.google.com/apikey を開き、Googleアカウントでログイン
2. 利用規約に同意 →「APIキーを作成（Create API key）」
3. 表示されたキー（`AIza...` で始まる長い文字列）をコピー
4. `.streamlit` フォルダの `secrets.toml.example` をコピーして、名前を **`secrets.toml`** に変更
5. メモ帳などで開き、キーを貼り付けて保存
   ```toml
   GEMINI_API_KEY = "AIzaSy..."
   APP_PASSWORD = "好きなパスワード"
   ```

**注意点**
- APIキーは他人に見せない・GitHubに上げない（パスワードと同じ扱い）
- 無料枠には「1分あたり／1日あたりの回数制限」があります。ログ解析は1試合1回の呼び出しなので、普通に使う分には十分です。
  制限は https://aistudio.google.com/rate-limit で確認できます
- 無料枠では、送った内容がGoogleのサービス改善に使われることがあります（ゲームのログなので通常は問題ありません）

---

## ステップ5：起動する

ステップ3と同じ画面（`(.venv)` が出ている状態）で：

```
streamlit run app.py
```

自動でブラウザが開き、`http://localhost:8501` にアプリが表示されます。
（2回目以降は「フォルダに移動 → 仮想環境を有効化 → `streamlit run app.py`」の3つだけ）

終了するときは、PowerShell/ターミナルで `Ctrl + C`。

### 最初にやること
1. パスワードを入力してログイン
2. サイドバーに **自分のPTCGLプレイヤー名** を入力（ログのどちらが自分か判定するため）
3. 「🗂 デッキ」タブでデッキを登録
   - PTCGL：デッキ編集画面 → エクスポート（コピー）→ 貼り付け → 保存
   - 合計が60枚と表示されればOK
4. 「⚔️ ログ解析」タブで試合を解析
   - PTCGL：対戦終了画面 →「バトルログ」→ ログ内で `Ctrl + A` → `Ctrl + C`（Macは `Command`）
   - 貼り付けてデッキを選び「🔍 解析する」
   - 「補足」に「ターン5で手札にボスの指令があった」などを書くと、最善手の精度が上がります

---

## ステップ6（任意）：ネットに公開してスマホから使う

Streamlit Community Cloud（無料）を使います。

### 6-1. GitHub にコードを置く
1. https://github.com でアカウントを作成
2. 右上「＋」→「New repository」
   - Repository name：`ptcgl-analyzer`
   - **Private** を選択（自分だけが見られる）→「Create repository」
3. 作成した画面の「uploading an existing file」リンクをクリックし、次をドラッグ＆ドロップ
   - `app.py`、`ptcg_core.py`、`requirements.txt`、`README.md`、`.gitignore`
   - **`secrets.toml` は絶対にアップロードしない**
4. 「Commit changes」

### 6-2. Streamlit Community Cloud で公開
1. https://share.streamlit.io を開き、「Continue with GitHub」でログイン（GitHubへのアクセスを許可）
2. 「Create app」→「Deploy a public app from GitHub」
3. Repository：`あなたの名前/ptcgl-analyzer`、Branch：`main`、Main file path：`app.py`
4. App URL を好きな名前に
5. **「Advanced settings」→「Secrets」** に `secrets.toml` と同じ内容を貼り付け
   ```toml
   GEMINI_API_KEY = "AIzaSy..."
   APP_PASSWORD = "好きなパスワード"
   ```
   ※公開URLは誰でもアクセスできるので、APP_PASSWORD は必ず設定してください
6. 「Deploy」→ 数分で `https://〇〇.streamlit.app` が使えるようになります

### クラウド版の注意
- 一定期間使わないとスリープします（開いて「起こす」ボタンを押せば復帰）
- **再起動するとデータ（デッキ・履歴）が消えることがあります。**
  サイドバーの「データを書き出す」でこまめにバックアップし、消えたら「データを読み込む」で戻してください
- コードを修正したら、GitHub上のファイルを更新すれば自動で反映されます

---

## 困ったとき

| 症状 | 対処 |
|---|---|
| `python` が見つからない | Windows：インストール時の「Add to PATH」を忘れている → 再インストール。Mac：`python3` を使う |
| `streamlit` が見つからない | 仮想環境が有効になっていない（行頭の `(.venv)` を確認）→ ステップ3の有効化コマンド |
| 「無料枠の利用上限に達しました」 | 1分待つ／翌日に再実行／サイドバーのモデルを `gemini-3.5-flash-lite` に変更 |
| 「モデル名が見つかりません」 | Googleがモデルを更新した可能性。サイドバーで別のモデルを選ぶか「その他」で最新名を入力（https://ai.google.dev/gemini-api/docs/models で確認） |
| 「プレイヤー名がログに見つかりません」 | サイドバーの名前をログ上の表記と完全に一致させる |
| ターンの区切りを判定できない | そのまま解析してOK（AIが自力で読みます）。気になる場合はログを添えて相談してください |
| 環境の自動調査でエラー | 検索機能がその時点の無料枠で使えない可能性。Limitless TCG などを見て手動でメモしてください |

---

## カスタマイズのヒント

- 評価の厳しさや観点を変えたい → `ptcg_core.py` の `SYSTEM_PROMPT` を編集
- 出力項目を増やしたい → `ptcg_core.py` の `TurnEval` / `SwingPoint` / `GameAnalysis` に項目を追加し、`app.py` の `render_analysis` で表示

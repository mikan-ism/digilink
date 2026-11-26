# DIGI LINK｜デジモン交流掲示板

初代『デジモンアドベンチャー』が好きな高校生のための掲示板。Flask、Jinja2、HTML、CSS、JavaScriptで作成しています。

## ローカルで起動

Windows PowerShellで実行します。仮想環境の有効化は不要です。

```powershell
cd C:\DigiLink
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

準備済みの場合は最後のコマンドだけで起動できます。ブラウザーで http://127.0.0.1:5000 を開きます。停止は `Ctrl+C`。開発用サーバーは自分のパソコンだけでアクセスできます。

ローカル起動時に `data/posts.json` と `static/uploads/` を自動作成します。投稿はJSON、画像はuploadsに残ります。例の4件は `app.py` 内の `SAMPLES` で管理し、すべて「サンプル」と表示します。実際の投稿データとは区別しています。

`local-art/` は初代の集合絵と立ち絵を使った画面確認用です。公開用ソースには含めません。出典と使用条件の確認先は `ASSETS.md` に記載しています。

## 確認

```powershell
cd C:\DigiLink
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

テストは一時ディレクトリを使うため、実際の投稿を変更しません。ローカル実行環境はPython 3.13.3。Azureの対象はPython 3.12です。GunicornはLinuxだけにインストールします。

## 保存先の切り替え

| 環境変数 | 用途 |
| --- | --- |
| `AZURE_STORAGE_CONNECTION_STRING` | 未設定・空ならローカル。設定するとTable／Blobを使用。実際の値はソースに記載しない。 |
| `SECRET_KEY` | セッション署名用の十分長いランダムな文字列。Azureでは必須。ローカルではdata内に自動生成し、Git対象外にする。 |

Azureでは `posts` テーブルと非公開の `digilink-images` コンテナーを使用します。存在しない場合は起動時に作成します。作成・読み書きの権限と接続可能なネットワークが必要です。接続失敗時は起動エラーになり、ローカル保存には切り替えません。画像は `/media/<ファイル名>` からFlaskが読み出すため、ストレージの認証情報はブラウザーに送りません。

投稿画像は実際の形式、拡張子、MIME、サイズ、画素数を確認し、再エンコードします。JPEG・PNG・WebPの静止画のみ、元ファイル5MB・2,000万画素までです。長辺2,400pxまで縮小し、EXIFなどの情報を除去します。投稿失敗時は保存済み画像の削除を試みます。画像の選択ミスや保存エラー時は文字入力を再表示します。

この課題版にはログイン、返信、管理画面を設けていません。投稿は公開を前提とします。不要な投稿は公開後に保存先から管理者が削除します。大量データを扱うためのページ分割は対象外です。

## Azureへの公開手順（まだ実施していません）

1. `mikan-ism/digilink` をPublicで作成し、公開用ソースを `main` にpushします。GitHub Freeと標準のGitHubホストランナー（例 `ubuntu-latest`）を使います。公開用ZIPを使う場合は、展開後に `app.py` があるフォルダーをリポジトリのルートにします。氏名入りの `requirements.md` はTeams提出用で、公開リポジトリには含めません。ローカル投稿は自動移行しません。
2. 学校のAzure for Studentsサブスクリプションで、まずJapan EastのLinux F1が選べるかポータルで確認します。他の許可リージョンも確認し、F1が見つからない場合は、利用制限・クォータ・価格を確認してから有料プランを判断します。CLIを使える場合は `az appservice list-locations --sku F1 --linux-workers-enabled -o table` も参考になります。実際のF1利用可否はポータルのサブスクリプションとリージョン選択で確認します。
3. 承認後、課題用の `IA42A-03-DigiLink` リソースグループに以下を作成します。

   | 項目 | 設定 |
   | --- | --- |
   | App Service | `ia42a03digilink`（空き状況により変更）、Linux、Python 3.12、Free F1 |
   | Storageアカウント | `ia42a03digilink`（空き状況により変更）、StorageV2、Standard、LRS、Hot |
   | Table / Blob | 同じStorageアカウントの `posts` と `digilink-images`。コンテナーはPrivate、Blob匿名アクセスは無効。 |

   F1のコンピューティング料金は無料です。Storageの保存量・操作・転送には課金される場合があるため、契約のクレジットと対象リージョンの見積もりを先に確認します。

4. App Serviceの環境変数に `AZURE_STORAGE_CONNECTION_STRING` と `SECRET_KEY` を設定します。接続文字列とセッション署名用のランダム値はApp Serviceにのみ設定します。`SECRET_KEY` は `python -c "import secrets; print(secrets.token_hex(32))"` などで生成できます。App Serviceの起動コマンドは次のとおりです。

   ```text
   gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 2 --timeout 120 'app:create_app()'
   ```

5. Deployment CenterでGitHub・`mikan-ism/digilink`・`main` を指定し、可能ならユーザー割り当てIDによるOpenID Connect認証を使います。生成されたActionsのGitHubホストランナー、Python 3.12、対象アプリを確認します。認証情報をYAMLやソースに書きません。学校の権限でOIDCを設定できない場合は、授業で指定された方法を確認します。
6. `app.py` と `requirements.txt` が直下にあるソースをデプロイします。ソースZIPの依存関係をApp Serviceでビルドする構成では `SCM_DO_BUILD_DURING_DEPLOYMENT=true` を設定します。GitHub側で依存関係をビルドする構成なら、生成されたワークフローに従い、Windows用の仮想環境や `local-art/` を含めません。
7. HTTPSのみを有効にし、公開サイトのフォームから `demo-materials/` のデモ原稿を投稿します。文字投稿を `posts` テーブルで、画像を `digilink-images` で確認し、ページ上の表示と `/media/` の画像を確認します。再読み込みとApp Service再起動の後も投稿・画像を再取得できること、カテゴリー切り替えとパートナー選択が動くことを確認します。
8. 小さなソース変更をpushしてActionsの成功とサイトへの反映を確認します。確認した実装レベルと実際のサイトURL・GitHub URLを `requirements.md` に記入し、Teamsに提出します。

Azureの接続・公開・自動公開は現在未検証です。レベル2のApp Service公開が完了したと報告するのは実際の公開確認後です。最終版は静的HTML/CSS/画像を含むFlaskアプリとして同じApp Serviceから配信します。別の静的版の提出が必要かは授業の採点方法に合わせて確認してください。

参考：[Pythonアプリの構成](https://learn.microsoft.com/en-us/azure/app-service/configure-language-python)、[GitHub Actionsによる公開](https://learn.microsoft.com/en-us/azure/app-service/deploy-github-actions)、[Linux App Service料金](https://azure.microsoft.com/en-us/pricing/details/app-service/linux/)、[Azure料金計算ツール](https://azure.microsoft.com/en-us/pricing/calculator/)。

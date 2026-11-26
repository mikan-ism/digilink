import io
import json
import os
import re
import secrets
import warnings
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

from filelock import FileLock
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError

BASE_DIR = Path(__file__).resolve().parent
MAX_IMAGE_BYTES = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
CATEGORIES = ['アニメ', '進化', 'ゲーム', 'イラスト', 'グッズ', '雑談']
PARTNERS = [
    {'id': 'agumon', 'name': 'アグモン', 'human': '八神太一', 'color': '#e89832', 'description': '勇気を出して、一歩先へ。好奇心いっぱいのパートナー。'},
    {'id': 'gabumon', 'name': 'ガブモン', 'human': '石田ヤマト', 'color': '#6d97bd', 'description': '大切な友だちのそばに。やさしく頼れるパートナー。'},
    {'id': 'piyomon', 'name': 'ピヨモン', 'human': '武之内空', 'color': '#d8809d', 'description': '好きな気持ちをまっすぐに。人なつっこいパートナー。'},
    {'id': 'tentomon', 'name': 'テントモン', 'human': '泉光子郎', 'color': '#c86a64', 'description': '気になることを調べよう。知る楽しさを分かち合うパートナー。'},
    {'id': 'palmon', 'name': 'パルモン', 'human': '太刀川ミミ', 'color': '#83a866', 'description': '自分らしさを大切に。のびのび過ごすパートナー。'},
    {'id': 'gomamon', 'name': 'ゴマモン', 'human': '城戸丈', 'color': '#85aaa9', 'description': 'ひと休みも冒険のうち。明るく気さくなパートナー。'},
    {'id': 'patamon', 'name': 'パタモン', 'human': '高石タケル', 'color': '#d9a05f', 'description': '小さな一歩に希望を込めて。がんばり屋のパートナー。'},
    {'id': 'tailmon', 'name': 'テイルモン', 'human': '八神ヒカリ', 'color': '#9b8ab5', 'description': '自分のペースで進もう。芯の強いパートナー。'},
]
PARTNER_MAP = {p['id']: p for p in PARTNERS}
SAMPLES = [
    {'id': 'sample-4', 'nickname': 'そらいろ', 'partner': 'patamon', 'category': '進化', 'title': 'パタモンの進化が一番好き！', 'body': 'いつも小さくてかわいいのに、進化したときの頼もしさがすごい。\nみんなは初代のどの進化シーンが好き？', 'created_at': '2026-11-25T08:10:00+00:00', 'image': '', 'sample': True},
    {'id': 'sample-3', 'nickname': 'らくがきノート', 'partner': 'agumon', 'category': 'イラスト', 'title': '放課後にパートナーを描いてみた', 'body': 'ノートのすみに、小さな恐竜を描いてみました。\nアグモンみたいな元気な雰囲気を出したい。次は色鉛筆でも描いてみようかな。', 'created_at': '2026-11-25T07:45:00+00:00', 'image': 'sample-sketch.svg', 'sample': True},
    {'id': 'sample-2', 'nickname': 'やま', 'partner': 'gabumon', 'category': 'アニメ', 'title': '初代を久しぶりに見返した', 'body': '最初の島の雰囲気がやっぱり好き。公衆電話が並んでいる風景、不思議だけど妙に覚えてる。\n今日は帰ってから続きを見る予定。', 'created_at': '2026-11-24T09:20:00+00:00', 'image': '', 'sample': True},
    {'id': 'sample-1', 'nickname': 'まめ', 'partner': 'tentomon', 'category': 'ゲーム', 'title': 'おすすめのデジモンゲームを教えて！', 'body': '育成をのんびり楽しめるゲームを探しています。\n遊んだことがある作品や、好きなところを教えてほしいです。', 'created_at': '2026-11-24T07:30:00+00:00', 'image': '', 'sample': True},
]
LOCAL_ART_DIR = BASE_DIR / 'local-art'


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=MAX_IMAGE_BYTES + 256 * 1024,
        DATA_DIR=BASE_DIR / 'data', UPLOAD_DIR=BASE_DIR / 'static' / 'uploads',
        AZURE_CONNECTION=os.environ.get('AZURE_STORAGE_CONNECTION_STRING', ''),
        SECRET_KEY=os.environ.get('SECRET_KEY'),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=bool(os.environ.get('WEBSITE_HOSTNAME')),
    )
    if test_config:
        app.config.update(test_config)
    azure = bool(app.config['AZURE_CONNECTION'])
    if os.environ.get('WEBSITE_HOSTNAME') and not azure:
        raise RuntimeError('App Service では AZURE_STORAGE_CONNECTION_STRING を設定してください。')
    table = container = None
    data_dir = Path(app.config['DATA_DIR'])
    uploads = Path(app.config['UPLOAD_DIR'])
    posts_file = data_dir / 'posts.json'

    if azure:
        if not app.config['SECRET_KEY']:
            raise RuntimeError('Azure モードでは環境変数 SECRET_KEY を設定してください。')
        try:
            from azure.data.tables import TableServiceClient
            from azure.storage.blob import BlobServiceClient
            from azure.core.exceptions import ResourceExistsError
            table = TableServiceClient.from_connection_string(app.config['AZURE_CONNECTION']).create_table_if_not_exists('posts')
            container = BlobServiceClient.from_connection_string(app.config['AZURE_CONNECTION']).get_container_client('digilink-images')
            try:
                container.create_container()
            except ResourceExistsError:
                pass
            container.get_container_properties()
        except Exception:
            raise RuntimeError('Azure Storage に接続できません。接続設定・権限・ネットワークを確認してください。ローカルには切り替えません。') from None
    else:
        data_dir.mkdir(parents=True, exist_ok=True)
        uploads.mkdir(parents=True, exist_ok=True)
        with FileLock(str(data_dir / 'posts.lock')):
            if not posts_file.exists():
                posts_file.write_text('[]\n', encoding='utf-8')
            if not app.config['SECRET_KEY']:
                secret_file = data_dir / '.session-secret'
                if not secret_file.exists():
                    secret_file.write_text(secrets.token_hex(32), encoding='ascii')
                app.config['SECRET_KEY'] = secret_file.read_text(encoding='ascii').strip()

    def read_posts():
        if azure:
            return [{**dict(p), 'id': p['RowKey']} for p in table.query_entities("PartitionKey eq 'posts'")]
        with FileLock(str(data_dir / 'posts.lock')):
            return json.loads(posts_file.read_text(encoding='utf-8'))

    def save_post(post):
        if azure:
            table.create_entity({'PartitionKey': 'posts', 'RowKey': post['id'], **post})
        else:
            # 同時投稿で上書きしないように、読み込みから保存までロックする。
            with FileLock(str(data_dir / 'posts.lock')):
                posts = json.loads(posts_file.read_text(encoding='utf-8'))
                posts.append(post)
                temporary = posts_file.with_suffix('.tmp')
                temporary.write_text(json.dumps(posts, ensure_ascii=False, indent=2), encoding='utf-8')
                os.replace(temporary, posts_file)

    def store_image(name, content, mime):
        if azure:
            from azure.storage.blob import ContentSettings
            container.upload_blob(name, content, overwrite=False, content_settings=ContentSettings(content_type=mime))
        else:
            (uploads / name).write_bytes(content)

    def remove_image(name):
        if azure:
            container.delete_blob(name)
        else:
            (uploads / name).unlink(missing_ok=True)

    @app.template_filter('jst')
    def jst(value):
        return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=9))).strftime('%Y.%m.%d %H:%M')

    @app.context_processor
    def common():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_urlsafe(32)
        return {'partners': PARTNERS, 'partner_map': PARTNER_MAP, 'categories': CATEGORIES,
                'local_art_url': local_art_url}

    def can_show_local_art():
        return not azure and not os.environ.get('WEBSITE_HOSTNAME') and request.remote_addr in {'127.0.0.1', '::1'}

    def local_art_url(name):
        if can_show_local_art() and (LOCAL_ART_DIR / name).is_file():
            return url_for('local_art', name=name)
        return None

    @app.get('/local-art/<name>')
    def local_art(name):
        # 作品画像はローカルの画面確認のみで使う。
        filenames = {'hero.webp', 'tailmon-scene.webp', *(p['id'] + '.webp' for p in PARTNERS)}
        if not can_show_local_art() or name not in filenames or not (LOCAL_ART_DIR / name).is_file():
            abort(404)
        return send_file(LOCAL_ART_DIR / name, mimetype='image/webp', max_age=0)

    def page(errors=None, form=None, status=200):
        selected_category = request.args.get('category', 'すべて')
        if selected_category not in ['すべて', *CATEGORIES]:
            selected_category = 'すべて'
        try:
            all_posts = sorted([*SAMPLES, *read_posts()], key=lambda p: p['created_at'], reverse=True)
        except Exception:
            return render_template('error.html', message='投稿を読み込めませんでした。保存先の設定を確認してください。'), 503
        posts = [p for p in all_posts if selected_category == 'すべて' or p['category'] == selected_category]
        counts = {c: sum(p['category'] == c for p in all_posts) for c in CATEGORIES}
        return render_template('index.html', posts=posts, total=len(all_posts), counts=counts,
                               selected_category=selected_category, errors=errors or [], form=form or {}), status

    @app.get('/')
    def index():
        return page()

    @app.post('/posts')
    def submit():
        token = request.form.get('csrf_token', '')
        if not token or not secrets.compare_digest(token, session.get('csrf_token', '')):
            return page(['ページの有効期限が切れました。もう一度投稿してください。'], request.form, 400)
        form = {key: request.form.get(key, '').strip() for key in ['nickname', 'partner', 'category', 'title', 'body']}
        errors = []
        for field, label, limit in [('nickname', 'ニックネーム', 24), ('title', 'タイトル', 80), ('body', '本文', 2000)]:
            if field != 'nickname' and not form[field]:
                errors.append(f'{label}を入力してください。')
            if len(form[field]) > limit:
                errors.append(f'{label}は{limit}文字以内で入力してください。')
        if form['partner'] not in PARTNER_MAP:
            errors.append('パートナーを選んでください。')
        if form['category'] not in CATEGORIES:
            errors.append('カテゴリーを選んでください。')
        photo = request.files.get('image')
        image_data = None
        if photo and photo.filename:
            try:
                image_data = validate_image(photo)
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            return page(errors, form, 400)
        post = {**form, 'nickname': form['nickname'] or '名無しのテイマー', 'id': uuid4().hex,
                'created_at': datetime.now(timezone.utc).isoformat(), 'image': '', 'sample': False}
        try:
            if image_data:
                content, extension, mime = image_data
                post['image'] = f'{uuid4().hex}.{extension}'
                store_image(post['image'], content, mime)
            save_post(post)
        except Exception:
            if post['image']:
                try:
                    remove_image(post['image'])
                except Exception:
                    app.logger.error('投稿失敗後の画像削除に失敗しました。')
            return page(['投稿を保存できませんでした。保存先を確認して、もう一度お試しください。'], form, 503)
        flash('投稿しました。パートナーと一緒に、交流を楽しもう。')
        return redirect(url_for('index') + '#board', code=303)

    @app.get('/media/<name>')
    def media(name):
        if not re.fullmatch(r'[a-f0-9]{32}\.(jpg|png|webp)', name):
            abort(404)
        mime = {'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}[name.rsplit('.', 1)[1]]
        if azure:
            from azure.core.exceptions import ResourceNotFoundError
            try:
                content = container.download_blob(name).readall()
            except ResourceNotFoundError:
                abort(404)
            except Exception:
                abort(503)
            return send_file(io.BytesIO(content), mimetype=mime, max_age=86400)
        if not (uploads / name).is_file():
            abort(404)
        return send_file(uploads / name, mimetype=mime, max_age=86400)

    @app.errorhandler(413)
    def too_large(_error):
        return render_template('error.html', message='画像は5MB以下にしてください。入力内容はブラウザーの「戻る」で確認できます。'), 413

    @app.after_request
    def security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        return response

    return app


def validate_image(photo):
    content = photo.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError('画像は5MB以下にしてください。')
    formats = {'JPEG': ('jpg', 'image/jpeg', {'.jpg', '.jpeg'}), 'PNG': ('png', 'image/png', {'.png'}), 'WEBP': ('webp', 'image/webp', {'.webp'})}
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as original:
                detected = original.format
                if detected not in formats:
                    raise ValueError('JPEG・PNG・WebP形式の画像を選んでください。')
                extension, mime, suffixes = formats[detected]
                if Path(photo.filename).suffix.lower() not in suffixes or photo.mimetype != mime:
                    raise ValueError('画像の拡張子・種類と実際の内容が一致しません。')
                if getattr(original, 'n_frames', 1) > 1:
                    raise ValueError('アニメーション画像は使用できません。静止画を選んでください。')
                original.verify()
            with Image.open(io.BytesIO(content)) as original:
                original.load()
                cleaned = ImageOps.exif_transpose(original).convert('RGB' if detected == 'JPEG' else 'RGBA')
                cleaned.thumbnail((2400, 2400))
                output = io.BytesIO()
                # 位置情報などのメタデータを引き継がず、画像だけを保存する。
                cleaned.save(output, format=detected)
                return output.getvalue(), extension, mime
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('画像を読み込めませんでした。有効な画像（2,000万画素以下）を選んでください。') from None


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5000, debug=False)

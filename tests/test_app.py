import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from app import create_app, MAX_IMAGE_BYTES


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = {'TESTING': True, 'DATA_DIR': self.root / 'data', 'UPLOAD_DIR': self.root / 'uploads', 'AZURE_CONNECTION': '', 'SECRET_KEY': 'test-only-key'}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.client.get('/')

    def tearDown(self):
        self.temp.cleanup()

    def post(self, client=None, **changes):
        client = client or self.client
        client.get('/')
        with client.session_transaction() as session:
            token = session['csrf_token']
        data = {'csrf_token': token, 'nickname': '', 'partner': 'patamon', 'category': '進化', 'title': 'テストの題名', 'body': '日本語の本文\n二行目です。'}
        data.update(changes)
        response = client.post('/posts', data=data, buffered=True)
        response.close()
        response.request.environ['wsgi.input'].close()
        return response

    def posts(self):
        return json.loads((self.root / 'data' / 'posts.json').read_text(encoding='utf-8'))

    def image(self, format='PNG', size=(32, 32)):
        output = io.BytesIO()
        Image.new('RGB', size, 'orange').save(output, format=format)
        output.seek(0)
        return output

    def test_page_assets_and_japanese(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('放課後、', html)
        self.assertEqual(html.count('class="sample-label"'), 4)
        self.assertIn('2026.11.25 17:10', html)
        for filename in re.findall(r'(?:src|href)="(/static/[^"?]+)"', html):
            with self.client.get(filename) as asset:
                self.assertEqual(asset.status_code, 200, filename)

    def test_text_default_name_partner_and_order(self):
        self.assertEqual(self.post().status_code, 303)
        self.assertEqual(self.post(title='最新投稿', partner='tailmon').status_code, 303)
        posts = self.posts()
        self.assertEqual(posts[0]['nickname'], '名無しのテイマー')
        self.assertEqual(posts[1]['partner'], 'tailmon')
        html = self.client.get('/').get_data(as_text=True)
        self.assertLess(html.index('最新投稿</h3>'), html.index('テストの題名</h3>'))

    def test_all_partners_and_categories(self):
        from app import PARTNERS, CATEGORIES
        for i, partner in enumerate(PARTNERS):
            self.assertEqual(self.post(partner=partner['id'], category=CATEGORIES[i % 6]).status_code, 303)
        self.assertEqual(len(self.posts()), 8)

    def test_filter_and_empty_state(self):
        self.post(title='進化だけの投稿')
        anime = self.client.get('/?category=アニメ').get_data(as_text=True)
        self.assertNotIn('進化だけの投稿', anime)
        self.assertIn('初代を久しぶりに見返した', anime)
        self.assertIn('まだ投稿がありません', self.client.get('/?category=グッズ').get_data(as_text=True))

    def test_required_and_length_limits(self):
        for changes in [{'title': '   '}, {'body': '\n '}, {'nickname': 'あ' * 25}, {'title': 'あ' * 81}, {'body': 'あ' * 2001}, {'partner': 'wrong'}, {'category': 'wrong'}]:
            with self.subTest(changes=list(changes)):
                self.assertEqual(self.post(**changes).status_code, 400)
        self.assertEqual(self.posts(), [])

    def test_html_is_escaped(self):
        self.post(title='<script>alert(1)</script>', body='<img src=x onerror=alert(1)>', nickname='<b>名前</b>')
        html = self.client.get('/').get_data(as_text=True)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertNotIn('<img src=x', html)

    def test_csrf_rejected(self):
        self.assertEqual(self.client.post('/posts', data={'title': 'a'}).status_code, 400)
        self.assertEqual(self.post(csrf_token='wrong').status_code, 400)
        self.assertEqual(self.posts(), [])

    def test_valid_image_formats_and_safe_names(self):
        for format, extension, mime in [('JPEG', 'jpg', 'image/jpeg'), ('PNG', 'png', 'image/png'), ('WEBP', 'webp', 'image/webp')]:
            with self.subTest(format=format):
                self.assertEqual(self.post(image=(self.image(format), f'../../日本語.{extension}', mime)).status_code, 303)
                name = self.posts()[-1]['image']
                self.assertRegex(name, r'^[a-f0-9]{32}\.' + extension + '$')
                response = self.client.get('/media/' + name)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, mime)
                Image.open(io.BytesIO(response.data)).verify()
                response.close()

    def test_invalid_mismatch_and_oversize_images(self):
        invalid = [(io.BytesIO(b'not an image'), 'test.png', 'image/png'), (self.image(), 'test.jpg', 'image/jpeg'), (self.image(), 'test.png', 'text/html'), (io.BytesIO(b'x' * (MAX_IMAGE_BYTES + 1)), 'large.png', 'image/png')]
        for upload in invalid:
            self.assertEqual(self.post(image=upload).status_code, 400)
        self.assertEqual(self.posts(), [])
        self.assertEqual(list((self.root / 'uploads').iterdir()), [])

    def test_request_size_limit(self):
        self.assertEqual(self.post(image=(io.BytesIO(b'x' * (6 * 1024 * 1024)), 'large.png', 'image/png')).status_code, 413)

    def test_pixel_limit(self):
        with patch('app.Image.MAX_IMAGE_PIXELS', 10):
            self.assertEqual(self.post(image=(self.image(size=(10, 10)), 'large.png', 'image/png')).status_code, 400)

    def test_animation_rejected(self):
        output = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(output, 'PNG', save_all=True, append_images=[Image.new('RGB', (8, 8), 'blue')], duration=100)
        output.seek(0)
        self.assertEqual(self.post(image=(output, 'animation.png', 'image/png')).status_code, 400)

    def test_refresh_restart_and_image_persistence(self):
        self.post(image=(self.image(), 'test.png', 'image/png'))
        name = self.posts()[0]['image']
        self.assertIn('テストの題名', self.client.get('/').get_data(as_text=True))
        restarted = create_app(self.config).test_client()
        self.assertIn('テストの題名', restarted.get('/').get_data(as_text=True))
        with restarted.get('/media/' + name) as response:
            self.assertEqual(response.status_code, 200)
        # 別プロセスからも保存済みの投稿と画像を読み込めることを確認する。
        code = "from app import create_app; from pathlib import Path; import sys; a=create_app({'TESTING':True,'AZURE_CONNECTION':'','SECRET_KEY':'test','DATA_DIR':Path(sys.argv[1]),'UPLOAD_DIR':Path(sys.argv[2])}); c=a.test_client(); assert c.get('/').status_code==200; assert c.get('/media/'+sys.argv[3]).status_code==200"
        result = subprocess.run([sys.executable, '-c', code, str(self.root / 'data'), str(self.root / 'uploads'), name], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_concurrent_posts(self):
        def submit(i):
            return self.post(client=self.app.test_client(), title=f'投稿{i}').status_code
        with ThreadPoolExecutor(max_workers=4) as executor:
            self.assertEqual(list(executor.map(submit, range(8))), [303] * 8)
        self.assertEqual(len(self.posts()), 8)

    def test_corrupt_storage_does_not_reset_data(self):
        path = self.root / 'data' / 'posts.json'
        path.write_text('{broken', encoding='utf-8')
        self.assertEqual(self.client.get('/').status_code, 503)
        self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_media_rejects_bad_name(self):
        self.assertEqual(self.client.get('/media/evil.html').status_code, 404)
        self.assertEqual(self.client.get('/media/' + 'a' * 32 + '.png').status_code, 404)

    def test_azure_bad_config_never_falls_back(self):
        with self.assertRaisesRegex(RuntimeError, 'ローカルには切り替えません'):
            create_app({**self.config, 'AZURE_CONNECTION': 'invalid-connection'})
        self.assertEqual(self.posts(), [])


if __name__ == '__main__':
    unittest.main()

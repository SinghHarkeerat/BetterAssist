"""Private, same-origin analytics and feedback API. No third-party tracking."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
PRIVATE_DIR = Path(os.environ.get('BETTERASSIST_PRIVATE_DIR', Path.home() / '.betterassist-private')).resolve()
MAX_BODY = 8192
SESSION_SECONDS = 3600


def password_hash(code, salt):
    return hashlib.scrypt(code.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def configure_admin(code, directory=PRIVATE_DIR):
    directory = Path(directory).resolve()
    if directory == ROOT or ROOT in directory.parents:
        raise ValueError('Private storage must be outside the website directory.')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    config_path = directory / 'secrets.json'
    existing = json.loads(config_path.read_text()) if config_path.exists() else {}
    salt = secrets.token_hex(16)
    config = {**existing, 'salt': salt, 'code_hash': password_hash(code, salt),
              'key': existing.get('key', secrets.token_hex(32))}
    config_path.write_text(json.dumps(config), encoding='utf-8')
    config_path.chmod(0o600)
    db = directory / 'engagement.sqlite3'
    if db.exists():
        connection = sqlite3.connect(db)
        try:
            with connection:
                connection.execute('DELETE FROM sessions')
        finally:
            connection.close()


class Engagement:
    def __init__(self, directory=PRIVATE_DIR):
        self.directory = Path(directory).resolve()
        if self.directory == ROOT or ROOT in self.directory.parents:
            raise ValueError('Private storage must be outside the website directory.')

    def connect(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(self.directory / 'engagement.sqlite3', timeout=10)
        db.row_factory = sqlite3.Row
        db.executescript('''
            CREATE TABLE IF NOT EXISTS visitors (id TEXT PRIMARY KEY, first_seen TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS visits (event TEXT PRIMARY KEY, visitor TEXT NOT NULL, day TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS visits_day ON visits(day);
            CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, rating INTEGER, message TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS limits (bucket TEXT NOT NULL, at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS limits_bucket ON limits(bucket, at);
        ''')
        return db

    def dispatch(self, method, path, headers, body, client_ip, origin):
        """Return (status, response headers, JSON bytes). Secrets load on each request."""
        extra = []

        def respond(data, status=200):
            return status, [('Content-Type', 'application/json; charset=utf-8'),
                            ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'), *extra], json.dumps(data).encode()

        config_path = self.directory / 'secrets.json'
        if not config_path.exists():
            return respond({'error': 'Visitor services are not connected yet. Please try again later.'}, 503)
        config = json.loads(config_path.read_text(encoding='utf-8'))
        if not all(k in config for k in ('key', 'salt', 'code_hash')):
            return respond({'error': 'Visitor services are unavailable.'}, 503)
        headers = {k.lower(): v for k, v in headers.items()}
        secure = origin.startswith('https://')
        host = urlsplit(origin).hostname
        if not secure and host not in ('localhost', '127.0.0.1', '::1'):
            return respond({'error': 'A secure HTTPS connection is required.'}, 403)
        if method == 'POST':
            if headers.get('origin') != origin or headers.get('sec-fetch-site') == 'cross-site':
                return respond({'error': 'This request must come from Better Assist.'}, 403)
            if headers.get('content-type', '').split(';')[0].strip() != 'application/json':
                return respond({'error': 'Expected JSON.'}, 415)
            if len(body) > MAX_BODY:
                return respond({'error': 'Request is too large.'}, 413)
            try:
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ValueError()
            except (ValueError, UnicodeDecodeError):
                return respond({'error': 'Invalid request.'}, 400)
        else:
            payload = {}

        cookie = SimpleCookie()
        try:
            cookie.load(headers.get('cookie', ''))
        except Exception:
            pass

        def cookie_value(name):
            return cookie[name].value if name in cookie else ''

        def set_cookie(name, value, age):
            extra.append(('Set-Cookie', f'{name}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}' + ('; Secure' if secure else '')))

        def digest(value):
            return hmac.new(bytes.fromhex(config['key']), value.encode(), hashlib.sha256).hexdigest()

        def valid_id(value):
            return isinstance(value, str) and len(value) == 36 and all(c in '0123456789abcdef-' for c in value)

        db = self.connect()
        try:
            # Serialize writes, including rate checks, across threads/processes.
            db.execute('BEGIN IMMEDIATE')
            now = time.time()
            day = datetime.now(timezone.utc).date().isoformat()
            db.execute('DELETE FROM limits WHERE at < ?', (now - 3600,))
            db.execute('DELETE FROM sessions WHERE expires <= ?', (now,))

            def limited(name, limit, seconds):
                bucket = digest(name)
                count = db.execute('SELECT COUNT(*) FROM limits WHERE bucket=? AND at>?', (bucket, now - seconds)).fetchone()[0]
                if count >= limit:
                    extra.append(('Retry-After', str(seconds)))
                    return True
                db.execute('INSERT INTO limits VALUES (?, ?)', (bucket, now))
                return False

            session = cookie_value('ba_admin')
            authenticated = bool(session and db.execute('SELECT 1 FROM sessions WHERE token=? AND expires>?', (digest(session), now)).fetchone())
            if path == '/api/admin/login' and method == 'POST':
                if limited('login:' + client_ip, 5, 900) or limited('login:global', 50, 3600):
                    return respond({'error': 'Too many login attempts. Try again later.'}, 429)
                code = payload.get('code', '')
                if not isinstance(code, str) or len(code) > 128 or not hmac.compare_digest(password_hash(code, config['salt']), config['code_hash']):
                    return respond({'error': 'That login code is incorrect.'}, 401)
                db.execute('DELETE FROM limits WHERE bucket=?', (digest('login:' + client_ip),))
                if session:
                    db.execute('DELETE FROM sessions WHERE token=?', (digest(session),))
                token = secrets.token_urlsafe(32)
                db.execute('INSERT INTO sessions VALUES (?, ?)', (digest(token), now + SESSION_SECONDS))
                set_cookie('ba_admin', token, SESSION_SECONDS)
                return respond({'ok': True})

            if path.startswith('/api/admin/'):
                if not authenticated:
                    return respond({'error': 'Please log in to view the dashboard.'}, 401)
                if path == '/api/admin/logout' and method == 'POST':
                    db.execute('DELETE FROM sessions WHERE token=?', (digest(session),))
                    set_cookie('ba_admin', '', 0)
                    return respond({'ok': True})
                if path == '/api/admin/stats' and method == 'GET':
                    today = datetime.now(timezone.utc).date()
                    since = (today - timedelta(days=29)).isoformat()
                    daily = {r['day']: dict(r) for r in db.execute('SELECT day, COUNT(*) AS views, COUNT(DISTINCT visitor) AS visitors FROM visits WHERE day>=? GROUP BY day', (since,))}
                    days = []
                    for offset in range(29, -1, -1):
                        date = (today - timedelta(days=offset)).isoformat()
                        days.append(daily.get(date, {'day': date, 'views': 0, 'visitors': 0}))
                    ratings = [dict(r) for r in db.execute('SELECT rating, COUNT(*) AS count FROM feedback WHERE rating IS NOT NULL GROUP BY rating ORDER BY rating')]
                    return respond({'views': db.execute('SELECT COUNT(*) FROM visits').fetchone()[0],
                                    'visitors': db.execute('SELECT COUNT(*) FROM visitors').fetchone()[0],
                                    'today': days[-1]['views'], 'days': days, 'ratings': ratings,
                                    'feedbackCount': db.execute('SELECT COUNT(*) FROM feedback').fetchone()[0],
                                    'feedback': [dict(r) for r in db.execute('SELECT rating, message, created FROM feedback ORDER BY created DESC, rowid DESC LIMIT 50')]})

            if path == '/api/privacy' and method == 'POST':
                set_cookie('ba_visitor', '', 0)
                return respond({'ok': True})

            if path == '/api/traffic' and method == 'POST':
                if payload.get('consent') is not True or not valid_id(payload.get('eventId')):
                    return respond({'error': 'Analytics consent and an event ID are required.'}, 400)
                if limited('traffic:' + client_ip, 120, 60):
                    return respond({'error': 'Please try again in a minute.'}, 429)
                if db.execute('SELECT 1 FROM visits WHERE event=?', (payload['eventId'],)).fetchone():
                    return respond({'ok': True})
                # Signed random cookie identifies a browser, never a name or IP address.
                parts = cookie_value('ba_visitor').split('.')
                if len(parts) == 2 and len(parts[0]) == 43 and hmac.compare_digest(digest('visitor:' + parts[0]), parts[1]):
                    visitor_token = parts[0]
                else:
                    visitor_token = secrets.token_urlsafe(32)
                set_cookie('ba_visitor', visitor_token + '.' + digest('visitor:' + visitor_token), 31536000)
                visitor = digest(visitor_token)
                db.execute('INSERT OR IGNORE INTO visitors VALUES (?, ?)', (visitor, day))
                db.execute('INSERT INTO visits VALUES (?, ?, ?)', (payload['eventId'], visitor, day))
                return respond({'ok': True})

            if path == '/api/feedback' and method == 'POST':
                rating, message = payload.get('rating'), payload.get('message', '')
                if rating is not None and (type(rating) is not int or rating not in range(1, 6)):
                    return respond({'error': 'Choose a rating from 1 to 5.'}, 400)
                if not isinstance(message, str) or len(message) > 2000 or (rating is None and not message.strip()) or not valid_id(payload.get('id')):
                    return respond({'error': 'Add a rating or a suggestion (up to 2,000 characters).'}, 400)
                if db.execute('SELECT 1 FROM feedback WHERE id=?', (payload['id'],)).fetchone():
                    return respond({'ok': True})
                if limited('feedback:' + client_ip, 6, 3600):
                    return respond({'error': 'Thanks for sharing! Please wait an hour before sending more feedback.'}, 429)
                db.execute('INSERT INTO feedback VALUES (?, ?, ?, ?)', (payload['id'], rating, message.strip(), datetime.now(timezone.utc).isoformat()))
                return respond({'ok': True})
            return respond({'error': 'Not found.'}, 404)
        except Exception:
            db.rollback()
            raise
        finally:
            db.commit()
            db.close()


service = Engagement()

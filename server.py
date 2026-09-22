"""Production WSGI entry point: serve public assets and the private API together."""
import mimetypes
import os
from http import HTTPStatus
from urllib.parse import unquote

from engagement import MAX_BODY, ROOT, service

PUBLIC_FILES = {'index.html', 'style.css', 'script.js', 'calgetc.js', 'community.js',
                'admin.html', 'admin.js', 'community.css'}


def public_file(path):
    decoded = unquote(path).replace('\\', '/')
    if any(part.startswith('.') or ':' in part for part in decoded.split('/') if part):
        return None
    relative = decoded.lstrip('/') or 'index.html'
    if relative == 'admin':
        relative = 'admin.html'
    file = (ROOT / relative).resolve()
    if ROOT not in file.parents or not file.is_file():
        return None
    if relative in PUBLIC_FILES or (relative.startswith('data/') and file.suffix == '.json'):
        return file
    return None


def application(environ, start_response):
    path, method = environ.get('PATH_INFO', '/'), environ['REQUEST_METHOD']
    if path.startswith('/api/'):
        try:
            length = int(environ.get('CONTENT_LENGTH') or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            status, headers, body = 413, [], b'{"error":"Request is too large."}'
        else:
            headers_in = {k[5:].replace('_', '-').lower(): v for k, v in environ.items() if k.startswith('HTTP_')}
            headers_in['content-type'] = environ.get('CONTENT_TYPE', '')
            # Public URL is explicit in production. Never trust a client-supplied forwarded header.
            origin = os.environ.get('BETTERASSIST_ORIGIN', '').rstrip('/')
            if not origin:
                host = environ.get('HTTP_HOST', '')
                if host.split(':')[0] not in ('localhost', '127.0.0.1'):
                    status, headers, body = 503, [], b'{"error":"Public origin is not configured."}'
                    return finish(start_response, status, headers, body, method)
                origin = 'http://' + host
            try:
                status, headers, body = service.dispatch(method, path, headers_in, environ['wsgi.input'].read(length), environ.get('REMOTE_ADDR', ''), origin)
            except Exception:
                # Do not expose credentials, filesystem paths, or private data on failures.
                status, headers, body = 503, [], b'{"error":"Service temporarily unavailable. Please try again."}'
        return finish(start_response, status, headers, body, method)
    file = public_file(path)
    if method not in ('GET', 'HEAD') or not file:
        return finish(start_response, 404, [('Content-Type', 'text/plain')], b'Not found', method)
    body = file.read_bytes()
    return finish(start_response, 200, [('Content-Type', mimetypes.guess_type(file.name)[0] or 'application/octet-stream')], body, method)


def finish(start_response, status, headers, body, method):
    headers = [*headers, ('Content-Length', str(len(body))), ('X-Frame-Options', 'DENY'),
               ('Referrer-Policy', 'same-origin')]
    if not any(k.lower() == 'cache-control' for k, _ in headers):
        headers.append(('Cache-Control', 'no-store'))
    if not any(k.lower() == 'x-content-type-options' for k, _ in headers):
        headers.append(('X-Content-Type-Options', 'nosniff'))
    headers.append(('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"))
    start_response(f'{status} {HTTPStatus(status).phrase}', headers)
    return [body if method != 'HEAD' else b'']


if __name__ == '__main__':
    from waitress import serve
    options = {}
    if os.environ.get('BETTERASSIST_TRUSTED_PROXY'):
        options.update(trusted_proxy=os.environ['BETTERASSIST_TRUSTED_PROXY'],
                       trusted_proxy_count=1, trusted_proxy_headers={'x-forwarded-for', 'x-forwarded-proto'})
    serve(application, host=os.environ.get('HOST', '127.0.0.1'), port=int(os.environ.get('PORT', '8000')),
          max_request_body_size=MAX_BODY, **options)

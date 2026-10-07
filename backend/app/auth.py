"""Optional server accounts. Local Windows use remains available without login."""
import hashlib
import os
import re
import secrets
import time
from pathlib import Path
from typing import Literal

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

COOKIE = 'catalog_session'
SESSION_SECONDS = 12 * 60 * 60
ROLES = Literal['viewer', 'admin']


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 600_000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def password_matches(password, stored):
    _, rounds, salt, digest = stored.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), int(rounds)).hex()
    return secrets.compare_digest(actual, digest)


def clean_username(username):
    username = username.strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,39}', username):
        raise ValueError('Логин: 3–40 латинских букв, цифр, точек, дефисов или подчёркиваний')
    return username


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class NewUser(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=12, max_length=200)
    role: ROLES = 'admin'


class UserUpdate(BaseModel):
    role: ROLES
    enabled: bool
    password: str | None = Field(default=None, min_length=12, max_length=200)


def install_auth(app, db):
    server = os.getenv('CATALOG_SERVER_MODE') == '1'
    secure_cookie = os.getenv('CATALOG_COOKIE_SECURE', '1') == '1'
    origin = os.getenv('CATALOG_PUBLIC_ORIGIN', '').rstrip('/')
    with db() as c:
        c.executescript('''
          CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, role TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
          CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT PRIMARY KEY, attempts INTEGER NOT NULL,
            started_at INTEGER NOT NULL);
        ''')
        if server and not c.execute('SELECT 1 FROM users').fetchone():
            filename = os.getenv('CATALOG_ADMIN_PASSWORD_FILE')
            password = Path(filename).read_text(encoding='utf-8').rstrip('\r\n') if filename else os.getenv('CATALOG_ADMIN_PASSWORD', '')
            if not 12 <= len(password) <= 200:
                raise RuntimeError('Set a 12–200 character administrator password before starting server mode')
            username = clean_username(os.getenv('CATALOG_ADMIN_USERNAME', 'admin'))
            c.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',
                      (username, password_hash(password), 'admin'))
    dummy_hash = password_hash(secrets.token_urlsafe(24)) if server else ''

    def access(request):
        if not server:
            return {'mode': 'local', 'user': None, 'role': 'admin', 'can_edit': True, 'can_delete': True,
                    'can_manage_users': False, 'csrf_token': None}
        user = None
        token = request.cookies.get(COOKIE, '')
        if token and len(token) <= 128:
            with db() as c:
                user = c.execute('''SELECT u.id,u.username,u.role,s.csrf_token FROM sessions s
                    JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires_at>? AND u.enabled=1''',
                    (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        role = user['role'] if user else 'visitor'
        return {'mode': 'server', 'user': {'id': user['id'], 'username': user['username']} if user else None,
                'role': role, 'can_edit': role == 'admin', 'can_delete': role == 'admin',
                'can_manage_users': role == 'admin', 'csrf_token': user['csrf_token'] if user else None}

    @app.middleware('http')
    async def permissions(request: Request, call_next):
        request.state.access = access(request)
        if server and request.method not in ['GET', 'HEAD', 'OPTIONS'] and request.url.path.startswith('/api/'):
            sent_origin = request.headers.get('origin')
            if sent_origin and (not origin or sent_origin.rstrip('/') != origin):
                return JSONResponse({'detail': 'Запрос с другого сайта запрещён'}, status_code=403)
            if request.url.path != '/api/auth/login':
                current = request.state.access
                if not current['user']:
                    return JSONResponse({'detail': 'Войдите в учётную запись'}, status_code=401)
                csrf = request.headers.get('x-csrf-token', '')
                if not csrf or not secrets.compare_digest(csrf, current['csrf_token']):
                    return JSONResponse({'detail': 'Обновите страницу и повторите действие'}, status_code=403)
                allowed = (request.url.path == '/api/auth/logout' or
                           (current['can_manage_users'] if request.url.path.startswith('/api/users') else
                            current['can_delete'] if request.method == 'DELETE' else current['can_edit']))
                if not allowed:
                    return JSONResponse({'detail': 'Нет прав на это действие'}, status_code=403)
        response = await call_next(request)
        if request.url.path.startswith(('/api/auth/', '/api/users')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/auth/session')
    def session(request: Request):
        return request.state.access

    @app.post('/api/auth/login')
    def login(payload: Login, request: Request):
        if not server:
            raise HTTPException(404, 'Вход нужен только в серверном режиме')
        now = int(time.time())
        ip = request.client.host if request.client else 'unknown'
        with db() as c:
            attempt = c.execute('SELECT * FROM login_attempts WHERE ip=?', (ip,)).fetchone()
            if attempt and attempt['started_at'] > now - 300 and attempt['attempts'] >= 10:
                raise HTTPException(429, 'Слишком много попыток. Повторите через 5 минут.')
            user = c.execute('SELECT * FROM users WHERE username=?', (payload.username.strip().lower(),)).fetchone()
        verified = password_matches(payload.password, user['password_hash'] if user else dummy_hash)
        if not user or not verified or not user['enabled']:
            with db() as c:
                c.execute('DELETE FROM login_attempts WHERE started_at<=?', (now - 300,))
                c.execute('''INSERT INTO login_attempts(ip,attempts,started_at) VALUES(?,1,?)
                    ON CONFLICT(ip) DO UPDATE SET attempts=attempts+1''', (ip, now))
            raise HTTPException(401, 'Неверный логин или пароль')
        token = secrets.token_urlsafe(32)
        with db() as c:
            c.execute('DELETE FROM sessions WHERE expires_at<=?', (now,))
            c.execute('DELETE FROM login_attempts WHERE ip=?', (ip,))
            previous = request.cookies.get(COOKIE)
            if previous:
                c.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(previous.encode()).hexdigest(),))
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)',
                      (hashlib.sha256(token.encode()).hexdigest(), user['id'], secrets.token_urlsafe(32), now + SESSION_SECONDS))
        response = JSONResponse({'status': 'ok'})
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                            secure=secure_cookie, samesite='strict', path='/')
        return response

    @app.post('/api/auth/logout')
    def logout(request: Request):
        token = request.cookies.get(COOKIE, '')
        with db() as c:
            c.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
        response = JSONResponse({'status': 'ok'})
        response.delete_cookie(COOKIE, path='/', secure=secure_cookie, httponly=True, samesite='strict')
        return response

    def require_admin(request):
        if not server or not request.state.access['can_manage_users']:
            raise HTTPException(403, 'Управление пользователями доступно администратору')

    @app.get('/api/users')
    def users(request: Request):
        require_admin(request)
        with db() as c:
            return [dict(row) for row in c.execute('SELECT id,username,role,enabled FROM users ORDER BY username')]

    @app.post('/api/users', status_code=201)
    def create_user(payload: NewUser, request: Request):
        require_admin(request)
        try:
            username = clean_username(payload.username)
        except ValueError as error:
            raise HTTPException(422, str(error))
        from sqlite3 import IntegrityError
        with db() as c:
            try:
                result = c.execute('INSERT INTO users(username,password_hash,role) VALUES(?,?,?)',
                                   (username, password_hash(payload.password), payload.role))
            except IntegrityError:
                raise HTTPException(409, 'Этот логин уже занят')
            return {'id': result.lastrowid, 'username': username, 'role': payload.role, 'enabled': True}

    @app.put('/api/users/{identity}')
    def update_user(identity: int, payload: UserUpdate, request: Request):
        require_admin(request)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            user = c.execute('SELECT * FROM users WHERE id=?', (identity,)).fetchone()
            if not user:
                raise HTTPException(404, 'Пользователь не найден')
            if user['role'] == 'admin' and user['enabled'] and (payload.role != 'admin' or not payload.enabled):
                count = c.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1").fetchone()[0]
                if count <= 1:
                    raise HTTPException(409, 'Нельзя отключить или понизить последнего администратора')
            c.execute('UPDATE users SET role=?,enabled=? WHERE id=?', (payload.role, payload.enabled, identity))
            if payload.password is not None:
                c.execute('UPDATE users SET password_hash=? WHERE id=?', (password_hash(payload.password), identity))
            if payload.password is not None or not payload.enabled or payload.role != user['role']:
                c.execute('DELETE FROM sessions WHERE user_id=?', (identity,))
            return {'id': identity, 'username': user['username'], 'role': payload.role, 'enabled': payload.enabled}

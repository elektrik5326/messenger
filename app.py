from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret-key-change-in-production')
socketio = SocketIO(app, cors_allowed_origins="*")

DB_PATH = 'database.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user TEXT NOT NULL,
            to_user TEXT NOT NULL,
            message TEXT,
            file TEXT,
            timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def get_user_by_username(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, username, password FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, password, created_at) VALUES (?, ?, ?)',
                  (username, generate_password_hash(password), datetime.now().isoformat()))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def save_message(from_user, to_user, message, file=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO messages (from_user, to_user, message, file, timestamp) VALUES (?, ?, ?, ?, ?)',
              (from_user, to_user, message, file, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_messages(user1, user2, limit=50):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        SELECT from_user, message, file, timestamp FROM messages
        WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)
        ORDER BY timestamp DESC LIMIT ?
    ''', (user1, user2, user2, user1, limit))
    messages = c.fetchall()
    conn.close()
    return list(reversed(messages))

def get_users_except(username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT username FROM users WHERE username != ?', (username,))
    users = [row[0] for row in c.fetchall()]
    conn.close()
    return users

# ========== РОУТЫ ==========
@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if create_user(username, password):
            session['username'] = username
            return redirect(url_for('chat'))
        error = 'Пользователь с таким именем уже существует'
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = get_user_by_username(username)
        if user and check_password_hash(user[2], password):
            session['username'] = username
            return redirect(url_for('chat'))
        error = 'Неверное имя пользователя или пароль'
    return render_template('login.html', error=error)

@app.route('/chat')
def chat():
    if 'username' not in session:
        return redirect(url_for('login'))
    users = get_users_except(session['username'])
    return render_template('index.html', username=session['username'], users=users)

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/api/messages/<to_user>')
def api_messages(to_user):
    if 'username' not in session:
        return jsonify([])
    messages = get_messages(session['username'], to_user)
    return jsonify([{
        'from': m[0],
        'message': m[1],
        'file': m[2],
        'time': m[3]
    } for m in messages])

# ========== WEBSOCKET ==========
@socketio.on('send_message')
def handle_send_message(data):
    to_user = data['to']
    message = data['message']
    from_user = session.get('username')
    if from_user and message:
        save_message(from_user, to_user, message)
        now = datetime.now().isoformat()
        emit('receive_message', {
            'from': from_user,
            'message': message,
            'time': now
        }, room=to_user)
        emit('receive_message', {
            'from': from_user,
            'message': message,
            'time': now
        }, room=from_user)

@socketio.on('join')
def handle_join(*args, **kwargs):
    username = session.get('username')
    if username:
        join_room(username)
        
if __name__ == '__main__':
    init_db()
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
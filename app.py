from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret-key')

# Подключение к PostgreSQL (или SQLite для локальной разработки)
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# ========== МОДЕЛИ БАЗЫ ДАННЫХ ==========
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.String(50), nullable=False)

class Message(db.Model):
    __tablename__ = 'messages'
    id = db.Column(db.Integer, primary_key=True)
    from_user = db.Column(db.String(80), nullable=False)
    to_user = db.Column(db.String(80), nullable=False)
    message = db.Column(db.Text)
    file = db.Column(db.String(200))
    timestamp = db.Column(db.String(50), nullable=False)

# ========== ФУНКЦИИ ==========
def get_user_by_username(username):
    return User.query.filter_by(username=username).first()

def create_user(username, password):
    if get_user_by_username(username):
        return False
    user = User(
        username=username,
        password=generate_password_hash(password),
        created_at=datetime.now().isoformat()
    )
    db.session.add(user)
    db.session.commit()
    return True

def save_message(from_user, to_user, message, file=None):
    msg = Message(
        from_user=from_user,
        to_user=to_user,
        message=message,
        file=file,
        timestamp=datetime.now().isoformat()
    )
    db.session.add(msg)
    db.session.commit()

def get_messages(user1, user2, limit=50):
    messages = Message.query.filter(
        ((Message.from_user == user1) & (Message.to_user == user2)) |
        ((Message.from_user == user2) & (Message.to_user == user1))
    ).order_by(Message.timestamp).limit(limit).all()
    return [(m.from_user, m.message, m.file, m.timestamp) for m in messages]

def get_users_except(username):
    users = User.query.filter(User.username != username).all()
    return [u.username for u in users]

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
        error = 'Пользователь уже существует'
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = get_user_by_username(username)
        if user and check_password_hash(user.password, password):
            session['username'] = username
            return redirect(url_for('chat'))
        error = 'Неверное имя или пароль'
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
    return jsonify([{'from': m[0], 'message': m[1], 'file': m[2], 'time': m[3]} for m in messages])

# ========== WEBSOCKET ==========
@socketio.on('join')
def handle_join(data):
    username = session.get('username')
    if username:
        join_room(username)

@socketio.on('send_message')
def handle_send_message(data):
    to_user = data['to']
    message = data['message']
    from_user = session.get('username')
    if from_user and message:
        save_message(from_user, to_user, message)
        now = datetime.now().isoformat()
        emit('receive_message', {'from': from_user, 'message': message, 'time': now}, room=to_user)
        emit('receive_message', {'from': from_user, 'message': message, 'time': now}, room=from_user)

# ========== ЗАПУСК ==========
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, debug=False, host='0.0.0.0', port=port)

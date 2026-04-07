from flask import Flask, render_template, request, redirect, session
from datetime import timedelta
import sqlite3, hashlib, os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.permanent_session_lifetime = timedelta(days=30)
DB = 'magazshooze.db'

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            size TEXT,
            description TEXT,
            photo TEXT
        );
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL
        );
    ''')
    db.commit()

UPLOAD_FOLDER = 'static/img'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    db = get_db()
    products = db.execute('SELECT * FROM products').fetchall()
    return render_template('index.html', products=products)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = hashlib.md5(request.form['password'].encode()).hexdigest()
        db = get_db()
        db.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, password))
        db.commit()
        return redirect('/login')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = hashlib.md5(request.form['password'].encode()).hexdigest()
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email=? AND password=?', (email, password)).fetchone()
        if user:
            session.permanent = True
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['role'] = user['role']
            return redirect('/')
        return render_template('login.html', error='Неверный email или пароль')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/product/<int:id>')
def product(id):
    db = get_db()
    p = db.execute('SELECT * FROM products WHERE id=?', (id,)).fetchone()
    if not p:
        return redirect('/')
    return render_template('product.html', p=p)

@app.route('/cart/add/<int:id>', methods=['POST'])
def cart_add(id):
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    existing = db.execute('SELECT * FROM cart WHERE user_id=? AND product_id=?', (session['user_id'], id)).fetchone()
    if existing:
        db.execute('UPDATE cart SET quantity=quantity+1 WHERE user_id=? AND product_id=?', (session['user_id'], id))
    else:
        db.execute('INSERT INTO cart (user_id, product_id) VALUES (?, ?)', (session['user_id'], id))
    db.commit()
    return redirect('/cart')

@app.route('/cart')
def cart():
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    items = db.execute('''
        SELECT p.name, p.price, c.quantity, c.id, p.id as pid
        FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.user_id=?
    ''', (session['user_id'],)).fetchall()
    total = sum(i['price'] * i['quantity'] for i in items)
    return render_template('cart.html', items=items, total=total)

@app.route('/cart/remove/<int:id>')
def cart_remove(id):
    db = get_db()
    db.execute('DELETE FROM cart WHERE id=?', (id,))
    db.commit()
    return redirect('/cart')

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    items = db.execute('''
        SELECT p.name, p.price, c.quantity, c.id, p.id as pid
        FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.user_id=?
    ''', (session['user_id'],)).fetchall()
    if not items:
        return redirect('/cart')
    total = sum(i['price'] * i['quantity'] for i in items)
    if request.method == 'POST':
        order = db.execute('INSERT INTO orders (user_id) VALUES (?)', (session['user_id'],))
        order_id = order.lastrowid
        for i in items:
            db.execute('INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)',
                       (order_id, i['pid'], i['quantity'], i['price']))
        db.execute('DELETE FROM cart WHERE user_id=?', (session['user_id'],))
        db.commit()
        order_data = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
        return render_template('order_success.html', order=order_data, items=items, total=total)
    return render_template('checkout.html', items=items, total=total)

@app.route('/order/<int:id>')
def order_detail(id):
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE id=? AND user_id=?', (id, session['user_id'])).fetchone()
    if not order:
        return redirect('/orders')
    items = db.execute('''
        SELECT p.name, oi.quantity, oi.price
        FROM order_items oi JOIN products p ON oi.product_id=p.id
        WHERE oi.order_id=?
    ''', (id,)).fetchall()
    total = sum(i['price'] * i['quantity'] for i in items)
    return render_template('order_detail.html', order=order, items=items, total=total)

@app.route('/order_success')
def order_success():
    return render_template('order_success.html')

@app.route('/orders')
def orders():
    if not session.get('user_id'):
        return redirect('/login')
    db = get_db()
    orders = db.execute('SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC', (session['user_id'],)).fetchall()
    return render_template('orders.html', orders=orders)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('role') != 'admin':
        return redirect('/')
    db = get_db()
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        size = request.form['size']
        description = request.form['description']
        photo = ''
        if 'photo' in request.files:
            file = request.files['photo']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                photo = '/static/img/' + filename
        db.execute('INSERT INTO products (name, price, size, description, photo) VALUES (?, ?, ?, ?, ?)',
                   (name, price, size, description, photo))
        db.commit()
    products = db.execute('SELECT * FROM products').fetchall()
    return render_template('admin.html', products=products)

@app.route('/admin/delete/<int:id>')
def delete_product(id):
    if session.get('role') != 'admin':
        return redirect('/')
    db = get_db()
    db.execute('DELETE FROM products WHERE id=?', (id,))
    db.commit()
    return redirect('/admin')


from flask import jsonify

@app.route('/api/me')
def api_me():
    if session.get('user_id'):
        return jsonify({'id': session['user_id'], 'name': session['user_name'], 'role': session.get('role')})
    return jsonify(None)

@app.route('/api/products')
def api_products():
    db = get_db()
    products = db.execute('SELECT * FROM products').fetchall()
    return jsonify([dict(p) for p in products])

@app.route('/api/cart')
def api_cart():
    if not session.get('user_id'):
        return jsonify([])
    db = get_db()
    items = db.execute('''
        SELECT c.id, c.quantity, p.id as pid, p.name, p.price, p.photo
        FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.user_id=?
    ''', (session['user_id'],)).fetchall()
    return jsonify([dict(i) for i in items])

@app.route('/api/cart/add/<int:pid>', methods=['POST'])
def api_cart_add(pid):
    if not session.get('user_id'):
        return jsonify({'error': 'not logged in'}), 401
    db = get_db()
    existing = db.execute('SELECT * FROM cart WHERE user_id=? AND product_id=?',
                          (session['user_id'], pid)).fetchone()
    if existing:
        db.execute('UPDATE cart SET quantity=quantity+1 WHERE user_id=? AND product_id=?',
                   (session['user_id'], pid))
    else:
        db.execute('INSERT INTO cart (user_id, product_id) VALUES (?, ?)',
                   (session['user_id'], pid))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/cart/remove/<int:cid>', methods=['POST'])
def api_cart_remove(cid):
    db = get_db()
    db.execute('DELETE FROM cart WHERE id=?', (cid,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/orders')
def api_orders():
    if not session.get('user_id'):
        return jsonify([])
    db = get_db()
    orders = db.execute('SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC',
                        (session['user_id'],)).fetchall()
    result = []
    for o in orders:
        items = db.execute('''
            SELECT p.name, oi.quantity, oi.price
            FROM order_items oi JOIN products p ON oi.product_id=p.id
            WHERE oi.order_id=?
        ''', (o['id'],)).fetchall()
        result.append({**dict(o), 'items': [dict(i) for i in items]})
    return jsonify(result)

@app.route('/api/orders/all')
def api_orders_all():
    if session.get('role') != 'admin':
        return jsonify([])
    db = get_db()
    orders = db.execute('''
        SELECT o.*, u.name as user_name 
        FROM orders o JOIN users u ON o.user_id=u.id
        ORDER BY o.created_at DESC
    ''').fetchall()
    result = []
    for o in orders:
        items = db.execute('''
            SELECT p.name, oi.quantity, oi.price
            FROM order_items oi JOIN products p ON oi.product_id=p.id
            WHERE oi.order_id=?
        ''', (o['id'],)).fetchall()
        result.append({**dict(o), 'items': [dict(i) for i in items]})
    return jsonify(result)

@app.route('/api/orders/status/<int:oid>', methods=['POST'])
def api_order_status(oid):
    if session.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    data = request.get_json()
    db = get_db()
    db.execute('UPDATE orders SET status=? WHERE id=?', (data['status'], oid))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/checkout', methods=['POST'])
def api_checkout():
    if not session.get('user_id'):
        return jsonify({'error': 'not logged in'}), 401
    db = get_db()
    items = db.execute('''
        SELECT c.quantity, p.id as pid, p.price
        FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.user_id=?
    ''', (session['user_id'],)).fetchall()
    if not items:
        return jsonify({'error': 'cart empty'}), 400
    order = db.execute('INSERT INTO orders (user_id) VALUES (?)', (session['user_id'],))
    order_id = order.lastrowid
    for i in items:
        db.execute('INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)',
                   (order_id, i['pid'], i['quantity'], i['price']))
    db.execute('DELETE FROM cart WHERE user_id=?', (session['user_id'],))
    db.commit()
    return jsonify({'ok': True, 'order_id': order_id})

@app.route('/api/admin/products/delete/<int:pid>', methods=['POST'])
def api_admin_delete(pid):
    if session.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    db = get_db()
    db.execute('DELETE FROM products WHERE id=?', (pid,))
    db.commit()
    return jsonify({'ok': True})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    email = data.get('email')
    password = hashlib.md5(data.get('password', '').encode()).hexdigest()
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE email=? AND password=?', (email, password)).fetchone()
    if user:
        session.permanent = True
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['role'] = user['role']
        return jsonify({'ok': True, 'name': user['name'], 'role': user['role']})
    return jsonify({'error': 'Неверный email или пароль'}), 401

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    name = data.get('name')
    email = data.get('email')
    password = hashlib.md5(data.get('password', '').encode()).hexdigest()
    db = get_db()
    try:
        db.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, password))
        db.commit()
        user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        session.permanent = True
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['role'] = user['role']
        return jsonify({'ok': True, 'name': name})
    except:
        return jsonify({'error': 'Email уже зарегистрирован'}), 400

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)
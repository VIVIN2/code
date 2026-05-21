from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_in_production'

DATABASE = 'database.db'

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    # Create Users Table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Admin', 'User'))
        )
    ''')
    # Create Tasks Table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            assigned_to INTEGER,
            priority TEXT NOT NULL CHECK(priority IN ('Low', 'Medium', 'High')),
            status TEXT NOT NULL CHECK(status IN ('Pending', 'In Progress', 'Completed')),
            deadline DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assigned_to) REFERENCES users (id) ON DELETE SET NULL
        )
    ''')
    
    # Check if admin user exists, if not create one
    admin = conn.execute('SELECT * FROM users WHERE username = ?', ('admin',)).fetchone()
    if not admin:
        hashed_password = generate_password_hash('admin123')
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                     ('admin', hashed_password, 'Admin'))
                     
    conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_role' not in session or session['user_role'] != 'Admin':
            flash('Access denied. Admin role required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('user_role') == 'Admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['user_role'] = user['role']
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ================= ADMIN ROUTES =================

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    total_users = conn.execute('SELECT COUNT(*) FROM users WHERE role="User"').fetchone()[0]
    total_tasks = conn.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
    completed_tasks = conn.execute('SELECT COUNT(*) FROM tasks WHERE status="Completed"').fetchone()[0]
    pending_tasks = conn.execute('SELECT COUNT(*) FROM tasks WHERE status="Pending"').fetchone()[0]
    conn.close()
    return render_template('admin_dashboard.html', 
                           total_users=total_users, 
                           total_tasks=total_tasks,
                           completed_tasks=completed_tasks,
                           pending_tasks=pending_tasks)

@app.route('/admin/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    conn = get_db_connection()
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role', 'User')
        
        if not username or not password:
            flash('Username and Password are required!', 'error')
        else:
            hashed_pw = generate_password_hash(password)
            try:
                conn.execute('INSERT INTO users (username, password, role) VALUES (?, ?, ?)',
                             (username, hashed_pw, role))
                conn.commit()
                flash('User created successfully!', 'success')
            except sqlite3.IntegrityError:
                flash('Username already exists.', 'error')
                
    users = conn.execute('SELECT * FROM users').fetchall()
    conn.close()
    return render_template('create_user.html', users=users)

@app.route('/admin/users/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('User deleted successfully!', 'success')
    return redirect(url_for('create_user'))

@app.route('/admin/tasks/assign', methods=['GET', 'POST'])
@login_required
@admin_required
def assign_task():
    conn = get_db_connection()
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        assigned_to = request.form['assigned_to']
        priority = request.form['priority']
        status = 'Pending'
        deadline = request.form['deadline']
        
        conn.execute('''
            INSERT INTO tasks (title, description, assigned_to, priority, status, deadline)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, description, assigned_to, priority, status, deadline))
        conn.commit()
        flash('Task assigned successfully!', 'success')
        conn.close()
        return redirect(url_for('manage_tasks'))
        
    users = conn.execute('SELECT id, username FROM users WHERE role="User"').fetchall()
    conn.close()
    return render_template('assign_task.html', users=users)

@app.route('/admin/tasks')
@login_required
@admin_required
def manage_tasks():
    conn = get_db_connection()
    tasks = conn.execute('''
        SELECT t.*, u.username as assigned_user 
        FROM tasks t LEFT JOIN users u ON t.assigned_to = u.id
    ''').fetchall()
    conn.close()
    return render_template('manage_tasks.html', tasks=tasks)

@app.route('/admin/tasks/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_task(id):
    conn = get_db_connection()
    task = conn.execute('SELECT * FROM tasks WHERE id = ?', (id,)).fetchone()
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        assigned_to = request.form['assigned_to']
        priority = request.form['priority']
        status = request.form['status']
        deadline = request.form['deadline']
        
        conn.execute('''
            UPDATE tasks SET title = ?, description = ?, assigned_to = ?, 
            priority = ?, status = ?, deadline = ? WHERE id = ?
        ''', (title, description, assigned_to, priority, status, deadline, id))
        conn.commit()
        conn.close()
        flash('Task updated successfully!', 'success')
        return redirect(url_for('manage_tasks'))
        
    users = conn.execute('SELECT id, username FROM users WHERE role="User"').fetchall()
    conn.close()
    return render_template('edit_task.html', task=task, users=users)

@app.route('/admin/tasks/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_task(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM tasks WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Task deleted successfully!', 'success')
    return redirect(url_for('manage_tasks'))

# ================= USER ROUTES =================

@app.route('/user')
@login_required
def user_dashboard():
    if session.get('user_role') != 'User':
        return redirect(url_for('index'))
        
    conn = get_db_connection()
    my_tasks = conn.execute('SELECT * FROM tasks WHERE assigned_to = ?', (session['user_id'],)).fetchall()
    completed_tasks = sum(1 for t in my_tasks if t['status'] == 'Completed')
    pending_tasks = sum(1 for t in my_tasks if t['status'] == 'Pending')
    in_progress_tasks = sum(1 for t in my_tasks if t['status'] == 'In Progress')
    conn.close()
    
    return render_template('user_dashboard.html', 
                           my_tasks=my_tasks, 
                           completed_tasks=completed_tasks,
                           pending_tasks=pending_tasks,
                           in_progress_tasks=in_progress_tasks)

@app.route('/user/tasks/<int:id>/update', methods=['POST'])
@login_required
def update_task_status(id):
    if session.get('user_role') != 'User':
        return redirect(url_for('index'))
        
    status = request.form['status']
    
    conn = get_db_connection()
    task = conn.execute('SELECT * FROM tasks WHERE id = ? AND assigned_to = ?', (id, session['user_id'])).fetchone()
    if task:
        conn.execute('UPDATE tasks SET status = ? WHERE id = ?', (status, id))
        conn.commit()
        flash('Task status updated successfully!', 'success')
    else:
        flash('Unauthorized action.', 'error')
    conn.close()
    
    return redirect(url_for('user_dashboard'))

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)

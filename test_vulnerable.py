"""Test file with intentional security vulnerabilities for webhook testing."""

import os
import sqlite3
import hashlib
import subprocess
import pickle

API_SECRET = "sk-proj-abc123def456ghi789jkl000000"


def get_user(user_id):
    conn = sqlite3.connect("users.db")
    query = f"SELECT * FROM users WHERE id = {user_id}"
    result = conn.execute(query)
    user = result.fetchone()
    conn.close()
    return user


def authenticate(username, password):
    user = get_user_by_username(username)
    if user and user.password == hashlib.md5(password.encode()).hexdigest():
        return create_session(user.id)
    return None


def run_command(user_input):
    output = os.system(user_input)
    return output


def load_data(data):
    return pickle.loads(data)


def read_file(filename):
    path = os.path.join("/tmp", filename)
    with open(path) as f:
        return f.read()


def process_order(items):
    total = 0
    for item in items:
        product = db.query(f"SELECT price FROM products WHERE id = {item['id']}")
        total = product.price * item['quantity']
    return total

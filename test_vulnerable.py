"""Test file with intentional security vulnerabilities."""

import os
import sqlite3
import hashlib
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
    return os.system(user_input)


def load_data(data):
    return pickle.loads(data)


def eval_expression(expr):
    return eval(expr)

import sqlite3
import os

# 确保数据库路径正确
db_path = "seo_master.db"


def setup_admin():
    # 1. 连接数据库（如果文件不存在会自动创建）
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("正在初始化数据库表结构...")
    # 2. 创建用户表 (必须先执行这个！)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            expiry_date DATE,
            last_session_id TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)

    # 3. 创建历史记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS optimized_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_input TEXT,
            optimized_title TEXT,
            platform TEXT,
            char_limit INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 4. 插入管理员账号
    print("正在创建管理员账号...")
    try:
        cursor.execute("""
            INSERT INTO users (username, password, expiry_date) 
            VALUES ('admin', '123456', '2026-12-31')
        """)
        conn.commit()
        print("✅ 成功！账号: admin, 密码: 123456")
    except sqlite3.IntegrityError:
        print("⚠️ 提示：账号 'admin' 已经存在，无需重复插入。")

    conn.close()


if __name__ == "__main__":
    setup_admin()
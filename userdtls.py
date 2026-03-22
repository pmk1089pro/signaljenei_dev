import logging
import sqlite3
import datetime
from config import DB_FILE, LOG_FILE

logging.basicConfig(
    filename=LOG_FILE,
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def new_user():
    print("Creating a new user...")
    user = input("Enter user name: ")
    kite_username = input("Enter Kite username: ")
    kite_password = input("Enter Kite password: ")
    kite_api_secret = input("Enter Kite API secret: ")
    kite_api_key = input("Enter Kite API key: ")
    kite_totp_token = input("Enter Kite TOTP token: ")
    telegram_chat_id = input("Enter Telegram chat ID: ")
    telegram_token = input("Enter Telegram token: ")

    user_detail = {
        "user": user,
        "kite_username": kite_username,
        "kite_password": kite_password,
        "kite_api_secret": kite_api_secret,
        "kite_api_key": kite_api_key,
        "kite_totp_token": kite_totp_token,
        "telegram_chat_id": telegram_chat_id,
        "telegram_token": telegram_token
    }

    print("User details stored:", user_detail)

    save_user_detail(user_detail)

def save_user_detail(user_detail):
    """
    Save a new user detail into the user_dtls table.
    user_detail: dict with keys matching table columns.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        sql = """
            INSERT INTO user_dtls (
                user, kite_username, kite_password, kite_api_secret, kite_api_key,
                kite_totp_token, telegram_chat_id, telegram_token, active_flag, crt_dt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            user_detail.get("user"),
            user_detail.get("kite_username"),
            user_detail.get("kite_password"),
            user_detail.get("kite_api_secret"),
            user_detail.get("kite_api_key"),
            user_detail.get("kite_totp_token"),
            user_detail.get("telegram_chat_id"),
            user_detail.get("telegram_token"),
            user_detail.get("active_flag", 1),
            user_detail.get("crt_dt", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        )
        c.execute(sql, params)
        conn.commit()
        conn.close()
        logging.info(f"✅ User detail saved for user: {user_detail.get('user')}")
    except Exception as e:
        print(f"❌ Error saving user detail: {e}")
        logging.error(f"❌ Error saving user detail: {e}")



def get_all_active_user():
    """
    Returns a list of dicts for all active users from user_dtls table.
    Each dict contains all columns including 'id'.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        sql = "SELECT * FROM user_dtls WHERE active_flag = 1"
        c.execute(sql)
        rows = c.fetchall()
        columns = [desc[0] for desc in c.description]
        users = [dict(zip(columns, row)) for row in rows]
        conn.close()
        return users
    except Exception as e:
        print(f"❌ Error fetching active users: {e}")
        logging.error(f"❌ Error fetching active users: {e}")
        return []
    
def get_admin_user():
    """
    Returns a list of dicts for all active users from user_dtls table.
    Each dict contains all columns including 'id'.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        sql = "SELECT * FROM user_dtls WHERE active_flag = 1 and user_type = 'ADMIN'"
        c.execute(sql)
        rows = c.fetchall()
        columns = [desc[0] for desc in c.description]
        users = [dict(zip(columns, row)) for row in rows]
        conn.close()
        return users
    except Exception as e:
        print(f"❌ Error fetching admin users: {e}")
        logging.error(f"❌ Error fetching admin users: {e}")
        return []

def get_sj_admin_user():
    """
    Returns a list of dicts for all active users from user_dtls table.
    Each dict contains all columns including 'id'.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        sql = "SELECT * FROM user_dtls WHERE active_flag = 1 and user_type = 'ADMIN' and kite_username = 'RQD364'"
        c.execute(sql)
        rows = c.fetchall()
        columns = [desc[0] for desc in c.description]
        users = [dict(zip(columns, row)) for row in rows]
        conn.close()
        return users
    except Exception as e:
        print(f"❌ Error fetching sj admin user: {e}")
        logging.error(f"❌ Error fetching sj admin user: {e}")
        return []

def get_sj_telegram_users():
    """
    Returns a list of dicts for all active users from user_dtls table.
    Each dict contains all columns including 'id'.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        sql = "SELECT id,user,telegram_chat_id,telegram_token FROM sj_users_cur WHERE active_flag = 1 and user_type = 'CLIENT'"
        c.execute(sql)
        rows = c.fetchall()
        columns = [desc[0] for desc in c.description]
        users = [dict(zip(columns, row)) for row in rows]
        conn.close()
        return users
    except Exception as e:
        print(f"❌ Error fetching sj users: {e}")
        logging.error(f"❌ Error fetching sj users: {e}")
        return []


if __name__ == "__main__":
    new_user()
import pyotp
import json
import requests
import sqlite3
from datetime import datetime
from kiteconnect import KiteConnect
from api_urls import LOGIN_URL, TWOFA_URL
from config import ACCESS_TOKEN_FILE, DB_FILE

def save_token_to_db(token_data, user_id, username):
    """Save token data to kite_session table"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        current_time = datetime.now().isoformat()
        
        # Check if user already has a session
        c.execute("SELECT session_pk FROM kite_session WHERE user_id = ?", (user_id,))
        existing = c.fetchone()
        
        if existing:
            # Update existing session
            c.execute("""
                UPDATE kite_session 
                SET access_token = ?, api_key = ?, api_secret = ?, lst_updt_dt = ?
                WHERE user_id = ?
            """, (
                token_data['access_token'],
                token_data['api_key'],
                token_data['api_secret'],
                current_time,
                user_id
            ))
            print(f"[INFO] Token updated in database for user_id: {user_id}")
        else:
            # Insert new session
            c.execute("""
                INSERT INTO kite_session (user_id, username, access_token, api_key, api_secret, crt_dt, lst_updt_dt)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                username,
                token_data['access_token'],
                token_data['api_key'],
                token_data['api_secret'],
                current_time,
                current_time
            ))
            print(f"[INFO] Token saved to database for user_id: {user_id}")
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"[ERROR] Database error while saving token: {e}")
        return False

def autologin_zerodha(user):
    session = requests.Session()

    # Step 1: Login with user_id and password
    response = session.post(LOGIN_URL, data={'user_id': user['kite_username'], 'password': user['kite_password']})
    request_id = json.loads(response.text)['data']['request_id']

    # Step 2: Two-factor authentication
    twofa_pin = pyotp.TOTP(user['kite_totp_token']).now()
    session.post(
        TWOFA_URL,
        data={
            'user_id': user['kite_username'],
            'request_id': request_id,
            'twofa_value': twofa_pin,
            'twofa_type': 'totp'
        }
    )

    # Step 3: Generate request_token and access_token
    kite = KiteConnect(api_key=user['kite_api_key'])
    kite_url = kite.login_url()
    print("[INFO] Kite login URL:", kite_url)

    try:
        session.get(kite_url)
    except Exception as e:
        e_msg = str(e)
        if 'request_token=' in e_msg:
            request_token = e_msg.split('request_token=')[1].split(' ')[0].split('&action')[0]
            print('[INFO] Successful Login with Request Token:', request_token)

            access_token = kite.generate_session(request_token, user['kite_api_secret'])['access_token']
            kite.set_access_token(access_token)

            # Prepare token data
            token_data = {
                "access_token": access_token,
                "api_key": user['kite_api_key'],
                "api_secret": user['kite_api_secret'],
                "username": user['kite_username']
            }
            
            # Save to database
            user_id = user.get('id')  # Assuming user dict has 'id' field
            if user_id:
                if save_token_to_db(token_data, user_id, user['user']):
                    print(f"[INFO] Token saved to database successfully")
                else:
                    print(f"[WARNING] Failed to save token to database, falling back to JSON")
                    # Fallback: Save to JSON if DB fails
                    FILE = user['user'] + "_" + ACCESS_TOKEN_FILE
                    with open(FILE, "w") as f:
                        json.dump(token_data, f, indent=2)
                    print(f"[INFO] Token saved to file: {FILE}")
            else:
                # If no user_id, save to JSON as fallback
                FILE = user['user'] + "_" + ACCESS_TOKEN_FILE
                with open(FILE, "w") as f:
                    json.dump(token_data, f, indent=2)
                print(f"[INFO] Token saved to file: {FILE}")

            return access_token
        else:
            print("[ERROR] Could not extract request_token from exception.")
            return None

def get_token_from_db(user_id):
    """Retrieve token data from kite_session table"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            SELECT access_token, api_key, api_secret, username
            FROM kite_session
            WHERE user_id = ?
        """, (user_id,))
        result = c.fetchone()
        conn.close()
        
        if result:
            return {
                'access_token': result[0],
                'api_key': result[1],
                'api_secret': result[2],
                'username': result[3]
            }
        return None
    except sqlite3.Error as e:
        print(f"[ERROR] Database error while retrieving token: {e}")
        return None

def do_login(user):

    result = autologin_zerodha(user)

    if result:
        print(f"[✅] Access token generated and saved successfully for {user['user']}.")
    else:
        print(f"[❌] Login failed for {user['user']}.")
    


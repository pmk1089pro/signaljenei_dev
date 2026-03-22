import requests
import json
from userdtls import get_admin_user, get_sj_telegram_users
import pandas as pd

# 1. Initialize a global cache variable
_admin_df_cache = None
_signal_users_df_cache = None

def send_telegram_message(message, CHAT_ID, TOKEN):
    url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
    data = {
        'chat_id': CHAT_ID,
        'text': message
    }
    response = requests.post(url, data=data)
    
def get_cached_admin_df():
    global _admin_df_cache
    # 2. Only fetch if cache is None OR empty
    if _admin_df_cache is None or _admin_df_cache.empty:
        admins = get_admin_user()
        _admin_df_cache = pd.DataFrame(admins)
    return _admin_df_cache

def get_cached_signal_users_df():
    global _signal_users_df_cache
    # 2. Only fetch if cache is None OR empty
    if _signal_users_df_cache is None or _signal_users_df_cache.empty:
        sjusers = get_sj_telegram_users()
        _signal_users_df_cache = pd.DataFrame(sjusers)
    return _signal_users_df_cache

def send_telegram_message_admin(message):
    # 3. Use the cached version
    df = get_cached_admin_df()
    
    # 4. Standard loop
    for index, row in df.iterrows():
        CHAT_ID = row['telegram_chat_id']
        TOKEN = row['telegram_token']
        url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
        data = {'chat_id': CHAT_ID, 'text': 'Admin : ' + message}
        requests.post(url, data=data)

def send_telegram_signals_users(message):
        # 3. Use the cached version
    df = get_cached_signal_users_df()
    
    # 4. Standard loop
    for index, row in df.iterrows():
        CHAT_ID = row['telegram_chat_id']
        TOKEN = row['telegram_token']
        url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
        data = {'chat_id': CHAT_ID, 'text': message}
        requests.post(url, data=data)


if __name__ == "__main__":

    send_telegram_signals_users("ok this is fine")
    # TOKEN = '8661425321:AAGQ_AQr9oogAsHgIKPNmAkhZ1v5t6f82zM'

    # CHAT_ID = ''
    # url = f'https://api.telegram.org/bot{TOKEN}/getUpdates'
    # res = requests.get(url)
    # print(json.dumps(res.json(), indent=4))
    # CHAT_ID = res.json()['result'][0]['message']['chat']['id']
    # print(CHAT_ID)
    # message = "Welcome to NiftyFlow! Stay tuned for updates and insights to enhance your trading experience."
    # if CHAT_ID != '':
    #     send_telegram_message(message, CHAT_ID, TOKEN)
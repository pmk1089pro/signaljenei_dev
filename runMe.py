import time
import subprocess
import threading
from commonFunction import is_today_holiday
from config import INSTRUMENTS_FILE
from kitelogin import do_login
from tradeJenie import init_and_run
from userdtls import get_all_active_user, get_sj_admin_user
import os
from datetime import datetime
from commonFunction import init_db

def run_user_login(user):
    print(f"Logging in user: {user['user']}")
    do_login(user)

def run_trade_genie(user):
    print(f"Starting trade genie for user: {user['user']}")
    init_and_run(user)

def run_script(script_name):
    subprocess.run(['/home/harshilkhatri2808/uat/tradeJenie/venv/bin/python', script_name])
    #subprocess.run(['python', script_name])

if __name__ == "__main__":
    print("Starting the process...")
    if is_today_holiday():
        print("Today is a holiday. Exiting the process.")
        exit(0)
    
    skip_update = False

    if os.path.exists(INSTRUMENTS_FILE):
        file_mtime = datetime.fromtimestamp(os.path.getmtime(INSTRUMENTS_FILE)).date()
        today = datetime.now().date()
        if file_mtime == today:
            print(f"{INSTRUMENTS_FILE} is already updated today. Skipping updateInstrument.py.")
            skip_update = True

    if not skip_update:
        run_script('updateinstrument.py')
    
    if not os.path.exists('trading.db'):
        print("trading.db not found. Initializing database...")
        init_db()
    
    time.sleep(2)  # Wait for 2 seconds to ensure the first script completes
    threads = []
    print("Starting user logins and trade genie...")
    users = get_sj_admin_user()
    # print(f"Active users: {users}")

    for user in users:
        run_user_login(user)

    for user in users:
        # t1 = threading.Thread(target=run_user_login, args=(user,))
        t2 = threading.Thread(target=run_trade_genie, args=(user,))
        # t1.start()
        t2.start()
        threads.append(t2)

    # Step 4: Wait for all threads to finish
    for t in threads:
        t.join()

   
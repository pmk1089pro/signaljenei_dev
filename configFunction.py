from commonFunction import get_trade_configs, save_trade_config
import sqlite3
import datetime
import logging                                  
from config import DB_FILE


def new_trade_config():
    print("Creating a new user...")

    USER_ID = input("Enter TradeGenie USER_ID: ").strip()
    KEY = input("Enter unique Strategy name: ").strip()

    # Strategy selection
    strategies = ["PARALLEL_EMA", "GOD_EMA", "HDSTRATEGY"]
    print("\nSelect STRATEGY:")
    for i, s in enumerate(strategies, 1):
        print(f"{i}. {s}")
    while True:
        choice = input("Enter choice number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(strategies):
            STRATEGY = strategies[int(choice) - 1]
            break
        print("❌ Invalid choice. Please select again.")

    # Interval selection
    intervals = ["30minute", "60minute"]
    print("\nSelect INTERVAL:")
    for i, iv in enumerate(intervals, 1):
        print(f"{i}. {iv}")
    while True:
        choice = input("Enter choice number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(intervals):
            INTERVAL = intervals[int(choice) - 1]
            break
        print("❌ Invalid choice. Please select again.")

    # QTY selection (any positive multiple of 75 allowed)
    while True:
        QTY = input("\nEnter QTY (must be a multiple of 75): ").strip()
        if QTY.isdigit() and int(QTY) > 0 and int(QTY) % 75 == 0:
            QTY = int(QTY)
            break
        print("❌ Invalid quantity. Please enter a positive multiple of 75 (e.g., 75, 150, 225, 300, ...)")


    # Intraday selection
    while True:
        INTRADAY = input("\nSelect INTRADAY (yes, no): ").strip().lower()
        if INTRADAY in ["yes", "no"]:
            break
        print("❌ Please enter yes or no.")

    # Real Trade selection
    while True:
        REAL_TRADE = input("\nSelect REAL TRADE (yes, no): ").strip().lower()
        if REAL_TRADE in ["yes", "no"]:
            break
        print("❌ Please enter yes or no.")

    # Expiry selection
    expiries = ["NEXT_WEEK", "LAST"]
    print("\nSelect EXPIRY:")
    for i, e in enumerate(expiries, 1):
        print(f"{i}. {e}")
    while True:
        choice = input("Enter choice number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(expiries):
            EXPIRY = expiries[int(choice) - 1]
            break
        print("❌ Invalid choice. Please select again.")

    # Nearest LTP - must be number
    while True:
        NEAREST_LTP = input("\nEnter NEAREST_LTP (number): ").strip()
        if NEAREST_LTP.replace('.', '', 1).isdigit():
            NEAREST_LTP = float(NEAREST_LTP)
            break
        print("❌ Please enter a valid number.")

    # Rollover Trade selection
    while True:
        ROLLOVER = input("\nSelect ROLLOVER TRADE (yes, no): ").strip().lower()
        if ROLLOVER in ["yes", "no"]:
            break
        print("❌ Please enter yes or no.")

    # Return as dictionary
    new_config = {
        "USER_ID": USER_ID,
        "KEY": KEY,
        "STRATEGY": STRATEGY,
        "INTERVAL": INTERVAL,
        "QTY": int(QTY),
        "INTRADAY": INTRADAY,
        "REAL_TRADE": REAL_TRADE,
        "NEW_TRADE": "yes",
        "EXPIRY": EXPIRY,
        "NEAREST_LTP": NEAREST_LTP,
        "ROLLOVER": ROLLOVER
    }

    trade_save = save_trade_config(new_config)
    




# basic logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def update_trade_config():
    # Interactive update flow that includes NEW_TRADE (with validation and ability to keep current values).
    try:
        conn = sqlite3.connect(DB_FILE)                                   # open DB connection
        c = conn.cursor()                                                 # create cursor for executing SQL

        user_id = input("\nEnter USER_ID: ").strip()                      # prompt for USER_ID and strip whitespace
        if not user_id:                                                   # if user entered nothing
            print("❌ USER_ID is required. Cancelling.")                   # notify user about cancellation
            conn.close()                                                  # close DB connection
            return                                                        # exit the function early

        # Fetch configs and include NEW_TRADE column in the SELECT
        c.execute(
            "SELECT KEY, STRATEGY, INTERVAL, QTY, NEAREST_LTP, INTRADAY, NEW_TRADE, TRADE, EXPIRY, ROLLOVER "  # include NEW_TRADE and ROLLOVER in selection
            "FROM trade_config WHERE USER_ID = ?",
            (user_id,)
        )
        configs = c.fetchall()                                             # fetch all matching configs

        if not configs:                                                    # if no configs found
            print("❌ No trade configs found for this USER_ID.")            # notify user
            conn.close()                                                   # close DB connection
            return                                                         # exit function

        # Show the list of available configs for selection
        print(f"\nAvailable Configs for USER_ID={user_id}:")                # header for choices
        for idx, row in enumerate(configs, start=1):                       # iterate over fetched rows
            print(f"{idx}. KEY={row[0]}, STRATEGY={row[1]}, INTERVAL={row[2]}, QTY={row[3]}")  # print summary

        choice = input("\nSelect config number to update (or press Enter to cancel): ").strip()  # prompt selection
        if choice == "":                                                   # if user pressed Enter
            print("Cancelled.")                                            # print cancelled
            conn.close()                                                   # close DB connection
            return                                                         # exit function
        if not choice.isdigit() or not (1 <= int(choice) <= len(configs)): # validate numeric choice
            print("❌ Invalid selection. Cancelling.")                      # invalid -> notify
            conn.close()                                                   # close DB
            return                                                         # exit

        selected = configs[int(choice) - 1]                                 # get the selected row tuple
        key = selected[0]                                                   # KEY is first column in selected tuple

        # Print existing values so user can see before updating
        print("\n📌 Existing Config Details:")                                # header
        fields = ["KEY", "STRATEGY", "INTERVAL", "QTY", "NEAREST_LTP", "INTRADAY", "NEW_TRADE", "TRADE", "EXPIRY", "ROLLOVER"]  # field names
        for f, v in zip(fields, selected):                                   # iterate field-name + value pairs
            print(f"{f}: {v}")                                               # print each field and its current value

        # --- Strategy selection with validation (Enter to keep current) ---
        strategies = ["PARALLEL_EMA", "GOD_EMA", "HDSTRATEGY"]                # allowed strategies
        print("\nSelect STRATEGY (press Enter to keep current):")             # show prompt header
        for i, s in enumerate(strategies, start=1):                          # enumerate options
            print(f"{i}. {s}")                                                # print options numbered
        while True:                                                           # loop until valid input
            s_choice = input(f"Enter choice number or name [{selected[1]}]: ").strip()  # prompt user
            if s_choice == "":                                                # keep current if blank
                new_strategy = selected[1]                                     # assign existing
                break                                                          # break loop
            if s_choice.isdigit() and 1 <= int(s_choice) <= len(strategies):   # numeric selection valid
                new_strategy = strategies[int(s_choice) - 1]                   # map numeric to strategy
                break                                                          # done
            if s_choice.upper() in strategies:                                 # exact name match (case-insensitive)
                new_strategy = s_choice.upper()                                # normalize and assign
                break                                                          # done
            print("❌ Invalid strategy. Choose by number or exact name from the list.")  # invalid -> retry

        # --- Interval selection with validation (Enter to keep current) ---
        intervals = ["30minute", "60minute"]                                  # allowed intervals
        print("\nSelect INTERVAL (press Enter to keep current):")              # prompt header
        for i, iv in enumerate(intervals, start=1):                            # enumerate intervals
            print(f"{i}. {iv}")                                                # print options
        while True:                                                             # loop until valid
            iv_choice = input(f"Enter choice number or value [{selected[2]}]: ").strip()  # prompt
            if iv_choice == "":                                                 # keep current if blank
                new_interval = selected[2]                                      # assign existing
                break                                                           # done
            if iv_choice.isdigit() and 1 <= int(iv_choice) <= len(intervals):   # numeric valid
                new_interval = intervals[int(iv_choice) - 1]                    # map numeric to value
                break                                                           # done
            if iv_choice.lower() in [x.lower() for x in intervals]:             # typed value valid (case-insensitive)
                for iv in intervals:                                            # normalize to stored casing
                    if iv_choice.lower() == iv.lower():                         # find matching case variant
                        new_interval = iv                                       # assign normalized value
                        break
                break                                                           # done
            print("❌ Invalid interval. Choose by number or exact value from the list.")  # invalid -> retry

        # --- QTY validation (multiple of 75) ---
        while True:                                                              # loop until valid qty
            new_qty_raw = input(f"Update QTY (multiple of 75) [{selected[3]}]: ").strip()  # prompt
            if new_qty_raw == "":                                                # keep current if blank
                new_qty = selected[3]                                             # use existing
                break                                                            # done
            if new_qty_raw.isdigit() and int(new_qty_raw) > 0 and int(new_qty_raw) % 75 == 0:  # validate multiple of 75
                new_qty = int(new_qty_raw)                                       # convert to int
                break                                                            # done
            print("❌ Quantity must be a positive multiple of 75. Examples: 75,150,225,...")  # invalid -> retry

        # --- NEAREST_LTP validation (numeric) ---
        while True:                                                              # loop until valid numeric LTP
            new_ltp_raw = input(f"Update NEAREST_LTP [{selected[4]}]: ").strip()  # prompt
            if new_ltp_raw == "":                                                # keep current if blank
                new_ltp = selected[4]                                             # use existing LTP
                break                                                            # done
            try:
                new_ltp = float(new_ltp_raw)                                      # try convert to float
                break                                                             # success -> break
            except ValueError:                                                    # conversion failed
                print("❌ Please enter a valid number for NEAREST_LTP (e.g., 25000 or 25000.5).")  # error msg

        # --- INTRADAY validation (yes/no) ---
        while True:                                                              # loop until valid answer
            new_intraday_raw = input(f"Update INTRADAY (yes/no) [{selected[5]}]: ").strip()  # prompt
            if new_intraday_raw == "":                                           # keep current if blank
                new_intraday = selected[5]                                        # assign existing
                break                                                            # done
            if new_intraday_raw.lower() in ("yes", "no"):                         # accept yes/no
                new_intraday = new_intraday_raw.lower()                           # normalize to lowercase
                break                                                            # done
            print("❌ Please enter 'yes' or 'no' (or press Enter to keep current).")  # invalid -> retry

        # --- NEW_TRADE validation (yes/no) (this was missing before) ---
        while True:                                                              # loop until valid NEW_TRADE
            new_new_trade_raw = input(f"Update NEW_TRADE (yes/no) [{selected[6]}]: ").strip()  # prompt (default is selected[6])
            if new_new_trade_raw == "":                                          # keep current if blank
                new_new_trade = selected[6]                                       # use existing NEW_TRADE value
                break                                                            # done
            if new_new_trade_raw.lower() in ("yes", "no"):                        # accept yes/no
                new_new_trade = new_new_trade_raw.lower()                         # normalize
                break                                                            # done
            print("❌ Please enter 'yes' or 'no' (or press Enter to keep current).")  # invalid -> retry

        # --- REAL_TRADE / TRADE validation (yes/no) ---
        while True:                                                              # loop until valid REAL_TRADE
            new_trade_raw = input(f"Update REAL_TRADE (yes/no) [{selected[7]}]: ").strip()  # prompt
            if new_trade_raw == "":                                              # keep current if blank
                new_trade = selected[7]                                           # use existing REAL_TRADE value
                break                                                            # done
            if new_trade_raw.lower() in ("yes", "no"):                            # accept yes/no
                new_trade = new_trade_raw.lower()                                 # normalize
                break                                                            # done
            print("❌ Please enter 'yes' or 'no' (or press Enter to keep current).")  # invalid -> retry

        # --- EXPIRY selection with validation (Enter to keep current) ---
        expiries = ["NEXT_WEEK", "LAST"]                                          # allowed expiries
        print("\nSelect EXPIRY (press Enter to keep current):")                    # prompt header
        for i, e in enumerate(expiries, start=1):                                  # enumerate options
            print(f"{i}. {e}")                                                     # print option
        while True:                                                                # loop until valid
            e_choice = input(f"Enter choice number or value [{selected[8]}]: ").strip()  # prompt
            if e_choice == "":                                                     # keep current if blank
                new_expiry = selected[8]                                           # assign existing
                break                                                              # done
            if e_choice.isdigit() and 1 <= int(e_choice) <= len(expiries):         # numeric valid
                new_expiry = expiries[int(e_choice) - 1]                           # map numeric to expiry
                break                                                              # done
            if e_choice.upper() in expiries:                                       # exact name match
                new_expiry = e_choice.upper()                                      # normalize
                break                                                              # done
            print("❌ Invalid expiry. Choose by number or exact name from the list.")  # invalid -> retry
        # --- ROLLOVER validation (yes/no) ---
        while True:                                                              # loop until valid answer
            new_rollover_raw = input(f"Update ROLLOVER (yes/no) [{selected[9]}]: ").strip()  # prompt
            if new_rollover_raw == "":                                           # keep current if blank
                new_rollover = selected[9]                                        # assign existing
                break                                                            # done
            if new_rollover_raw.lower() in ("yes", "no"):                         # accept yes/no
                new_rollover = new_rollover_raw.lower()                           # normalize to lowercase
                break                                                            # done
            print("❌ Please enter 'yes' or 'no' (or press Enter to keep current).")  # invalid -> retry
        # --- Apply update to DB including NEW_TRADE ---
        sql = """
            UPDATE trade_config
            SET STRATEGY = ?, INTERVAL = ?, QTY = ?, NEAREST_LTP = ?, INTRADAY = ?, NEW_TRADE = ?, TRADE = ?, EXPIRY = ?, LST_UPDT_DT = ?, ROLLOVER = ?
            WHERE USER_ID = ? AND KEY = ?
        """                                                                        # SQL update template including NEW_TRADE
        params = (
            new_strategy,                                                           # new STRATEGY
            new_interval,                                                           # new INTERVAL
            new_qty,                                                                # new QTY
            new_ltp,                                                                # new NEAREST_LTP
            new_intraday,                                                           # new INTRADAY
            new_new_trade,                                                          # new NEW_TRADE (added)
            new_trade,                                                              # new REAL_TRADE
            new_expiry,                                                             # new EXPIRY
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),                  # update timestamp
            new_rollover,                                                          # new ROLLOVER
            user_id,                                                                # WHERE USER_ID
            key                                                                    # WHERE KEY
            
        )                                                                         # end params tuple
        c.execute(sql, params)                                                     # execute the update with params
        conn.commit()                                                              # commit the transaction
        conn.close()                                                               # close DB connection

        logging.info(f"✅ Trade config updated for USER_ID={user_id}, KEY={key}")    # log success
        print(f"\n✅ Trade config updated successfully for USER_ID={user_id}, KEY={key}")  # user-facing success msg

    except Exception as e:                                                          # catch any exception
        print(f"❌ Error updating trade config: {e}")                                # print error
        logging.error(f"❌ Error updating trade config: {e}")                         # log error



def main():
    print("\n📌 Trade Config Manager")
    print("1. Create new trade config")
    print("2. Update existing trade config")
    print("3. Exit")

    while True:
        choice = input("\nSelect an option (1/2/3): ").strip()

        if choice == "1":
            new_trade_config()   # Call your function to create new config
            break
        elif choice == "2":
            update_trade_config()  # Call your function to update existing config
            break
        elif choice == "3":
            print("Exiting Trade Config Manager. 👋")
            break
        else:
            print("❌ Invalid choice. Please select 1, 2, or 3.")

if __name__ == "__main__":
    main()
    
    
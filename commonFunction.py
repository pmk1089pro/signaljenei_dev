import time
import datetime
from datetime import timedelta
import numpy as np
import pandas as pd
import sqlite3
import logging
from kitefunction import  get_historical_df, place_option_hybrid_order, get_avgprice_from_positions, get_token_for_symbol, get_quotes_with_retry, get_profile
from telegrambot import send_telegram_message, send_telegram_message_admin
from config import  DB_FILE, HARDLIMIT, HEDGE_NEAREST_LTP, HEDGE_STRIKE_DIFF,SYMBOL,SEGMENT, CANDLE_DAYS as DAYS, REQUIRED_CANDLES, LOG_FILE,INSTRUMENTS_FILE, OPTION_SYMBOL, SERVER
import os

# pd.set_option('future.no_silent_downcasting', True)

logging.basicConfig(
    filename=LOG_FILE,
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
instrument_token = get_token_for_symbol(SYMBOL)

if instrument_token is None:
    logging.error(f"❌ Instrument token for {SYMBOL} not found. Exiting.")
    exit(1)
logging.info(f"ℹ️ Instrument token for {SYMBOL}: {instrument_token} at current time {current_time}")

instruments_df = pd.read_csv(INSTRUMENTS_FILE)


def log_instruments_file_mod_time(filename):
    
    try:
        mod_time = time.ctime(os.path.getmtime(filename))
        print(f"ℹ️ {filename} last modified: {mod_time}")
        logging.info(f"ℹ️ {filename} last modified: {mod_time}")
    except Exception as e:
        print(f"❌ Failed to get modification time of {filename}: {e}")
        logging.error(f"❌ Failed to get modification time of {filename}: {e}")


def init_db():
    try:
        # Connect to SQLite database (will create file if it doesn't exist)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Create completed_trades table
        c.execute("""
            CREATE TABLE IF NOT EXISTS completed_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal TEXT,
                spot_entry REAL,
                option_symbol TEXT,
                strike INTEGER,
                expiry TEXT,
                option_sell_price REAL,
                entry_time TEXT,
                spot_exit REAL,
                option_buy_price REAL,
                exit_time TEXT,
                pnl REAL,
                qty INTEGER,
                interval TEXT,
                real_trade TEXT,
                entry_reason TEXT,
                exit_reason TEXT,
                expiry_type TEXT,
                strategy TEXT,
                key TEXT,
                user_id INTEGER,
                hedge_option_symbol TEXT,
                hedge_strike INTEGER,
                hedge_option_buy_price REAL,
                hedge_qty INTEGER,
                hedge_entry_time TEXT,
                hedge_exit_time TEXT,
                hedge_option_sell_price REAL,
                hedge_pnl REAL,
                total_pnl REAL
                
            )
        """)

        # Create open_trades table
        c.execute("""
            CREATE TABLE IF NOT EXISTS open_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal TEXT,
                spot_entry REAL,
                option_symbol TEXT,
                strike INTEGER,
                expiry TEXT,
                option_sell_price REAL,
                entry_time TEXT,
                qty INTEGER,
                interval TEXT,
                real_trade TEXT,
                entry_reason TEXT,
                expiry_type TEXT,
                strategy TEXT,
                key TEXT,
                user_id INTEGER,
                hedge_option_symbol TEXT,
                hedge_strike INTEGER,
                hedge_option_buy_price REAL,
                hedge_qty INTEGER,
                hedge_entry_time TEXT,
                trade_status TEXT
            )
        """)

        # Create user_dtls table
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_dtls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                kite_username TEXT,
                kite_password TEXT,
                kite_api_secret TEXT,
                kite_api_key TEXT,
                kite_totp_token TEXT,
                telegram_chat_id TEXT,
                telegram_token TEXT,
                active_flag INTEGER,
                crt_dt TEXT
            )
        """)

        # Create trade_config table
        c.execute("""
            CREATE TABLE IF NOT EXISTS trade_config (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                USER_ID INTEGER,
                KEY TEXT UNIQUE,
                INTERVAL TEXT,
                LOT TEXT,
                NEAREST_LTP INTEGER,
                INTRADAY TEXT,
                NEW_TRADE TEXT,
                REAL_TRADE TEXT,
                EXPIRY TEXT,
                STRATEGY TEXT,
                CRT_DT TEXT,
                LST_UPDT_DT TEXT,
                HEDGE_TYPE TEXT,
                HEDGE_ROLLOVER_TYPE TEXT,
                MONTHLY_STOPLOSS INTEGER,
                ACTIVATE_MONTHLY_SL INTEGER DEFAULT 0,
                STOPLOSS_PER_TRADE INTEGER,
                ACTIVATE_SL_PER_TRADE INTEGER DEFAULT 0,
                THREAD_STATUS   TEXT DEFAULT 'ACTIVE',  -- Values: 'ACTIVE', 'BLOCKED'
	            LAST_ERROR_REASON	TEXT,               -- Stores mismatch/partial fill details
	            ERROR_TIMESTAMP	TEXT,                   -- Stores exactly when the thread died
                
                FOREIGN KEY(USER_ID) REFERENCES user_dtls(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS "kite_session" (
                "session_pk"	INTEGER,
                "user_id"	INTEGER,
                "username"	TEXT,
                "access_token"	TEXT,
                "api_key"	TEXT,
                "api_secret"	TEXT,
                "crt_dt"	TEXT,
                "lst_updt_dt"	TEXT,
                PRIMARY KEY("session_pk"),
                FOREIGN KEY("user_id") REFERENCES "user_dtls"("id")
            )
        """)

        # Commit changes and close connection
        conn.commit()
        print(f"Database initialized successfully at {os.path.abspath(DB_FILE)}")
    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    finally:
        if conn:
            conn.close()

def save_trade_config(new_config):
    """
    Save a new trade configuration into the trade_config table.
    Prevents duplicate KEY for the same USER_ID.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Check for duplicate (USER_ID + KEY)
        c.execute("""
            SELECT COUNT(*) FROM trade_config 
            WHERE USER_ID = ? AND KEY = ?
        """, (new_config.get("USER_ID"), new_config.get("KEY")))
        exists = c.fetchone()[0]

        if exists > 0:
            logging.warning(
                f"⚠️ Trade config already exists for USER_ID={new_config.get('USER_ID')} "
                f"and KEY={new_config.get('KEY')} (skipping insert)."
            )
            send_telegram_message_admin(f"⚠️ Same Key are not Allowed. Config already exists for USER_ID={new_config.get('USER_ID')} and KEY={new_config.get('KEY')}. Please use a unique KEY for each config." )
            print("❌ Duplicate entry. Config already exists.")
            conn.close()
            return False

        # Insert new record
        sql = """
            INSERT INTO trade_config (
                USER_ID, KEY, INTERVAL, LOT, NEAREST_LTP, INTRADAY, NEW_TRADE, REAL_TRADE,
                EXPIRY, STRATEGY, CRT_DT, LST_UPDT_DT, HEDGE_TYPE, HEDGE_ROLLOVER_TYPE, MONTHLY_STOPLOSS, ACTIVATE_MONTHLY_SL, STOPLOSS_PER_TRADE, ACTIVATE_SL_PER_TRADE, THREAD_STATUS, LAST_ERROR_REASON, ERROR_TIMESTAMP
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            new_config.get("USER_ID"),
            new_config.get("KEY"),
            new_config.get("INTERVAL"),
            new_config.get("LOT"),
            new_config.get("NEAREST_LTP"),
            new_config.get("INTRADAY"),
            new_config.get("NEW_TRADE"),
            new_config.get("REAL_TRADE"),
            new_config.get("EXPIRY"),
            new_config.get("STRATEGY"),
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            new_config.get("HEDGE_TYPE"),
            new_config.get("HEDGE_ROLLOVER_TYPE"),
            new_config.get("MONTHLY_STOPLOSS"),
            new_config.get("ACTIVATE_MONTHLY_SL", 0),
            new_config.get("STOPLOSS_PER_TRADE"),
            new_config.get("ACTIVATE_SL_PER_TRADE", 0),
            new_config.get("THREAD_STATUS", "ACTIVE"),
            new_config.get("LAST_ERROR_REASON", ""),
            new_config.get("ERROR_TIMESTAMP", "")
        )
        c.execute(sql, params)
        conn.commit()
        conn.close()
        logging.info(f"✅ Trade config saved for key: {new_config.get('KEY')}")
        return True

    except Exception as e:
        print(f"❌{new_config.get('KEY')} Error saving trade config: {e}")
        logging.error(f"❌{new_config.get('KEY')} Error saving trade config: {e}")


def get_trade_configs(user_id):
    try:
        conn = sqlite3.connect(DB_FILE)  # change to your DB
        cursor = conn.cursor()
        cursor.execute("""
            SELECT USER_ID, KEY, STRATEGY, INTERVAL, LOT, NEAREST_LTP, INTRADAY, NEW_TRADE,
                REAL_TRADE, EXPIRY, HEDGE_TYPE, HEDGE_ROLLOVER_TYPE, MONTHLY_STOPLOSS, ACTIVATE_MONTHLY_SL, STOPLOSS_PER_TRADE, ACTIVATE_SL_PER_TRADE, THREAD_STATUS, LAST_ERROR_REASON, ERROR_TIMESTAMP
            FROM trade_config 
            WHERE USER_ID = ? AND THREAD_STATUS != 'DEACTIVE'
			GROUP by USER_ID, KEY, STRATEGY, INTERVAL, LOT, NEAREST_LTP, INTRADAY, NEW_TRADE,
                REAL_TRADE, EXPIRY, HEDGE_TYPE, HEDGE_ROLLOVER_TYPE, MONTHLY_STOPLOSS, ACTIVATE_MONTHLY_SL, STOPLOSS_PER_TRADE, ACTIVATE_SL_PER_TRADE
        """, (user_id,))

        rows = cursor.fetchall()
        conn.close()

        configs = {}
        for row in rows:
            (
                USER_ID, KEY, STRATEGY, INTERVAL, LOT, NEAREST_LTP, INTRADAY, NEW_TRADE,
                REAL_TRADE, EXPIRY, HEDGE_TYPE, HEDGE_ROLLOVER_TYPE, MONTHLY_STOPLOSS, ACTIVATE_MONTHLY_SL, STOPLOSS_PER_TRADE, ACTIVATE_SL_PER_TRADE, THREAD_STATUS, LAST_ERROR_REASON, ERROR_TIMESTAMP
            ) = row

            config_dict = {
                "INTERVAL": INTERVAL,
                "LOT": LOT,
                "NEAREST_LTP": NEAREST_LTP,
                "INTRADAY": INTRADAY,
                "NEW_TRADE": NEW_TRADE,
                "REAL_TRADE": REAL_TRADE,
                "EXPIRY": EXPIRY,
                "HEDGE_TYPE": HEDGE_TYPE,
                "HEDGE_ROLLOVER_TYPE": HEDGE_ROLLOVER_TYPE,
                "STRATEGY": STRATEGY,
                "KEY": KEY,
                "MONTHLY_STOPLOSS": MONTHLY_STOPLOSS,
                "ACTIVATE_MONTHLY_SL": ACTIVATE_MONTHLY_SL,
                "STOPLOSS_PER_TRADE": STOPLOSS_PER_TRADE,
                "ACTIVATE_SL_PER_TRADE": ACTIVATE_SL_PER_TRADE,
                "THREAD_STATUS": THREAD_STATUS,
                "LAST_ERROR_REASON": LAST_ERROR_REASON,
                "ERROR_TIMESTAMP": ERROR_TIMESTAMP
            }
            configs[KEY] = config_dict
        return configs
    

    except Exception as e:
        print(f"❌{user_id} Error fetching trade configs: {e}")
        logging.error(f"❌{user_id} Error fetching trade configs: {e}")
        send_telegram_message_admin(f"❌{user_id} Error fetching trade configs: {e}")
        return []

def get_keywise_trade_config(key):
    try:
        conn = sqlite3.connect(DB_FILE)  # change to your DB
        cursor = conn.cursor()
        cursor.execute("""
            SELECT USER_ID, KEY, STRATEGY, INTERVAL, LOT, NEAREST_LTP, INTRADAY, NEW_TRADE,
                REAL_TRADE, EXPIRY, HEDGE_TYPE, HEDGE_ROLLOVER_TYPE, MONTHLY_STOPLOSS, ACTIVATE_MONTHLY_SL, STOPLOSS_PER_TRADE, ACTIVATE_SL_PER_TRADE, THREAD_STATUS, LAST_ERROR_REASON, ERROR_TIMESTAMP
            FROM trade_config 
            WHERE KEY = ? AND THREAD_STATUS != 'DEACTIVE'
			GROUP by USER_ID, KEY, STRATEGY, INTERVAL, LOT, NEAREST_LTP, INTRADAY, NEW_TRADE,
                REAL_TRADE, EXPIRY, HEDGE_TYPE, HEDGE_ROLLOVER_TYPE, MONTHLY_STOPLOSS, ACTIVATE_MONTHLY_SL, STOPLOSS_PER_TRADE, ACTIVATE_SL_PER_TRADE
        """, (key,))

        rows = cursor.fetchall()
        conn.close()

        configs = {}
        for row in rows:
            (
                USER_ID, KEY, STRATEGY, INTERVAL, LOT, NEAREST_LTP, INTRADAY, NEW_TRADE,
                REAL_TRADE, EXPIRY, HEDGE_TYPE, HEDGE_ROLLOVER_TYPE, MONTHLY_STOPLOSS, ACTIVATE_MONTHLY_SL, STOPLOSS_PER_TRADE, ACTIVATE_SL_PER_TRADE, THREAD_STATUS, LAST_ERROR_REASON, ERROR_TIMESTAMP
            ) = row

            config_dict = {
                "INTERVAL": INTERVAL,
                "LOT": LOT,
                "NEAREST_LTP": NEAREST_LTP,
                "INTRADAY": INTRADAY,
                "NEW_TRADE": NEW_TRADE,
                "REAL_TRADE": REAL_TRADE,
                "EXPIRY": EXPIRY,
                "HEDGE_TYPE": HEDGE_TYPE,
                "HEDGE_ROLLOVER_TYPE": HEDGE_ROLLOVER_TYPE,
                "STRATEGY": STRATEGY,
                "KEY": KEY,
                "MONTHLY_STOPLOSS": MONTHLY_STOPLOSS,
                "ACTIVATE_MONTHLY_SL": ACTIVATE_MONTHLY_SL,
                "STOPLOSS_PER_TRADE": STOPLOSS_PER_TRADE,
                "ACTIVATE_SL_PER_TRADE": ACTIVATE_SL_PER_TRADE,
                "THREAD_STATUS": THREAD_STATUS,
                "LAST_ERROR_REASON": LAST_ERROR_REASON,
                "ERROR_TIMESTAMP": ERROR_TIMESTAMP
            }
            
        return config_dict
    

    except Exception as e:
        print(f"❌{key} | Error fetching trade configs: {e}")
        logging.error(f"❌{key} | Error fetching trade configs: {e}")
        send_telegram_message_admin(f"❌{key} | Error fetching trade configs: {e}")
        return []


def generate_god_signals(df, len1=8, len2=20):
    df['ema1'] = df['close'].ewm(span=len1, adjust=False).mean()
    df['ema2'] = df['close'].ewm(span=len2, adjust=False).mean()
    df['crossover'] = (df['ema1'] > df['ema2']) & (df['ema1'].shift(1) <= df['ema2'].shift(1))
    df['crossunder'] = (df['ema1'] < df['ema2']) & (df['ema1'].shift(1) >= df['ema2'].shift(1))
    trend = []
    current_trend = 0
    for i in range(len(df)):
        if df['crossover'].iloc[i]:
            current_trend = 1
        elif df['crossunder'].iloc[i]:
            current_trend = -1
        trend.append(current_trend)
    df['trend'] = trend
    df['twoAbove'] = (df['close'] > df['ema1']) & (df['close'] > df['ema2']) & \
                     (df['close'].shift(1) > df['ema1'].shift(1)) & (df['close'].shift(1) > df['ema2'].shift(1))
    df['twoBelow'] = (df['close'] < df['ema1']) & (df['close'] < df['ema2']) & \
                     (df['close'].shift(1) < df['ema1'].shift(1)) & (df['close'].shift(1) < df['ema2'].shift(1))
    buy_signals = []
    sell_signals = []
    buy_fired = False
    sell_fired = False
    prev_trend = 0
    for i in range(len(df)):
        curr_trend = df['trend'][i]
        new_cross = curr_trend != prev_trend
        if new_cross:
            buy_fired = False
            sell_fired = False
        buy = curr_trend == 1 and df['twoAbove'][i] and not buy_fired
        sell = curr_trend == -1 and df['twoBelow'][i] and not sell_fired
        buy_signals.append(buy)
        sell_signals.append(sell)
        if buy:
            buy_fired = True
        if sell:
            sell_fired = True
        prev_trend = curr_trend
    df['buySignal'] = buy_signals
    df['sellSignal'] = sell_signals
    return df

def wait_until_next_candle(config):
    now = datetime.datetime.now()
    gap = int(config['INTERVAL'].replace("minute", ""))
    start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    minutes_since_start = (now - start_time).seconds // 60
    wait_min = gap - (minutes_since_start % gap)
    end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)
    next_candle_time = now + timedelta(minutes=wait_min)
    if next_candle_time > end_time:
        wait_sec = (end_time - now).total_seconds()
        print(f"⏳{config['KEY']} | Next candle would be after market close. Waiting only until {end_time.strftime('%H:%M:%S')}")
        logging.info(f"⏳{config['KEY']} | Next candle would be after market close. Waiting only until {end_time.strftime('%H:%M:%S')}")
    else:
        wait_sec = wait_min * 60 - now.second + 2
        next_candle_time = now + timedelta(seconds=wait_sec)
        print(f"⏳{config['KEY']} | Waiting {max(2, int(wait_sec))} seconds until next candle at {next_candle_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logging.info(f"⏳{config['KEY']} | Waiting {max(2, int(wait_sec))} seconds until next candle at {next_candle_time.strftime('%Y-%m-%d %H:%M:%S')}")
    time.sleep(max(2, int(wait_sec)))


def get_lot_size(config, instruments_df):
    """
    Return lot_size from instruments_df according to config['EXPIRY'].
    Filters by OPTION_SYMBOL, SEGMENT, and expiry type.
    """
    try:
        df = instruments_df.copy()
        today = pd.Timestamp.today().normalize()
        
        if config['EXPIRY'] == "NEXT_WEEK":
            days = 7
        elif config['EXPIRY'] == "NEXT_TO_NEXT_WEEK":
            days = 14
        else:
            days = 0
        
        df_filtered = df[
            (df['name'] == OPTION_SYMBOL) &
            (df['segment'] == SEGMENT)
        ].copy()
        
        if df_filtered.empty:
            logging.warning(f"⚠️{config['KEY']} | No instruments found for {OPTION_SYMBOL}")
            return None
        
        df_filtered['expiry'] = pd.to_datetime(df_filtered['expiry'])
        
        if config['EXPIRY'] == "LAST":
            if today.day <= 15:
                month_ref = today
            else:
                month_ref = (today + pd.DateOffset(months=1)).replace(day=1)
            next_month = month_ref.replace(day=28) + timedelta(days=4)
            last_day_of_month = next_month - timedelta(days=next_month.day)
            last_tuesday = last_day_of_month - timedelta(days=(last_day_of_month.weekday() - 1) % 7)
            target_expiry = last_tuesday
        else:
            days_until_tuesday = (1 - today.weekday() + 7) % 7
            this_week_tuesday = today + timedelta(days=days_until_tuesday)
            target_expiry = this_week_tuesday + timedelta(days=days)
        
        week_start = target_expiry - timedelta(days=target_expiry.weekday())
        week_end = week_start + timedelta(days=6)
        
        target_options = df_filtered[
            (df_filtered['expiry'] >= week_start) & (df_filtered['expiry'] <= week_end)
        ]
        
        if target_options.empty:
            logging.warning(f"⚠️{config['KEY']} | No options found for expiry type {config['EXPIRY']}")
            return None
        
        lot_size = int(target_options.iloc[0]['lot_size'])
        logging.info(f"✅{config['KEY']} | Lot size retrieved: {lot_size} for expiry {config['EXPIRY']}")
        return lot_size
        
    except Exception as e:
        print(f"❌{config['KEY']} | Error getting lot size: {e}")
        logging.error(f"❌{config['KEY']} | Error getting lot size: {e}")
        return None

def get_robust_optimal_option(signal, spot, nearest_price, instruments_df, config, user, hedge_offset=200, hedge_required=True):
    from kitefunction import get_entire_quote, get_kite_client
    kite = get_kite_client(user)
    print(f"{config['KEY']} | Start Search: {datetime.datetime.now()} | Target: {nearest_price}")
    logging.info(f"{config['KEY']} | Start Search: {datetime.datetime.now()} | Target: {nearest_price}")



    # --- 1. PRE-CALCULATE EXPIRY (OUTSIDE LOOP) ---
    days = 7 if config.get('EXPIRY') == "NEXT_WEEK" else 14 if config.get('EXPIRY') == "NEXT_TO_NEXT_WEEK" else 0 
    today = pd.Timestamp.today().normalize()
    
    if config.get('EXPIRY') == "LAST":
        month_ref = today if today.day <= 15 else (today + pd.DateOffset(months=1)).replace(day=1)
        next_month = month_ref.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        target_expiry = last_day - timedelta(days=(last_day.weekday() - 1) % 7)
    else:
        days_until_tuesday = (1 - today.weekday() + 7) % 7
        target_expiry = today + timedelta(days=days_until_tuesday + days)

    week_start = target_expiry - timedelta(days=target_expiry.weekday())
    week_end = week_start + timedelta(days=6)

    # --- 2. FAST PRE-FILTERING (OUTSIDE LOOP) ---
    opt_type = "PE" if signal == "BUY" else "CE"
    df = instruments_df.copy()
    df['expiry'] = pd.to_datetime(df['expiry'])
    
    # Filter by Name and Expiry Window once
    fast_df = df[
        (df['name'] == OPTION_SYMBOL) & 
        (df['tradingsymbol'].str.endswith(opt_type)) &
        (df['expiry'] >= week_start) & 
        (df['expiry'] <= week_end)
    ].copy()

    if fast_df.empty:
        return None, None, None, None, None

    # Create a fast lookup map for strikes
    strike_map = fast_df.set_index('strike').to_dict('index')

    # --- 3. BULK PRICE FETCH (ONE API CALL) ---
    # Get all potential symbols near the spot to avoid individual API calls
    fast_df['dist'] = (fast_df['strike'] - spot).abs()
    candidate_symbols = ["NFO:" + s for s in fast_df.nsmallest(30, 'dist')['tradingsymbol'].tolist()]
    

    all_quotes = kite.ltp(candidate_symbols)

    # --- 4. THE SEARCH LOOP (IN-MEMORY) ---
    strike = int(round(spot / 100.0) * 100)
    strike_step = -100 if signal == "BUY" else 100
    hedge_direction = -1 if signal == "BUY" else 1 
    best_option, best_ltp_diff = None, float('inf')

    for _ in range(100):
        if strike not in strike_map:
            strike += strike_step
            continue
            
        opt = strike_map[strike]
        opt_symbol = opt['tradingsymbol']
        expiry_val = opt['expiry']
        
        # Get pre-fetched price
        m_ltp = all_quotes.get("NFO:" + opt_symbol, {}).get('last_price', 0)
        
        # If not in bulk fetch, fallback to single quote (rare)
        if m_ltp == 0:
            m_ltp = get_entire_quote(opt_symbol, user).get('last_price', 0)

        if m_ltp > 0:
            effective_price = m_ltp
            hedge_symbol, hedge_price = None, None
            hedge_liquid = True if not hedge_required else False

            if hedge_required:
                h_strike = strike + (hedge_offset * hedge_direction)
                if h_strike in strike_map:
                    hedge_symbol = strike_map[h_strike]['tradingsymbol']
                    # Bulk check or single check for hedge
                    h_ltp = all_quotes.get("NFO:"+hedge_symbol, {}).get('last_price', 0)
                    if h_ltp == 0:
                        h_quote = get_entire_quote(hedge_symbol, user)
                        h_ltp = h_quote.get('last_price', 0) or (h_quote.get('buy_price', 0) + h_quote.get('sell_price', 0)) / 2
                    
                    if h_ltp > 0:
                        hedge_liquid, hedge_price = True, h_ltp
                else:
                    strike += strike_step
                    continue

            if effective_price and hedge_liquid:
                diff = abs(effective_price - nearest_price)
                if diff < best_ltp_diff:
                    best_ltp_diff = diff
                    best_option = (opt_symbol, strike, expiry_val, effective_price, hedge_symbol, hedge_price)
                
                if diff <= 5: break
                if effective_price < (nearest_price - HARDLIMIT): break
        
        strike += strike_step

    # --- 5. FINAL CHECK ---
    if best_option:
        opt_symbol, opt_strike, opt_expiry, opt_ltp, h_sym, h_ltp = best_option
        print(f"Best option found: {opt_symbol} @ {opt_ltp} with hedge {h_sym} @ {h_ltp} | Diff: {best_ltp_diff}")
        logging.info(f"{config['KEY']} | Best option: {opt_symbol} @ {opt_ltp} with hedge {h_sym} @ {h_ltp} | Diff: {best_ltp_diff}")
        if abs(opt_ltp - nearest_price) <= HARDLIMIT:
            print(f"✅ {config['KEY']} | Match: {opt_symbol} @ {opt_ltp} | Hedge: {h_sym} @{h_ltp}")
            logging.info(f"{config['KEY']} | Match: {opt_symbol} @ {opt_ltp} | Hedge: {h_sym} @{h_ltp}")
            return opt_symbol, opt_strike, opt_expiry, opt_ltp, h_sym
        else:
            print(f"⚠️ {config['KEY']} | No good match: {opt_symbol} @ {opt_ltp} | Hedge: {h_sym} @{h_ltp} | Diff: {best_ltp_diff}")
            logging.warning(f"{config['KEY']} | No good match: {opt_symbol} @ {opt_ltp} | Hedge: {h_sym} @{h_ltp} | Diff: {best_ltp_diff}")
    else:
        print(f"❌ {config['KEY']} | No valid option found near {nearest_price}")
        logging.error(f"{config['KEY']} | No valid option found near {nearest_price}")

    return None, None, None, None, None

def get_optimal_option(signal, spot, nearest_price, instruments_df, config, user):
    from kitefunction import get_entire_quote
    print(f"{config['KEY']} | Searching for optimal option. Signal: {signal}, Target: {nearest_price}")
    logging.info(f"{config['KEY']} | Searching for optimal option. Signal: {signal}, Target: {nearest_price}")
    
    
    # 1. Expiry Logic
    if config['EXPIRY'] == "NEXT_WEEK":
        days = 7
    elif config['EXPIRY'] == "NEXT_TO_NEXT_WEEK":
        days = 14
    else:
        days = 0 

    strike = int(round(spot / 100.0) * 100)
    df = instruments_df.copy()
    
    best_option = None
    best_ltp_diff = float('inf')
    
    # Define search direction
    opt_type = "PE" if signal == "BUY" else "CE"
    strike_step = -100 if signal == "BUY" else 100

    # Start Search Loop
    for _ in range(100):  # Limit search to 100 strikes to avoid infinite loops
        df_filtered = df[
            (df['name'] == OPTION_SYMBOL) &
            (df['segment'] == SEGMENT) &
            (df['strike'] == strike) &
            (df['tradingsymbol'].str.endswith(opt_type))
        ].copy()

        if df_filtered.empty:
            break

        # Expiry Calculation
        df_filtered['expiry'] = pd.to_datetime(df_filtered['expiry'])
        today = pd.Timestamp.today().normalize()

        if config['EXPIRY'] == "LAST":
            # Logic for last Tuesday of the month
            month_ref = today if today.day <= 15 else (today + pd.DateOffset(months=1)).replace(day=1)
            next_month = month_ref.replace(day=28) + timedelta(days=4)
            last_day = next_month - timedelta(days=next_month.day)
            target_expiry = last_day - timedelta(days=(last_day.weekday() - 1) % 7)
        else:
            # Logic for upcoming Tuesday
            days_until_tuesday = (1 - today.weekday() + 7) % 7
            target_expiry = today + timedelta(days=days_until_tuesday + days)

        week_start = target_expiry - timedelta(days=target_expiry.weekday())
        week_end = week_start + timedelta(days=6)
        
        target_options = df_filtered[
            (df_filtered['expiry'] >= week_start) & (df_filtered['expiry'] <= week_end)
        ].sort_values('expiry')

        if not target_options.empty:
            opt = target_options.iloc[0]
            opt_symbol = opt['tradingsymbol']
            expiry_str = opt['expiry']

            # 2. IMPROVED PRICE FETCHING (Retry + Mid-Price Fallback)
            effective_price = None
            for attempt in range(3):  # 3 Retries for API glitches
                try:
                    # Get full quote to see Bid/Ask in case LTP is 0
                    quote = get_entire_quote(opt_symbol, user) 
                    ltp = quote.get('last_price', 0)
                    bid = quote.get('buy_price', 0)
                    ask = quote.get('sell_price', 0)

                    if ltp > 0:
                        effective_price = ltp
                    elif bid > 0 and ask > 0:
                        effective_price = (bid + ask) / 2 # Use Mid-Price if illiquid
                        print(f"⚠️{config['KEY']} | {opt_symbol} LTP is 0. Using Mid-Price: {effective_price}")
                        logging.warning(f"⚠️{config['KEY']} | {opt_symbol} LTP is 0. Using Mid-Price: {effective_price}")
                    
                    if effective_price: 
                        # print(f"{config['KEY']} | Option Symbol {opt_symbol} at ltp of {effective_price}")
                        break
                except Exception as e:
                    print(f"{config['KEY']} | API Error on {opt_symbol}: {e}")
                    logging.error(f"{config['KEY']} | API Error on {opt_symbol}: {e}")
                time.sleep(0.5)

            if effective_price:
                diff = abs(effective_price - nearest_price)
                if diff < best_ltp_diff:
                    best_ltp_diff = diff
                    best_option = (opt_symbol, strike, expiry_str, effective_price)
                else:
                    # Price is starting to move away from target, stop here
                    break

        # Move to next strike
        strike += strike_step

    # 3. RELAXED FINAL CHECK
    # We want to enter even if it's slightly outside the original 10-point tolerance
    strict_tolerance = 10
    hard_limit = 25 # Allow up to 25 points difference to prevent halting entries
    
    if best_option:
        opt_symbol, opt_strike, opt_expiry, opt_ltp = best_option
        final_diff = abs(opt_ltp - nearest_price)
        
        if final_diff <= strict_tolerance:
            print(f"{config['KEY']} |  Optimal Match: {opt_symbol} at {opt_ltp}")
            logging.info(f"✅{config['KEY']} | Optimal Match: {opt_symbol} at {opt_ltp}")
            return best_option
        elif final_diff <= hard_limit:
            print(f"⚠️{config['KEY']} | Relaxed Match: {opt_symbol} at {opt_ltp} (Diff {final_diff} > {strict_tolerance}). Entering to avoid halt.")
            logging.warning(f"⚠️{config['KEY']} | Relaxed Match: {opt_symbol} at {opt_ltp} (Diff {final_diff} > {strict_tolerance}). Entering to avoid halt.")
            return best_option
        else:
            print(f"❌{config['KEY']} | Rejected: {opt_symbol} price {opt_ltp} is too far from {nearest_price}")
            logging.error(f"❌{config['KEY']} | Rejected: {opt_symbol} price {opt_ltp} is too far from {nearest_price}")

    return None, None, None, None

def get_hedge_option(signal, spot, strike, main_ltp, instruments_df, config, user):
    """
    ADDED: main_ltp parameter to compare against hedge price.
    """
    print(f"{config['KEY']} | Finding hedge for strike: {strike}, Main LTP: {main_ltp}")
    logging.info(f"{config['KEY']} | Finding hedge for strike: {strike}, Main LTP: {main_ltp}")
    
    # 1. Determine Strike Offset (STAYS FIXED as requested)
    if config['HEDGE_TYPE'] == "H-M100":
        HEDGE_STRIKE_DIFF = 100
    elif config['HEDGE_TYPE'] == "H-M200":
        HEDGE_STRIKE_DIFF = 200
    else:
        HEDGE_STRIKE_DIFF = 100 

    days = 7 if config['EXPIRY'] == "NEXT_WEEK" else 14 if config['EXPIRY'] == "NEXT_TO_NEXT_WEEK" else 0

    if signal == "BUY":
        opt_type, hedge_strike = "PE", strike - HEDGE_STRIKE_DIFF
    else:
        opt_type, hedge_strike = "CE", strike + HEDGE_STRIKE_DIFF

    # 2. Filter Instruments
    df = instruments_df.copy()
    df_filtered = df[
        (df['name'] == OPTION_SYMBOL) &
        (df['strike'] == hedge_strike) &
        (df['tradingsymbol'].str.endswith(opt_type))
    ].copy()

    if df_filtered.empty:
        logging.error(f"❌{config['KEY']} | No hedge options found for strike {hedge_strike}")
        print(f"❌{config['KEY']} | No hedge options found for strike {hedge_strike}")
        return None, None, None, None

    # 3. Expiry Logic (Kept your original logic)
    df_filtered['expiry'] = pd.to_datetime(df_filtered['expiry'])
    today = pd.Timestamp.today().normalize()
    if config['EXPIRY'] == "LAST":
        month_ref = today if today.day <= 15 else (today + pd.DateOffset(months=1)).replace(day=1)
        next_month = month_ref.replace(day=28) + timedelta(days=4)
        last_day = next_month - timedelta(days=next_month.day)
        target_expiry = last_day - timedelta(days=(last_day.weekday() - 1) % 7)
    else:
        target_expiry = (today + timedelta(days=(1 - today.weekday() + 7) % 7)) + timedelta(days=days)

    week_start = target_expiry - timedelta(days=target_expiry.weekday())
    week_end = week_start + timedelta(days=6)
    
    target_options = df_filtered[
        (df_filtered['expiry'] >= week_start) & (df_filtered['expiry'] <= week_end)
    ].sort_values('expiry')

    if target_options.empty:
        logging.error(f"❌{config['KEY']} | No hedge options found for strike {hedge_strike}")
        print(f"❌{config['KEY']} | No hedge options found for strike {hedge_strike}")
        return None, None, None, None

    opt = target_options.iloc[0]
    opt_symbol = opt['tradingsymbol']
    expiry = opt['expiry'].strftime('%Y-%m-%d')

    # 4. FETCH PRICE & PERFORM COMPARISON
    # Using the retry helper you already have
    hedge_ltp = get_quotes_with_retry(opt_symbol, user)
    
    if hedge_ltp is None:
        print(f"❌{config['KEY']} | Failed to fetch LTP for hedge {opt_symbol}")
        logging.error(f"❌{config['KEY']} | Failed to fetch LTP for hedge {opt_symbol}")
        return None, None, None, None

    # THE CORE FIX: Reject if hedge is more expensive than the main trade
    if hedge_ltp >= main_ltp:
        print(f"❌{config['KEY']} | Hedge Option {opt_symbol} hedge ltp ({hedge_ltp}) >= Main ltp ({main_ltp}). Strategy Inverted. Aborting.")
        logging.error(f"❌{config['KEY']} | Hedge Option {opt_symbol} hedge ltp ({hedge_ltp}) >= Main ltp ({main_ltp}). Strategy Inverted. Aborting.")
        return None, None, None, None

    print(f"✅{config['KEY']} | Hedge found: {opt_symbol} | LTP: {hedge_ltp}")
    logging.info(f"✅{config['KEY']} | Hedge found: {opt_symbol} | LTP: {hedge_ltp}")
    return opt_symbol, hedge_strike, expiry, hedge_ltp


def save_open_position(trade, config, tradeGenie_id):
    """
    Saves the trade to the SQLite 'open_trades' table.
    Converts all Timestamp objects to strings to match the TEXT schema.
    """
    try:
        logging.info(f"{config['KEY']} | Saving open position: {trade['OptionSymbol']} in {config['INTERVAL']} interval")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # SQL query matching your schema columns
        sql = """
            INSERT INTO open_trades (
                signal, spot_entry, option_symbol, strike, expiry, 
                option_sell_price, entry_time, qty, interval, real_trade, 
                entry_reason, expiry_type, strategy, key, user_id, 
                hedge_option_symbol, hedge_strike, hedge_option_buy_price, 
                hedge_qty, hedge_entry_time, trade_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # --- CONVERSION LOGIC ---
        # Wrapping Timestamp fields in str() fixes the 'Timestamp not supported' error.
        # Ensure qty and strike are cast to int to match the INTEGER columns.
        params = (
            str(trade.get("Signal", "BUY")),           # TEXT
            float(trade.get("SpotEntry", 0.0)),        # REAL
            str(trade.get("OptionSymbol")),            # TEXT
            int(trade.get("Strike", 0)),               # INTEGER
            str(trade.get("Expiry")),                  # TEXT (Converted from Timestamp)
            float(trade.get("OptionSellPrice", 0.0)),  # REAL
            str(trade.get("EntryTime")),               # TEXT (Converted from Timestamp)
            int(trade.get("qty", 0)),                  # INTEGER
            str(trade.get("interval", config.get('INTERVAL'))), # TEXT
            str(trade.get("real_trade", config.get('REAL_TRADE'))), # TEXT
            str(trade.get("EntryReason", "SIGNAL_GENERATED")), # TEXT
            str(trade.get("ExpiryType", config.get('EXPIRY'))), # TEXT
            str(trade.get("Strategy", config.get('STRATEGY'))), # TEXT
            str(trade.get("Key", "NA")),               # TEXT
            int(tradeGenie_id),                        # INTEGER
            str(trade.get("hedge_option_symbol", "NA")), # TEXT
            int(trade.get("hedge_strike", 0)),         # INTEGER
            float(trade.get("hedge_option_buy_price", 0.0)), # REAL
            int(trade.get("hedge_qty", 0)),            # INTEGER
            str(trade.get("hedge_entry_time", "")),    # TEXT (Converted from Timestamp)
            str(trade.get("trade_status", "OPEN"))     # TEXT
        )

        c.execute(sql, params)
        conn.commit()
        conn.close()
        
        logging.info(f"✅{config['KEY']} | Open position saved successfully: {trade['OptionSymbol']}")

    except Exception as e:
        print(f"❌{config['KEY']} | Error saving open position: {e}")
        logging.error(f"{config['KEY']} | Error saving open position for {trade.get('OptionSymbol')}: {e}")
        send_telegram_message_admin(f"❌{config['KEY']} | Error saving open position for {trade.get('OptionSymbol')}: {e}")

def delete_open_position(symbol, config, trade, tradeGenie_id):
    try:
        logging.info(f"{config['KEY']} | Deleting open position for {symbol} in {config['INTERVAL']} interval")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        sql = "DELETE FROM open_trades WHERE option_symbol = ? and interval = ? and expiry_type = ? and strategy = ? and key = ? and user_id = ?"
        params = (symbol, config['INTERVAL'], trade.get("ExpiryType",config['EXPIRY']), trade.get("Strategy",config['STRATEGY']), trade.get("Key","NA"), tradeGenie_id)
        # print("Executing SQL:", sql, "\nWith parameters:", params)
        c.execute(sql, params)
        conn.commit()
        conn.close()
        logging.info(f"✅{config['KEY']} |  Open position for {symbol} deleted successfully in {config['INTERVAL']} interval")
    except Exception as e:
        print(f"❌{config['KEY']} | Error deleting open position for {symbol}: {e}")
        logging.error(f"{config['KEY']} | Error deleting open position for {symbol}: {e}")
        send_telegram_message_admin(f"❌{config['KEY']} | Error deleting open position for {symbol}: {e}")

def load_open_position(config,key , user , tradeGenie_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    sql = """
        SELECT signal, spot_entry, option_symbol, strike, expiry, 
               option_sell_price, entry_time, qty, interval, real_trade, entry_reason, expiry_type, strategy, key, user_id, hedge_option_symbol, hedge_strike, hedge_option_buy_price, hedge_qty, hedge_entry_time
        FROM open_trades where interval = ? and expiry_type = ? and strategy = ? and key = ? and user_id = ?
        ORDER BY id DESC LIMIT 1
    """
    params = (config['INTERVAL'], config['EXPIRY'], config['STRATEGY'], key, tradeGenie_id)
    # print("Executing SQL:", sql, "\nWith parameters:", params)
    c.execute(sql, params)
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    position_data = {
        "Signal": row[0],
        "SpotEntry": row[1],
        "OptionSymbol": row[2],
        "Strike": row[3],
        "Expiry": row[4],
        "OptionSellPrice": row[5],
        "EntryTime": row[6],
        "qty": row[7],
        "Interval": row[8],
        "RealTrade": row[9],
        "EntryReason": row[10],
        "ExpiryType": row[11],
        "Strategy": row[12],
        "Key": row[13],
        "user_id": row[14],
        "hedge_option_symbol": row[15],
        "hedge_strike": row[16],
        "hedge_option_buy_price": row[17],
        "hedge_qty": row[18],
        "hedge_entry_time": row[19],
        
    }
    avg_price, broker_qty = get_avgprice_from_positions(position_data["OptionSymbol"], user)
    if config['HEDGE_TYPE'] != "NH":
        if position_data['RealTrade'] == "yes":
            hedge_avg_price, hedge_broker_qty = get_avgprice_from_positions(position_data["hedge_option_symbol"], user)
            print(f"hedge_broker_qty: {hedge_broker_qty} | DB qty: {position_data['hedge_qty']} for {position_data['hedge_option_symbol']}")    
            logging.info(f"{key}  | hedge_broker_qty: {hedge_broker_qty} | DB qty: {position_data['hedge_qty']} for {position_data['hedge_option_symbol']}")
            if hedge_broker_qty >= position_data["hedge_qty"] and position_data["RealTrade"] == "yes":
                print(f"✅ {key}  | Broker position matches for Hedge Position or exceeds DB qty: {hedge_broker_qty} for {position_data['hedge_option_symbol']}")
                logging.info(f"✅ {key}  | Broker position matches for Hedge Position or exceeds DB qty: {hedge_broker_qty} for {position_data['hedge_option_symbol']}")
            else:
                
                err_msg = f"❌ {key}  | Broker qty {hedge_broker_qty} for {position_data['hedge_option_symbol']} is less than DB qty {position_data['hedge_qty']} — treating as closed."
                logging.error(err_msg)
                send_telegram_message_admin(err_msg)
                send_telegram_message(err_msg, user['telegram_chat_id'], user['telegram_token'])
                update_trade_config_on_failure(config['KEY'], err_msg, user)
            
    if position_data['RealTrade'] == "yes":    
        print(f"broker_qty: {broker_qty} | DB qty: {position_data['qty']} for {position_data['OptionSymbol']}")
        logging.info(f"{key}  | broker_qty: {broker_qty} | DB qty: {position_data['qty']} for {position_data['OptionSymbol']}")
        if broker_qty >= position_data["qty"]:
            print(f"✅ {key}  | Broker position matches for Open Position or exceeds DB qty: {broker_qty} for {position_data['OptionSymbol']}")
            logging.info(f"✅ {key}  | Broker position matches for Open Position or exceeds DB qty: {broker_qty} for {position_data['OptionSymbol']}")
        else:
           
            err_msg = f"❌{key}  |  Broker qty {broker_qty} for {position_data['OptionSymbol']} is less than DB qty {position_data['qty']} — treating as closed."
            logging.error(err_msg)
            send_telegram_message_admin(err_msg)
            send_telegram_message(err_msg, user['telegram_chat_id'], user['telegram_token'])
            update_trade_config_on_failure(config['KEY'], err_msg, user)
        print(f"✅ {key} | Loaded open position from DB: {position_data}")
        logging.info(f"✅ {key} | Loaded open position from DB: {position_data}")
    return position_data

def update_trade_status(trade, config, tradeGenie_id, new_status):
    try:
        logging.info(f"{config['KEY']} | Updating trade status to '{new_status}' for {trade['OptionSymbol']} in {config['INTERVAL']} interval")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        sql = """
            UPDATE open_trades 
            SET trade_status = ?
            WHERE option_symbol = ? AND interval = ? AND expiry_type = ? AND strategy = ? AND key = ? AND user_id = ?
        """
        params = (
            new_status, trade["OptionSymbol"], config['INTERVAL'], trade.get("ExpiryType",config['EXPIRY']), trade.get("Strategy",config['STRATEGY']), trade.get("Key","NA"), tradeGenie_id
        )
        # print("Executing SQL:", sql, "\nWith parameters:", params)
        c.execute(sql, params)
        conn.commit()
        conn.close()
        logging.info(f"✅{config['KEY']} | Trade status updated to '{new_status}' for {trade['OptionSymbol']} in {config['INTERVAL']} interval")
    except Exception as e:
        print(f"❌{config['KEY']} | Error updating trade status for {trade['OptionSymbol']}: {e}")
        logging.error(f"{config['KEY']} | Error updating trade status for {trade['OptionSymbol']}: {e}")
        send_telegram_message_admin(f"❌{config['KEY']} | Error updating trade status for {trade['OptionSymbol']}: {e}")

def record_trade(trade, config, tradeGenie_id):
    """
    Records a completed trade into the 'completed_trades' table.
    Converts Timestamps to strings and ensures correct numeric types.
    """
    try:
        logging.info(f"✅{config['KEY']} | Recording completed trade: {trade.get('OptionSymbol')}")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        sql = """
            INSERT INTO completed_trades (
                signal, spot_entry, option_symbol, strike, expiry, 
                option_sell_price, entry_time, spot_exit, option_buy_price, 
                exit_time, pnl, qty, interval, real_trade, entry_reason, 
                exit_reason, expiry_type, strategy, key, user_id, 
                hedge_option_symbol, hedge_strike, hedge_option_buy_price, 
                hedge_qty, hedge_entry_time, hedge_exit_time, 
                hedge_option_sell_price, hedge_pnl, total_pnl
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # --- FIX: Convert Timestamps to Strings & Cast Numerics ---
        params = (
            str(trade.get("Signal", "BUY")),                 # TEXT
            float(trade.get("SpotEntry", 0.0)),              # REAL
            str(trade.get("OptionSymbol")),                  # TEXT
            int(trade.get("Strike", 0)),                     # INTEGER
            str(trade.get("Expiry")),                        # TEXT (Timestamp fix)
            float(trade.get("OptionSellPrice", 0.0)),        # REAL
            str(trade.get("EntryTime")),                     # TEXT (Timestamp fix)
            float(trade.get("SpotExit", 0.0)),               # REAL
            float(trade.get("OptionBuyPrice", 0.0)),         # REAL
            str(trade.get("ExitTime")),                      # TEXT (Timestamp fix)
            float(trade.get("PnL", 0.0)),                    # REAL
            int(trade.get("qty", 0)),                        # INTEGER
            str(trade.get("Interval", config['INTERVAL'])),  # TEXT
            str(trade.get("RealTrade", config['REAL_TRADE'])), # TEXT
            str(trade.get("EntryReason", "MANUAL_ENTRY")),   # TEXT
            str(trade.get("ExitReason", "MANUAL_EXIT")),     # TEXT
            str(trade.get("ExpiryType", config['EXPIRY'])),  # TEXT
            str(trade.get("Strategy", config['STRATEGY'])),  # TEXT
            str(trade.get("Key", "NA")),                     # TEXT
            int(tradeGenie_id),                              # INTEGER
            str(trade.get("hedge_option_symbol", "NA")),     # TEXT
            int(trade.get("hedge_strike", 0)),               # INTEGER
            float(trade.get("hedge_option_buy_price", 0.0)), # REAL
            int(trade.get("hedge_qty", 0)),                  # INTEGER
            str(trade.get("hedge_entry_time", "")),          # TEXT (Timestamp fix)
            str(trade.get("hedge_exit_time", "")),           # TEXT (Timestamp fix)
            float(trade.get("hedge_option_sell_price", 0.0)),# REAL
            float(trade.get("hedge_pnl", 0.0)),              # REAL
            float(trade.get("total_pnl", 0.0))               # REAL
        )

        c.execute(sql, params)
        conn.commit()
        conn.close()
        
        logging.info(f"📊{config['KEY']} |  Trade recorded in DB successfully for {trade.get('OptionSymbol')}")

    except Exception as e:
        print(f"❌{config['KEY']} | Error recording trade: {e}")
        logging.error(f"{config['KEY']} | Error recording completed trade: {e}")
        send_telegram_message_admin(f"❌{config['KEY']} | Error recording completed trade: {e}")



def get_next_expiry_optimal_option(signal, last_expiry, price, nearest_price, instruments_df, config, user):
    
    try:
        df = instruments_df.copy()
        base_strike = int(round(price / 100.0) * 100)
        opt_type = "PE" if signal == "BUY" else "CE"
        today = pd.Timestamp.today().normalize()
        last_expiry_date = pd.to_datetime(last_expiry)
        if signal == "BUY":
            strike = base_strike - 100
            strike_adjustment = -100
        else:
            strike = base_strike + 100
            strike_adjustment = 100
        best_option = None
        best_ltp_diff = float('inf')
        previous_strike = None
        previous_ltp = None
        previous_symbol = None
        while True:
            df_filtered = df[
                (df['name'] == OPTION_SYMBOL) &
                (df['segment'] == SEGMENT) &
                (df['strike'] == strike) &
                (df['tradingsymbol'].str.endswith(opt_type))
            ].copy()
            if df_filtered.empty:
                break
            df_filtered['expiry'] = pd.to_datetime(df_filtered['expiry'])
            df_next_expiry = df_filtered[df_filtered['expiry'] > last_expiry_date].copy()
            if df_next_expiry.empty:
                break
            df_next_expiry = df_next_expiry.sort_values('expiry')
            next_expiry = df_next_expiry.iloc[0]['expiry']
            if config['EXPIRY'] == "LAST":
                if today.day <= 15:
                    month_str = today.strftime('%b').upper()
                else:
                    next_month = (today + pd.DateOffset(months=1))
                    month_str = next_month.strftime('%b').upper()
                df_same_expiry = df_next_expiry[df_next_expiry['tradingsymbol'].str.contains(month_str)].copy()
                if df_same_expiry.empty:
                    break
            else:
                df_same_expiry = df_next_expiry[df_next_expiry['expiry'] == next_expiry].copy()
            if df_same_expiry.empty:
                break
            option = df_same_expiry.iloc[0]
            opt_symbol = option['tradingsymbol']
            ltp = get_quotes_with_retry(opt_symbol, user) or 0.0
            if ltp == 0.0:
                strike += strike_adjustment
                continue
            if ltp > nearest_price:
                previous_strike = strike
                previous_ltp = ltp
                previous_symbol = opt_symbol
                strike += strike_adjustment
                continue
            if previous_strike is not None and previous_ltp is not None:
                prev_diff = abs(previous_ltp - nearest_price)
                curr_diff = abs(ltp - nearest_price)
                if prev_diff <= curr_diff:
                    best_strike = previous_strike
                    best_ltp = previous_ltp
                    best_symbol = previous_symbol
                else:
                    best_strike = strike
                    best_ltp = ltp
                    best_symbol = opt_symbol
            else:
                best_strike = strike
                best_ltp = ltp
                best_symbol = opt_symbol
            best_expiry = next_expiry.strftime('%Y-%m-%d')
            print(f"✅{config['KEY']} | Found option: {best_symbol} | Strike: {best_strike} | Expiry: {best_expiry} | LTP: {best_ltp}")
            logging.info(f"✅{config['KEY']} | Found option: {best_symbol} | Strike: {best_strike} | Expiry: {best_expiry} | LTP: {best_ltp}")
            return best_symbol, best_strike, best_expiry, best_ltp
        print(f"❌ {config['KEY']} | No suitable option found for signal {signal} after {last_expiry}")
        logging.info(f"❌ {config['KEY']} | No suitable option found for signal {signal} after {last_expiry}")
        return None, None, None, None
    except Exception as e:
        print(f"❌ {config['KEY']} | Error in get_next_expiry_optimal_option: {e}")
        logging.error(f"❌ {config['KEY']} | Error in get_next_expiry_optimal_option: {e}")
        send_telegram_message_admin(f"❌ {config['KEY']} | Error in get_next_expiry_optimal_option: {e}")
        return None, None, None, None

def is_market_open():
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        return False
    return datetime.time(9, 15, 10) <= now.time() <= datetime.time(15, 30)

def will_market_open_within_minutes(minutes=60):
    now = datetime.datetime.now()
    if now.weekday() >= 5:
        days_until_monday = 7 - now.weekday()
        next_monday = now + datetime.timedelta(days=days_until_monday)
        market_open_time = next_monday.replace(hour=9, minute=15, second=0, microsecond=0)
    else:
        market_open_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
        if now.time() >= datetime.time(15, 30):
            market_open_time = market_open_time + datetime.timedelta(days=1)
            if market_open_time.weekday() >= 5:
                days_until_monday = 7 - market_open_time.weekday()
                market_open_time = market_open_time + datetime.timedelta(days=days_until_monday)
        elif now.time() < datetime.time(9, 15):
            pass
        else:
            return True
    time_diff = market_open_time - now
    minutes_until_open = time_diff.total_seconds() / 60
    return minutes_until_open <= minutes


def close_position_and_no_new_trade(trade, position, close, ts, config, user, key):
    from tradeJenie import execute_robust_exit
    """
    Unified Exit Function:
    - Uses execute_robust_exit to handle NH, SEMI, FULL, and Qty Changes.
    - Forces expiry_match="DIFF" for a total exit.
    - Updates DB and kills thread on any mismatch or partial fill.
    """
    print(f"📥 {user['user']} {SERVER} | {key} | Final Exit: Closing {trade['OptionSymbol']}")
    logging.info(f"📥 {user['user']} {SERVER} | {key} | Final Exit: Closing {trade['OptionSymbol']}")

    if config['HEDGE_TYPE'] != "NH":
        hedge_required = True
    else:
        hedge_required = False

    # --- ROBUST EXIT EXECUTION ---
    # This single call replaces both the 'if' and 'else' blocks in your original code.
    # We use 'DIFF' to ensure a complete termination of the strategy.
    exit_qty, avg_price, hedge_avg_price = execute_robust_exit(
        trade, 
        config, 
        user, 
        expiry_match="DIFF"
    )
    if hedge_required:
        logging.info(f"📤{key} | Exited position {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty} | {trade['hedge_option_symbol']} with Avg price: ₹{hedge_avg_price:.2f} | Qty: {exit_qty}")
    else:
        logging.info(f"📤{key} | Exited position {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty}")
    

    if not is_valid_trade_data(exit_qty, avg_price, hedge_avg_price, hedge_required):
        err_msg = f"⚠️ {key} | FAILED EXIT: Qty: ({exit_qty}) or Price: ({avg_price}) is 0 for {trade['OptionSymbol']}. DB NOT updated."
        logging.error(err_msg)
        send_telegram_message_admin(err_msg)
        update_trade_config_on_failure(config['KEY'], err_msg, user)
        return    

    # UPDATE DATA
    trade.update({
        "SpotExit": close,
        "OptionBuyPrice": avg_price,
        "ExitTime": ts,
        "PnL": trade["OptionSellPrice"] - avg_price,
        "qty": exit_qty,
        "ExitReason": "FORCE_CLOSE_NO_NEW_TRADE",
        "hedge_option_sell_price": hedge_avg_price,
        "hedge_exit_time": ts,
        "hedge_pnl": (hedge_avg_price - trade.get("hedge_option_buy_price", 0)) if hedge_avg_price > 0 else 0.0,
    })
    
    # Calculate Total PnL
    trade["total_pnl"] = trade["PnL"] + trade.get("hedge_pnl", 0)

    # RECORD & DELETE
    record_trade(trade, config, user['id'])
    delete_open_position(trade["OptionSymbol"], config, trade, user['id'])
    
    # DYNAMIC NOTIFICATION
    if hedge_avg_price > 0:
        msg = (f"📤 {user['user']} {SERVER} | {key} | Final Exit\n"
               f"{trade['OptionSymbol']} @ ₹{avg_price:.2f}\n"
               f"{trade['hedge_option_symbol']} @ ₹{hedge_avg_price:.2f}\n"
               f"Total Profit Per Qty: ₹{trade['total_pnl']:.2f}")
    else:
        msg = (f"📤 {user['user']} {SERVER} | {key} | Final Exit (NH)\n"
               f"{trade['OptionSymbol']} @ ₹{avg_price:.2f}\n"
               f"Total Profit Per Qty: ₹{trade['total_pnl']:.2f}")

    send_telegram_message(msg, user['telegram_chat_id'], user['telegram_token'])
    
    return {}, None

def who_tried(user):
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    profile = get_profile(user)
    if profile is None:
        print(f"❌{user['user']} Profile not found. Exiting.")
        logging.error(f"❌{user['user']}  Profile not found. Exiting.")
        send_telegram_message(f"❌{user['user']}  Profile not found. Exiting.",user['telegram_chat_id'], user['telegram_token'])
        return
    else:
        print(f"ℹ️ Profile: {profile} | Current Time: {current_time}")
        logging.info(f"{get_profile(user)} tried to execute program at | Current Time: {current_time}")
        send_telegram_message(f"ℹ️ {get_profile(user)} tried to execute program at | Current Time: {current_time}\n" ,user['telegram_chat_id'], user['telegram_token'])




def _parse_interval_to_minutes(interval_str: str) -> int:
    """
    Accepts common formats like: "1", "3", "5", "15", "30", "60",
    or "1minute","5min","15m","1h","60min", etc. Returns minutes as int.
    """
    s = str(interval_str).strip().lower()
    if s.endswith(("minute", "minutes")):
        s = s.split("minute")[0]
    elif s.endswith(("min", "m")):
        s = s[:-1]
    elif s.endswith(("hour", "hours", "h")):
        # e.g. "1h"
        num = int(''.join(ch for ch in s if ch.isdigit()))
        return num * 60
    # default: numeric minutes
    num = int(''.join(ch for ch in s if ch.isdigit()))
    return max(1, num)

def get_next_candle_time(interval_str: str, from_dt=None):
    """
    Given INTERVAL (e.g., "5", "5min", "15m", "1h"), return the datetime
    when the next candle should start (rounded up), using 9:15 as the reference start time.
    """
    # Align all intervals to start from 9:15 (first candle), e.g. 9:15, 9:30, 9:45, ...
    minutes = _parse_interval_to_minutes(interval_str)
    if from_dt is None:
        from_dt = datetime.datetime.now()
    base = from_dt.replace(hour=9, minute=15, second=5, microsecond=0)
    if from_dt < base:
        return base
    # Calculate minutes since 9:15
    delta = from_dt - base
    passed_blocks = int(delta.total_seconds() // 60 // minutes)
    next_candle = base + timedelta(minutes=(passed_blocks + 1) * minutes)
    next_candle += timedelta(seconds=5)
    # Don't go past 15:30
    market_end = from_dt.replace(hour=15, minute=30, second=0, microsecond=0)
    if next_candle > market_end:
        next_candle = market_end
    return next_candle

def get_next_candle_time_old(interval_str: str, from_dt=None):
    import math
    if from_dt is None:
        from_dt = datetime.datetime.now()
    minutes = _parse_interval_to_minutes(interval_str)
    # Round up to the next interval boundary
    total_minutes = from_dt.hour * 60 + from_dt.minute
    next_blocks = math.floor(total_minutes / minutes) + 1
    next_total_minutes = next_blocks * minutes
    next_hour = (next_total_minutes // 60) % 24
    next_minute = next_total_minutes % 60
    next_dt = from_dt.replace(hour=next_hour, minute=next_minute, second=0, microsecond=0)
    # If rounding produced a time in the past (possible at midnight boundary), add a day
    if next_dt <= from_dt:
        next_dt = next_dt + datetime.timedelta(minutes=minutes)
    return next_dt

def convertIntoHeikinashi(df):
    ha_df = df.copy()
    ha_close = (df['open'] + df['high'] + df['low'] + df['close']) / 4
    ha_open = [df['open'].iloc[0]]
    for i in range(1, len(df)):
        ha_open.append((ha_open[i-1] + ha_close.iloc[i-1]) / 2)
    ha_high = pd.DataFrame({'high': df['high'], 'ha_open': ha_open, 'ha_close': ha_close}).max(axis=1)
    ha_low = pd.DataFrame({'low': df['low'], 'ha_open': ha_open, 'ha_close': ha_close}).min(axis=1)
    ha_df['open'] = ha_open
    ha_df['close'] = ha_close
    ha_df['high'] = ha_high
    ha_df['low'] = ha_low
    return ha_df



def hd_strategy(df: pd.DataFrame, maLength: int = 50) -> pd.DataFrame:
    """
    Python version of HdStrategy1.2 from Pine Script.
    Input: DataFrame with ['date','open','high','low','close','volume']
    Output: DataFrame with ['trend','buySignal','sellSignal']
    """
    # print(df.tail(5))
    # === Moving Average ===
    df["sma"] = df["close"].rolling(maLength).mean()

    # === Condition ===
    prev_high = df["high"].shift(1)
    prev_low = df["low"].shift(1)

    df["condition"] = (prev_high > df["high"]) & (prev_low < df["low"])
    df["isUptrend"] = df["close"] > df["sma"]
    df["isDowntrend"] = df["close"] < df["sma"]

    # === Buy & Sell Levels (like Pine's var persistence with ffill) ===
    df["buyat"] = np.where(df["condition"], prev_high, np.nan)
    df["sellat"] = np.where(df["condition"], prev_low, np.nan)
    df["buyat"] = df["buyat"].ffill()
    df["sellat"] = df["sellat"].ffill()

    # === Raw signals (crossover / crossunder with persistence levels) ===
    df["raw_buy_signal"] = (df["close"] > df["buyat"]) & (df["close"].shift(1) <= df["buyat"].shift(1))
    df["raw_sell_signal"] = (df["close"] < df["sellat"]) & (df["close"].shift(1) >= df["sellat"].shift(1))

    # === Final signals with trend tracking ===
    buy_signals, sell_signals, trends = [], [], []
    currentTrend = 0  # 0 = neutral, 1 = long, -1 = short

    for buy, sell in zip(df["raw_buy_signal"], df["raw_sell_signal"]):
        if buy:
            buy_signals.append(True)
            sell_signals.append(False)
            currentTrend = 1
        elif sell:
            buy_signals.append(False)
            sell_signals.append(True)
            currentTrend = -1
        else:
            buy_signals.append(False)
            sell_signals.append(False)
        trends.append(currentTrend)

    df["buySignal"] = buy_signals
    df["sellSignal"] = sell_signals
    df["trend"] = trends

    # === Cleanup ===
    df.drop(columns=["condition","isUptrend","isDowntrend",
                     "raw_buy_signal","raw_sell_signal"], inplace=True)

    return df

import pandas as pd

def railway_track_strategy(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """
    Parallel EMA High/Low Strategy (converted from Pine Script)

    Args:
        df (pd.DataFrame): Must have columns ['open', 'high', 'low', 'close']
        period (int): EMA period (default=20)

    Returns:
        pd.DataFrame: Original df + ['emaHigh','emaLow','buySignal','sellSignal','trend']
    """
    # === EMA of High and Low ===
    df["emaHigh"] = df["high"].ewm(span=period, adjust=False).mean()
    df["emaLow"]  = df["low"].ewm(span=period, adjust=False).mean()

    # === Two consecutive closes above/below ===
    buyCondRaw  = (df["close"].shift(1) > df["emaHigh"].shift(1)) & (df["close"] > df["emaHigh"])
    sellCondRaw = (df["close"].shift(1) < df["emaLow"].shift(1))  & (df["close"] < df["emaLow"])

    # === Only trigger when condition is new (no duplicates) ===
    # df["buySignal"]  = buyCondRaw & (~buyCondRaw.shift(1).fillna(False))
    # df["sellSignal"] = sellCondRaw & (~sellCondRaw.shift(1).fillna(False))

    df["buySignal"]  = buyCondRaw & (~buyCondRaw.shift(1, fill_value=False))
    df["sellSignal"] = sellCondRaw & (~sellCondRaw.shift(1, fill_value=False))

    # === Trend column (1 = long, -1 = short, 0 = neutral) ===
    trends = []
    currentTrend = 0
    for buy, sell in zip(df["buySignal"], df["sellSignal"]):
        if buy:
            currentTrend = 1
        elif sell:
            currentTrend = -1
        trends.append(currentTrend)

    df["trend"] = trends

    return df


import requests, datetime

def is_today_holiday():
    """
    Check if today is a holiday using NSE India holiday API.
    Returns True if today is a holiday, False otherwise.
    """
    url = "https://www.nseindia.com/api/holiday-master?type=trading"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    data = res.json()

    today = datetime.date.today().strftime("%d-%b-%Y")
    holidays = [h["tradingDate"] for h in data["CM"]]

    print("Today:", today)
    print("Is holiday?", today in holidays)
    return today in holidays

def get_monthly_strategy_total_pnl(user,config, month=None, year=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        if month is None or year is None:
            now = datetime.datetime.now()
            month = now.month
            year = now.year
        sql = """
            SELECT SUM(total_pnl*qty) FROM completed_trades
            WHERE key = ? AND user_id = ? AND strftime('%m', exit_time) = ? AND strftime('%Y', exit_time) = ?
        """
        params = (config['KEY'], user['id'], f"{month:02d}", str(year))
        c.execute(sql, params)
        result = c.fetchone()
        conn.close()
        total_pnl = result[0] if result[0] is not None else 0.0
        print(f"✅ Total PnL for {config['KEY']} in {month}/{year}: {total_pnl}")
        logging.info(f"✅ Total PnL for {config['KEY']} in {month}/{year}: {total_pnl}")
        return total_pnl
    except Exception as e:
        print(f"❌{user['user']} {SERVER} | {config['KEY']} |  Error calculating monthly PnL: {e}")
        logging.error(f"❌{user['user']} {SERVER} | {config['KEY']} |  Error calculating monthly PnL: {e}")
        return 0.0

def check_monthly_stoploss_hit(user,config):
    if config['ACTIVATE_MONTHLY_SL'] == 1 and config['MONTHLY_STOPLOSS'] != None:
        total_pnl = get_monthly_strategy_total_pnl(user, config)
        if total_pnl <= -abs(config['MONTHLY_STOPLOSS']):
            print(f"🚫 {config['KEY']} | {user['user']}  |  MONTHLY_STOPLOSS limit reached ({total_pnl} <= -{config['MONTHLY_STOPLOSS']}). No new trades allowed. Skipping till next month.")
            return True
        else:
            print(f"✅ {config['KEY']} | {user['user']}  | MONTHLY_STOPLOSS limit not reached ({total_pnl} > -{config['MONTHLY_STOPLOSS']}). Trades allowed.")
            return False
    else:
        print(f"ℹ️ {config['KEY']} | {user['user']}  |  MONTHLY_STOPLOSS not activated.")
        return False
    
def check_trade_stoploss_hit(user, trade, config):
    print(f"ℹ️ Checking TRADE_STOPLOSS for {config['KEY']} interval on trade {trade['OptionSymbol']}")
    current_ltp = get_quotes_with_retry(trade["OptionSymbol"] ,user)
    entry_ltp = trade["OptionSellPrice"]
    total_pnl = None
    if config['HEDGE_TYPE'] != "NH":
        logging.info(f"{config['KEY']} | Calculating total PnL including hedge for trade {trade['OptionSymbol']} and hedge {trade['hedge_option_symbol']}")
        hedge_current_ltp = get_quotes_with_retry(trade["hedge_option_symbol"] ,user)
        hedge_entry_ltp = trade["hedge_option_buy_price"]
        logging.info(f"{config['KEY']} | Trade {trade['OptionSymbol']} | Entry LTP: {entry_ltp}, Current LTP: {current_ltp}")
        logging.info(f"{config['KEY']} | Hedge {trade['hedge_option_symbol']} | Entry LTP: {hedge_entry_ltp}, Current LTP: {hedge_current_ltp}")
        if hedge_current_ltp is not None and hedge_entry_ltp is not None and current_ltp is not None and entry_ltp is not None:
            total_pnl = (entry_ltp - current_ltp) + (hedge_current_ltp - hedge_entry_ltp)   
    else:
        logging.info(f"{config['KEY']} | Calculating total PnL for trade {trade['OptionSymbol']} without hedge")
        logging.info(f"{config['KEY']} | Trade {trade['OptionSymbol']} | Entry LTP: {entry_ltp}, Current LTP: {current_ltp}")
        if current_ltp is not None and entry_ltp is not None:
            total_pnl = (entry_ltp - current_ltp)
            
    if total_pnl is None:
        return False
    total_pnl = total_pnl * trade.get("qty", config['QTY'])
    logging.info(f"{config['KEY']} | Total PnL for trade {trade['OptionSymbol']}: {total_pnl}")
    if config['ACTIVATE_SL_PER_TRADE'] and config['STOPLOSS_PER_TRADE'] != None:
        if total_pnl <= -abs(config['STOPLOSS_PER_TRADE']):
            print(f"🚫 {config['KEY']} | TRADE_STOPLOSS limit reached for {trade['OptionSymbol']} ({total_pnl} <= -{config['STOPLOSS_PER_TRADE']}). Closing position.")
            return True
        else:
            print(f"✅ {config['KEY']} | TRADE_STOPLOSS limit not reached for {trade['OptionSymbol']} ({total_pnl} > -{config['STOPLOSS_PER_TRADE']}).")
            return False
    else:
        print(f"ℹ️ {config['KEY']} | TRADE_STOPLOSS not set.")
        return False

def check_login_success(user,password):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT * FROM user_dtls WHERE user = ? AND kite_password = ?", (user, password))
        result = c.fetchone()
        conn.close()
        return result[0] is not None, result if result is not None else None
    except Exception as e:
        print(f"❌{user} Error checking login: {e}")
        logging.error(f"❌{user} | Error checking login: {e}")
        return False, None
    

def update_trade_config_on_failure(config_key, kill_reason, user):
    """
    Updates trade_config table to block the thread and logs the error.
    Used right before sys.exit().
    """
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # Update the specific strategy row
        c.execute("""
            UPDATE trade_config 
            SET THREAD_STATUS = 'BLOCKED', 
                LAST_ERROR_REASON = ?, 
                ERROR_TIMESTAMP = ?,
                LST_UPDT_DT = ?
            WHERE KEY = ?
        """, (kill_reason, now, now, config_key))
        
        conn.commit()
        conn.close()
        
        # Send the final Telegram alert
        err_msg = (f"☢️ THREAD KILLED | {user['user']}\n"
                   f"Strategy: {config_key}\n"
                   f"Reason: {kill_reason}\n"
                   f"Timestamp: {now}\n"
                   f"Action: Manual Intervention Required.")
        
        send_telegram_message_admin(err_msg)
        logging.critical(f"{user['user']} | Database updated: {config_key} is now BLOCKED. Reason: {kill_reason}")
        
    except Exception as e:
        logging.error(f"{user['user']} | {config_key} | Failed to update trade_config on failure: {e}")

def is_valid_trade_data(qty, avg_price, hedge_price=0, hedge_required=False):
    """Returns True only if critical trade values are non-zero."""
    if qty <= 0 or avg_price <= 0:
        return False
    if hedge_required and hedge_price <= 0:
        return False
    return True


def validate_trade_prices(main_symbol, hedge_symbol, config, user):
    """
    Checks:
    1. Hedge Price < Main Price.
    2. Main Price vs NEAREST_LTP: 10pt Warning / 25pt Hard Abort.
    """
    main_ltp = get_quotes_with_retry(main_symbol, user) or 0
    hedge_ltp = get_quotes_with_retry(hedge_symbol, user) or 0
    target_ltp = float(config.get('NEAREST_LTP', 0))
    
    price_diff = abs(main_ltp - target_ltp)

    # RULE 1: Strategy Check
    if hedge_ltp >= main_ltp:
        logging.error(f"❌{config['KEY']} |  REJECTED: Hedge ({hedge_ltp}) >= Main ({main_ltp}). Invalid Credit.")
        return False

    # RULE 2: Hard Abort (25 Points)
    if price_diff > 25.0:
        logging.critical(f"☢️{config['KEY']} | ABORT: Main {main_ltp} is {price_diff}pts from Target {target_ltp}.")
        return False

    # RULE 3: Soft Tolerance (10 Points)
    if price_diff > 10.0:
        logging.warning(f"⚠️{config['KEY']} | CAUTION: Main {main_ltp} moved {price_diff}pts from Target.")
    
    logging.info(f"✅ {config['KEY']} | Price Validated: Main {main_ltp} (Diff: {round(price_diff, 2)})")
    return True

def get_clean_trade(trade):
    clean_trade = {}
    for key, value in trade.items():
        # This part checks: "Is this a date/time object?"
        if hasattr(value, 'strftime'): 
            # If yes, turn it into a string like '2026-03-17 11:21:47'
            clean_trade[key] = value.strftime('%Y-%m-%d %H:%M:%S')
        else:
            # If no, just keep it as it is (Number or Text)
            clean_trade[key] = value
    return clean_trade
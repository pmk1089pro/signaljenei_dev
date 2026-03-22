    # emalive.py

import sys
import time
import datetime
from datetime import timedelta
import pandas as pd
import sqlite3
import logging
from commonFunction import check_monthly_stoploss_hit, close_position_and_no_new_trade, convertIntoHeikinashi, delete_open_position, generate_god_signals, get_next_candle_time, get_optimal_option, get_robust_optimal_option, get_trade_configs, hd_strategy, init_db, is_market_open, load_open_position, railway_track_strategy, record_trade, save_open_position, update_trade_config_on_failure, validate_trade_prices, wait_until_next_candle, who_tried, will_market_open_within_minutes,get_hedge_option,get_lot_size,check_trade_stoploss_hit,get_keywise_trade_config,is_valid_trade_data,get_clean_trade
from config import  HEDGE_NEAREST_LTP, SYMBOL,SEGMENT, CANDLE_DAYS as DAYS, REQUIRED_CANDLES, LOG_FILE,INSTRUMENTS_FILE, OPTION_SYMBOL, SERVER, ROLLOVER_CALC
from kitefunction import get_entire_quote, get_historical_df, place_option_hybrid_order, get_token_for_symbol, get_quotes_with_retry, simulate_robust_limit_order
from telegrambot import send_telegram_signals_users,send_telegram_message_admin
import importlib
import threading
import pandas as pd
from requests.exceptions import ReadTimeout
from kiteconnect import exceptions
import random

# ====== Setup Logging ======
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

# ====== Main Live Trading Loconfig['REAL_TRADE']op ======
def live_trading(instruments_df, config, key, user):

    if config['REAL_TRADE'].lower() != "yes":
        print(f"🚫{key} | {user['user']} {SERVER}  | TRADE mode is OFF SIMULATED_ORDER will be tracked")
        logging.info(f"🚫 {key} | {user['user']} {SERVER}  | TRADE mode is OFF. Running in SIMULATION mode.")
    else:    
        print(f"🚀 {key} | {user['user']} {SERVER}  | TRADE mode is ON LIVE_ORDER will be placed")
        logging.info(f"🚀 {key} | {user['user']} {SERVER}  | TRADE mode is ON. Running in LIVE mode.")
    
    open_trade = load_open_position(config, key, user, user['id'])
    if open_trade:
            trade = open_trade
            position = open_trade["Signal"]
            logging.info(f"📌 {key}  |   {user['user']} {SERVER}  | Resumed open position: {position} | {open_trade['OptionSymbol']} @ ₹{open_trade['OptionSellPrice']} | Qty: {open_trade['qty']} | Hedge Symbol: {open_trade['hedge_option_symbol']} @ ₹{open_trade['hedge_option_buy_price']} | Hedge Qty: {open_trade['hedge_qty']}")
            print(f"📌 {key}  |   {user['user']} {SERVER}  | Resumed open position: {position} | {open_trade['OptionSymbol']} @ ₹{open_trade['OptionSellPrice']} | Qty: {open_trade['qty']} | Hedge Symbol: {open_trade['hedge_option_symbol']} @ ₹{open_trade['hedge_option_buy_price']} | Hedge Qty: {open_trade['hedge_qty']}")

            market_vibe = "Trend Continuation | Monitoring Setup"

            friend_message = (
                f"📌 **ACTIVE SETUP MONITORED**\n\n"
                f"🔴 **SELL Position** {open_trade['OptionSymbol']} @ ₹{open_trade['OptionSellPrice']:.2f}\n"
                f"🟢 **BUY Position** (Fence) {open_trade['hedge_option_symbol']} @ ₹{open_trade['hedge_option_buy_price']:.2f}\n\n"
                f"📊 *Market Study | Nifty Update*\n"
                f"📍 *Nifty Entry Spot:* {open_trade['SpotEntry']}\n"
                f"🌟 *Market Mood:* {market_vibe}\n\n"
                f"The automated system has resumed tracking this active position for my personal journal.\n\n"
                f"⚠️ *Note: This is an automated log for educational study. I am NOT a SEBI-registered advisor. Not a trading recommendation.*"
            )    
            send_telegram_signals_users(friend_message,user['telegram_chat_id'], user['telegram_token'])
            send_telegram_message_admin(f"📌 {key} | {user['user']} {SERVER}  | Resumed open position: {position} | {open_trade['OptionSymbol']} @ ₹{open_trade['OptionSellPrice']} | Qty: {open_trade['qty']} | Hedge Symbol: {open_trade['hedge_option_symbol']} @ ₹{open_trade['hedge_option_buy_price']} | Hedge Qty: {open_trade['hedge_qty']}",user['telegram_chat_id'], user['telegram_token'])
    else:
        trade = {}
        position = None
        print(f"ℹ️ {key} | {user['user']} {SERVER}  |   No open position. Waiting for next signal...")
        logging.info(f"ℹ️ {key} | {user['user']} {SERVER}  |   No open position. Waiting for next signal...")
   
    

    while True:
        open_trade = load_open_position(config, key, user, user['id'])
        if open_trade:
            trade = open_trade
            position = open_trade["Signal"]
            logging.info(f"📌 {key}  | {user['user']} {SERVER}  | Resumed open position: {position} | {open_trade['OptionSymbol']} @ ₹{open_trade['OptionSellPrice']} | Qty: {open_trade['qty']} | Hedge Symbol: {open_trade['hedge_option_symbol']} @ ₹{open_trade['hedge_option_buy_price']} | Hedge Qty: {open_trade['hedge_qty']}")
            print(f"➡️ {key}  |  {user['user']} {SERVER} | Resumed open position: {position} | {open_trade['OptionSymbol']} @ ₹{open_trade['OptionSellPrice']} | Qty: {open_trade['qty']} | Hedge Symbol: {open_trade['hedge_option_symbol']} @ ₹{open_trade['hedge_option_buy_price']} | Hedge Qty: {open_trade['hedge_qty']}")
            # send_telegram_message(f"📌 {key}  | {user['user']} {SERVER}  |  {config['INTERVAL']} Resumed open position: {position} | {open_trade['OptionSymbol']} @ ₹{open_trade['OptionSellPrice']} | Qty: {open_trade['qty']} | Hedge Symbol: {open_trade['hedge_option_symbol']} @ ₹{open_trade['hedge_option_buy_price']} | Hedge Qty: {open_trade['hedge_qty']}",user['telegram_chat_id'], user['telegram_token'])
        else:
            trade = {}
            position = None
            print(f"ℹ️ {key} | {user['user']} {SERVER} No open position. Waiting for next signal...")
            logging.info(f"ℹ️ {key} | {user['user']} {SERVER} No open position. Waiting for next signal...")
   
        try:
            # configs = get_trade_configs(user['id'])
            config = get_keywise_trade_config(key)
            lot_size = get_lot_size(config, instruments_df)
            config['QTY'] = lot_size*int(config['LOT'])

            if config['NEW_TRADE'].lower() == "no" and trade == {}:   
                print(f"🚫 {key}  | {user['user']} {SERVER}, There is no live trade present, No new trades allowed. So Closing the program")
                logging.info(f"🚫 {key}  |{user['user']} {SERVER}, There is no live trade present, No new trades allowed. So Closing the program")
                #send_telegram_message(f"🕒 {key}  | {user['user']} {SERVER}, There is no live trade present, No new trades allowed. So Closing the program",user['telegram_chat_id'], user['telegram_token'])
                break    
            
            

            if not is_market_open():
                print(f" {key}  | {user['user']} {SERVER} Market is closed. Checking if market will open within 60 minutes...")
                if will_market_open_within_minutes(60):
                    print(f" {key} | {user['user']} {SERVER}Market will open within 60 minutes. Continuing to wait...")
                    time.sleep(60)
                    continue
                else:
                    print(f"{key}  | {user['user']} {SERVER}, Market will not open within 60 minutes. Stopping program.")
                    #send_telegram_message(f"🛑 {key}  | {user['user']} {SERVER}, Market will not open within 60 minutes. Stopping program.",user['telegram_chat_id'], user['telegram_token'])
                    return

            if config['INTRADAY'].lower() == "yes" and trade == {} and datetime.datetime.now().time() >= datetime.time(15, 15):
                print(f"🚫 {key}  | {user['user']} {SERVER} | There is no live trade present, No new trades allowed. So Closing the program")
                logging.info(f"🚫{key}  |{user['user']} {SERVER} | There is no live trade present, No new trades allowed. So Closing the program")
                #send_telegram_message(f"🕒 {key}  | {user['user']} {SERVER} | There is no live trade present, No new trades allowed. So Closing the program",user['telegram_chat_id'], user['telegram_token'])
                break     

            df = get_historical_df(instrument_token, config['INTERVAL'], DAYS, user)
            print(f"🕵️‍♀️{key} | {user['user']} {SERVER} Candles available: {len(df)} / Required: {REQUIRED_CANDLES}")

            if len(df) < REQUIRED_CANDLES:
                print(f"⚠️ {key}  | {user['user']} {SERVER} Not enough candles. Waiting...")
                logging.warning(f"⚠️ {key}  | {user['user']} {SERVER} Not enough candles. Waiting...")
                time.sleep(60)
                continue
            
            if config['STRATEGY'] == "GOD":
                df = generate_god_signals(df)
            elif config['STRATEGY'] == "HDSTRATEGY":
                df = convertIntoHeikinashi(df)
                df = hd_strategy(df)
            elif config['STRATEGY'] == "RAILWAY_TRACK":
                df = railway_track_strategy(df)
            
            latest = df.iloc[-1]
            latest_time = pd.to_datetime(latest['date'])
            # now = datetime.now()

            # ✅ Decide which row to use for signals
            if df.iloc[-1]['buySignal'] or df.iloc[-1]['sellSignal']:
                latest = df.iloc[-1]
            elif df.iloc[-2]['buySignal'] or df.iloc[-2]['sellSignal']:
                latest = df.iloc[-2]
            else:
                latest = df.iloc[-1]  # No signal in last 2 candles

            ts = latest['date'].strftime('%Y-%m-%d %H:%M')
            close = latest['close']
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logging.info(f"🕒{key} | Signal Received at Current Time: {current_time}\n{df.tail(5)}")            
            logging.info(f"{key} | {config['STRATEGY']} | Candle time {ts} | Close: {close} | Buy: {latest['buySignal']} | Sell: {latest['sellSignal']} | Trend: {latest['trend']} | Current Time: {current_time}")
            print(f"{key} | {config['STRATEGY']} | Candle time {ts} | Close: {close} | Buy: {latest['buySignal']} | Sell: {latest['sellSignal']} | Trend: {latest['trend']} | Current Time: {current_time}")
            
            
            if config['HEDGE_TYPE'] != "NH":
                # ✅ BUY SIGNAL
                if latest['buySignal'] and position != "BUY":
                    if position == "SELL":
                        # EXIT CODE EXECUTION :: START
                        # 1. PRE-EXIT PREPARATION
                        # Extract existing quantities and settings
                        existing_qty = int(trade.get("qty", config['QTY']))
                        target_qty_new = int(config.get('QTY', existing_qty))
                        hr_type = str(config.get('HEDGE_ROLLOVER_TYPE', 'FULL')).upper()
                        

                        print(f"📥 {key} |  {user['user']} {SERVER} | Exiting  {trade['OptionSymbol']} | {trade['hedge_option_symbol']} | Qty: {existing_qty}" )
                        logging.info(f"📥 {key} |  {user['user']} {SERVER} | Exiting  {trade['OptionSymbol']} | {trade['hedge_option_symbol']} | Qty: {existing_qty}" )

                        # 2. EXECUTE ROBUST EXIT (Replaces manual hybrid orders)
                        # This function handles NH/SEMI/FULL and Qty Changes internally.
                        # It will KILL the thread if a mismatch or partial fill occurs.
                        exit_qty, avg_price, hedge_avg_price = execute_robust_exit( trade, config, user)
                        
                        logging.info(f"📤{key} | Exited from {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty} And {trade['hedge_option_symbol']} with Avg price: ₹{hedge_avg_price:.2f} | Qty: {exit_qty}" )

                        if not is_valid_trade_data(exit_qty, avg_price, hedge_avg_price, hedge_required=True):
                            err_msg = f"⚠️ {key} | FAILED EXIT: {trade['OptionSymbol']} or {trade['hedge_option_symbol']} of Qty ({exit_qty}) or Price ({avg_price}) or ({hedge_avg_price}) is 0 for {trade['OptionSymbol']} or {trade['hedge_option_symbol']}. DB NOT updated."
                            logging.error(err_msg)
                            send_telegram_message_admin(err_msg)
                            update_trade_config_on_failure(config['KEY'], err_msg, user)
                            return 

                        # 3. UPDATE DATA & RECORD
                        trade.update({
                            "OptionBuyPrice": avg_price,
                            "SpotExit": close,
                            "ExitTime": current_time,
                            "PnL": trade["OptionSellPrice"] - avg_price,
                            "qty": exit_qty,
                            "ExitReason": "SIGNAL_GENERATED",
                            "hedge_option_sell_price": hedge_avg_price,
                            "hedge_exit_time": current_time,
                            "hedge_pnl": (hedge_avg_price - trade["hedge_option_buy_price"]) if hedge_avg_price > 0 else 0,
                        })
                        
                        # Calculate Total PnL (Main + Hedge)
                        trade["total_pnl"] = trade["PnL"] + trade.get("hedge_pnl", 0)

                        logging.info(f"📥 {key} | SELL Signal Generated | Exit Successful | Main Avg: {avg_price} | Hedge Avg: {hedge_avg_price} | Qty: {exit_qty}")
                        
                        trade = get_clean_trade(trade)
                        record_trade(trade, config, user['id'])
                        delete_open_position(trade["OptionSymbol"], config, trade, user['id'])
                        
                        # 4. NOTIFY
                        # msg = (f"📤{key} | {user['user']} {SERVER} | Exit SELL Signal Generated.\n"
                        #     f"{trade['OptionSymbol']} @ ₹{avg_price:.2f}\n"
                        #     f"Hedge: {trade['hedge_option_symbol']} @ ₹{hedge_avg_price:.2f}\n"
                        #     f"Profit/Qty: ₹{trade['total_pnl']:.2f}")
                        
                        market_vibe = "Trend Reversal"
                        exit_message = (
                            f"🏁 *EXIT SIGNAL LOGGED*\n\n"
                            f"🟢 *BUY (Back)* {trade['OptionSymbol']} @ ₹{exit_price:.2f}\n"
                            f"🔴 *SELL (Fence)* {hedge_opt_symbol} @ ₹{hedge_exit_price:.2f}\n\n"
                            f"💰 *Performance:* +₹{trade['total_pnl']:.2f} Per Qty\n"
                            f"📊 Nifty Exit Spot: {trade['SpotExit']}\n"
                            f"🌟 Market Mood: {market_vibe}\n\n"
                            f"The system identified a shift in trend and closed the setup in my personal log.\n\n"
                            f"⚠️ Note: Educational log only. I am NOT SEBI-registered. Past performance does not guarantee future results."
                        )
                        send_telegram_signals_users(exit_message, user['telegram_chat_id'], user['telegram_token'])
                    # EXIT CODE EXECUTION :: END
                    if config['NEW_TRADE'].lower() == "no":
                        print(f"🚫{key} | {user['user']} | {SERVER} | No new trades allowed. Skipping BUY signal.")
                        logging.info(f"{key} | {user['user']} | {SERVER} | No new trades allowed. Skipping BUY signal.")
                        break

                    
                    if check_monthly_stoploss_hit(user, config):
                        break

                    # --- BUY ENTRY CODE EXECUTION :: START ---
                    try:
                        hedge_required = config['HEDGE_TYPE'] != "NH"
                        # Set the offset based on config
                        h_offset = 200 if config['HEDGE_TYPE'] == "H-M200" else 100
                        
                        result = (None, None, None, None, None)
                        
                        # 1. UNIFIED SEARCH
                        for attempt in range(3):
                            if config['HEDGE_TYPE'] == "H-P10":
                                # For P10, find Main first (Hedge Required=False for this call)
                                result = get_robust_optimal_option(signal="BUY", spot=close, nearest_price=config['NEAREST_LTP'], 
                                                                instruments_df=instruments_df, config=config, user=user, hedge_required=False)
                                
                                # Then find P10 Hedge separately
                                m_sym, m_strike, m_exp, m_ltp, _ = result
                                if m_sym:
                                    h_res = get_robust_optimal_option(signal="BUY", spot=close, nearest_price=HEDGE_NEAREST_LTP, 
                                                                    instruments_df=instruments_df, config=config, user=user, hedge_required=False)
                                    if h_res[0]:
                                        # Combine Main from first call and Hedge from second call
                                        result = (m_sym, m_strike, m_exp, m_ltp, h_res[0])
                                    else: result = (None,) * 5
                            else:
                                # For M100/M200 or NH, use the single robust call (It handles the offset internally)
                                result = get_robust_optimal_option(signal="BUY", spot=close, nearest_price=config['NEAREST_LTP'], 
                                                                instruments_df=instruments_df, config=config, user=user, 
                                                                hedge_offset=h_offset, hedge_required=hedge_required)
                            
                            if result[0] is not None: break
                            time.sleep(2)

                        # 2. VALIDATION & EXECUTION
                        opt_symbol, strike, expiry, ltp, hedge_opt_symbol = result

                        if opt_symbol is None or (hedge_required and hedge_opt_symbol is None):
                            print(f"❌ {key} | {user['user']} {SERVER} | Optimal option not found. Skipping this signal.")
                            logging.error(f"❌{key} | No Pair Found.")
                            continue 
                        
                        print(f"📤 {key} | {user['user']} {SERVER} | Signal Generated for Entry : Optimal option {opt_symbol} at LTP {ltp} with Hedge {hedge_opt_symbol}")
                        logging.info(f"📤 {key} | {user['user']} {SERVER} | Signal Generated for Entry : Optimal option {opt_symbol} at LTP {ltp} with Hedge {hedge_opt_symbol}")

                        # 3. EXECUTE ORDERS
                        temp_trade_symbols = {"OptionSymbol": opt_symbol, "hedge_option_symbol": hedge_opt_symbol}
                        qty, avg_price, hedge_avg_price = execute_robust_entry(temp_trade_symbols, config, user)

                        if is_valid_trade_data(qty, avg_price, hedge_avg_price, hedge_required):
                            trade = {
                                "Signal": "BUY", "SpotEntry": close, "OptionSymbol": opt_symbol, "Strike": strike, "Expiry": expiry,
                                "OptionSellPrice": avg_price, "EntryTime": current_time, "qty": qty, "Key": key, 
                                "hedge_option_symbol": hedge_opt_symbol, "hedge_strike":hedge_strike,"hedge_option_buy_price": hedge_avg_price, 
                                "hedge_qty": qty if hedge_avg_price > 0 else "-","hedge_entry_time": current_time if hedge_avg_price > 0 else "-"
                            }
                            save_open_position(get_clean_trade(trade), config, user['id'])

                            print(f"✅ {key} | {user['user']} {SERVER} | BUY Entry Executed: {opt_symbol} @ ₹{avg_price:.2f} | Hedge: {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f} | Qty: {qty}")
                            logging.info(f"✅ {key} | {user['user']} {SERVER} | BUY Entry Executed: {opt_symbol} @ ₹{avg_price:.2f} | Hedge: {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f} | Qty: {qty}")
                            # send_telegram_message(f"🟢{key} | {user['user']} {SERVER} | BUY Entry Executed: {opt_symbol} @ ₹{avg_price:.2f} | Hedge: {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f} | Qty: {qty}", user['telegram_chat_id'], user['telegram_token'])
                            market_vibe = "Bullish Momentum Detected"
                            entry_message = (
                                f"🚀 *ENTRY SIGNAL LOGGED*\n\n"
                                f"🔴 *SELL* {opt_symbol} @ ₹{avg_price:.2f}\n"
                                f"🟢 *BUY* (Fence) {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f}\n\n"
                                f"📊 Market Study | Nifty Update\n"
                                f"📍 Nifty Spot: {close}\n"
                                f"🌟 Market Mood: {market_vibe}\n\n"
                                f"My automated system shows current levels are favorable for a trend. I'm tracking this setup for my own study.\n\n"
                                f"⚠️ Note: This is an automated log for educational study. I am NOT a SEBI-registered advisor. Not a trading recommendation."
                            )
                            send_telegram_signals_users(entry_message, user['telegram_chat_id'], user['telegram_token'])
                    except Exception as e:
                        print(f"❌ {key} | {user['user']} {SERVER} | Error during BUY entry execution: {e}")
                        logging.error(f"❌{key} | {user['user']} {SERVER} | BUY Entry Error: {e}")
                        send_telegram_message_admin(f"❌ BUY Entry Error for {key} | {user['user']} | {SERVER}: {e}")

                    #BUY ENTRY CODE EXECUTION :: END
                    
                # ✅ SELL SIGNAL
                elif latest['sellSignal'] and position != "SELL":
                    
                    if position == "BUY":
                        # EXIT CODE EXECUTION :: START
                        existing_qty = int(trade.get("qty", config['QTY']))
                        
                        print(f"📥 {key} |  {user['user']} {SERVER} | Signal Exit: Buying back {trade['OptionSymbol']} | Qty: {existing_qty} | Hedge: {trade['hedge_option_symbol']}")
                        logging.info(f"📥  {key} |  {user['user']} {SERVER} | Signal Exit: Buying back {trade['OptionSymbol']} | Qty: {existing_qty} | Hedge: {trade['hedge_option_symbol']}")
    
                        # 2. ROBUST EXIT EXECUTION
                        # Handles SEMI/FULL/NH and Qty Changes. Kills thread if mismatch occurs.
                        exit_qty, avg_price, hedge_avg_price = execute_robust_exit(
                            trade, 
                            config, 
                            user
                        )
                        print(f"📤{key} | Exited from {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty} And {trade['hedge_option_symbol']} with Avg price: ₹{hedge_avg_price:.2f} | Qty: {exit_qty}" )
                        logging.info(f"📤{key} | Exited from {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty} And {trade['hedge_option_symbol']} with Avg price: ₹{hedge_avg_price:.2f} | Qty: {exit_qty}" )

                        if not is_valid_trade_data(exit_qty, avg_price, hedge_avg_price, hedge_required=True):
                            err_msg = f"⚠️ {key} | FAILED EXIT:{trade['OptionSymbol']} or {trade['hedge_option_symbol']} of Qty ({exit_qty}) or Price ({avg_price}) or ({hedge_avg_price}) is 0 for {trade['OptionSymbol']} or {trade['hedge_option_symbol']}. DB NOT updated."
                            logging.error(err_msg)
                            send_telegram_message_admin(err_msg)
                            update_trade_config_on_failure(config['KEY'], err_msg, user)
                            return 
                        
                        # 3. UPDATE DATA & CALCULATE PNL
                        trade.update({
                            "OptionBuyPrice": avg_price,
                            "SpotExit": close,
                            "ExitTime": current_time,
                            "PnL": trade["OptionSellPrice"] - avg_price,
                            "qty": exit_qty,
                            "ExitReason": "SIGNAL_GENERATED",
                            "hedge_option_sell_price": hedge_avg_price,
                            "hedge_exit_time": current_time,
                            "hedge_pnl": (hedge_avg_price - trade["hedge_option_buy_price"]) if hedge_avg_price > 0 else 0,
                        })
                        
                        # Calculate Total PnL (Main + Hedge)
                        trade["total_pnl"] = trade["PnL"] + trade.get("hedge_pnl", 0)

                        logging.info(f"📥 {key} |{user['user']} {SERVER} | Signal Exit Success | {trade['OptionSymbol']} of M_Avg: {avg_price} | {trade['hedge_option_symbol']} of H_Avg: {hedge_avg_price}")
                        
                        trade = get_clean_trade(trade)
                        record_trade(trade, config, user['id'])
                        delete_open_position(trade["OptionSymbol"], config, trade, user['id'])
                        
                        # 4. NOTIFY
                        # msg = (f"📤{key} | {user['user']} {SERVER} |  Exit Signal Generated\n"
                        #     f"{trade['OptionSymbol']} @ ₹{avg_price:.2f}\n"
                        #     f"{trade['hedge_option_symbol']} @ ₹{hedge_avg_price:.2f}\n"
                        #     f"Total PnL/Qty: ₹{trade['total_pnl']:.2f}")
                        
                        logging.info(msg)
                        market_vibe = "Trend Reversal"
                        exit_message = (
                            f"🏁 *EXIT SIGNAL LOGGED*\n\n"
                            f"🟢 *BUY (Back)* {trade['OptionSymbol']} @ ₹{avg_price:.2f}\n"
                            f"🔴 *SELL (Fence)* {trade['hedge_option_symbol']} @ ₹{hedge_avg_price:.2f}\n\n"
                            f"💰 *Performance:* +₹{trade['total_pnl']:.2f} Per Qty\n"
                            f"📊 Nifty Exit Spot: {close}\n"
                            f"🌟 Market Mood: {market_vibe}\n\n"
                            f"The system identified a shift in trend and closed the setup in my personal log.\n\n"
                            f"⚠️ Note: Educational log only. I am NOT SEBI-registered. Past performance does not guarantee future results."
                        )
                        send_telegram_signals_users(exit_message, user['telegram_chat_id'], user['telegram_token'])
                        # send_telegram_message(msg, user['telegram_chat_id'], user['telegram_token']) 
                    # EXIT CODE EXECUTION :: END                   
                    
                    if config['NEW_TRADE'].lower() == "no":
                        print(f"🚫  {key}  | {user['user']} {SERVER}  |  No new trades allowed. Skipping SELL signal.")
                        logging.info(f"🚫 {key} | {user['user']} {SERVER}  | No new trades allowed. Skipping SELL signal.")
                        break
                    
                    if check_monthly_stoploss_hit(user, config):
                        break
                    
                           
                    # --- ENTRY CODE EXECUTION (SELL) :: START ---
                    try:
                        h_type = config['HEDGE_TYPE']
                        h_required = h_type != "NH"
                        h_offset = 200 if h_type == "H-M200" else 100
                        
                        result = (None, None, None, None, None)
                        hedge_result = (None, None, None, None, None)

                        # 1. FIND MAIN OPTION (SELL)
                        for attempt in range(3):
                            # We use hedge_required=False to find the Main CE first
                            result = get_robust_optimal_option(
                                signal="SELL", 
                                spot=close, 
                                nearest_price=config['NEAREST_LTP'], 
                                instruments_df=instruments_df, 
                                config=config, 
                                user=user, 
                                hedge_required=False
                            )
                            
                            # Unpacks: (opt_symbol, strike, expiry, ltp, _)
                            if result[0] is not None:
                                break

                            print(f"⚠️ {key}  | {user['user']} {SERVER} | Search Attempt {attempt+1} failed to find an option within tolerance. Retrying in 2s...")    
                            logging.info(f"⚠️{key}  |  Search Attempt {attempt+1} failed to find an option within tolerance. Retrying in 2s...")
                            time.sleep(2)

                        
                        
                        opt_symbol, strike, expiry, ltp, _ = result
                        print(f"📤 {key}  | {user['user']} {SERVER} | Signal Generated for Entry : Optimal option {opt_symbol} at LTP {ltp}")
                        logging.info(f"📤 {key} | {user['user']} {SERVER} | Signal Generated for Entry : Optimal option {opt_symbol} at LTP {ltp}")
                        
                        # 2. FIND HEDGE OPTION (SELL)
                        if opt_symbol is not None and h_required:
                            # CASE A: Price-based Hedge (H-P10)
                            if h_type == "H-P10":
                                for attempt in range(3):
                                    hedge_result = get_robust_optimal_option(
                                        signal="SELL", 
                                        spot=close, 
                                        nearest_price=HEDGE_NEAREST_LTP, 
                                        instruments_df=instruments_df, 
                                        config=config, 
                                        user=user, 
                                        hedge_required=False
                                    )
                                    if hedge_result[0] is not None:
                                        break
                                    
                                    print(f"⚠️{key} |  Search Attempt {attempt+1} failed to find a Hedge option within tolerance. Retrying in 2s...")
                                    logging.info(f"⚠️{key} |  Search Attempt {attempt+1} failed to find an option within tolerance. Retrying in 2s...")
                                    time.sleep(2)
                                    
                            # CASE B: Offset-based Hedge (H-M100 / H-M200)
                            elif h_type in ["H-M100", "H-M200"]:
                                for attempt in range(3):
                                    # Search for the fixed offset CE Hedge strike (+ h_offset)
                                    h_search = get_robust_optimal_option(
                                        signal="SELL", 
                                        spot=close, 
                                        nearest_price=config['NEAREST_LTP'], # Fixed offset search
                                        instruments_df=instruments_df, 
                                        config=config, 
                                        user=user, 
                                        hedge_offset=h_offset, 
                                        hedge_required=True
                                    )
                                    
                                    # The 5th index of robust return is the calculated hedge symbol
                                    if h_search[4] is not None:
                                        h_sym = h_search[4]
                                        h_q = get_entire_quote(h_sym, user)
                                        hedge_result = (h_sym, strike + h_offset, expiry, h_q.get('last_price', 0),None)
                                        break
                                        
                                    print(f"⚠️{key} | {user['user']} Search Attempt {attempt+1} failed to find an Hedge option. Retrying in 2s...")
                                    logging.info(f"⚠️{key} | {user['user']} Search Attempt {attempt+1} failed to find an Hedge option. Retrying in 2s...")
                                    time.sleep(2)

                        # 3. VALIDATION & ERROR HANDLING
                        if result[0] is None or (h_required and (hedge_result is None or hedge_result[0] is None)):
                            print(f"❌{key} | {user['user']} {SERVER} | No suitable option found for SELL signal. Main: {result[0]} Hedge: {hedge_result[0] if hedge_result else None}")
                            logging.error(f"❌{config['KEY']} | {SERVER}: No suitable option found for SELL signal. Main: {result[0]} Hedge: {hedge_result[0] if hedge_result else None}")
                            # send_telegram_message(f"❌{config['KEY']} | {SERVER}: No suitable option found for SELL signal.",user['telegram_chat_id'], user['telegram_token'])
                            
                            err_msg = f"❌{config['KEY']} | {SERVER} : "
                            err_msg += "No Main option found" if result[0] is None else "No Hedge option found"
                            send_telegram_message_admin(err_msg)
                            # continue (Assuming this is inside a loop)
                        else:
                            # 4. EXECUTION
                            opt_symbol, strike, expiry, ltp, _ = result
                            hedge_opt_symbol, hedge_strike, hedge_expiry, hedge_ltp, _ = hedge_result if hedge_result else (None, None, None, 0, None)

                            temp_trade_symbols = {
                                "OptionSymbol": opt_symbol,
                                "hedge_option_symbol": hedge_opt_symbol
                            }

                            print(f"📤{key} | Entering SELL Sequence for {opt_symbol} with Hedge {hedge_opt_symbol}")
                            logging.info(f"📤 {key} | Entering SELL Sequence for {opt_symbol} with Hedge {hedge_opt_symbol}")

                            qty, avg_price, hedge_avg_price = execute_robust_entry(temp_trade_symbols, config, user)

                            print(f"📤{key} | SELL Entry Executed: {opt_symbol} @ ₹{avg_price:.2f} | Qty: {qty}. Hedge {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f}")
                            logging.info(f"📤{key} | Entered in {opt_symbol} @ ₹{avg_price:.2f} | Qty: {qty}. Hedge {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f}")
                            
                            if not is_valid_trade_data(qty, avg_price, hedge_avg_price, hedge_required=h_required):
                                err_msg = f"⚠️ {key} | FAILED Entry:{opt_symbol} or {hedge_opt_symbol}  Qty or Price is 0. Database NOT updated."
                                logging.error(err_msg)
                                send_telegram_message_admin(err_msg)
                                # break (Assuming this is inside a loop)

                            # 5. DB SAVE & TELEGRAM
                            trade = get_clean_trade({
                                "Signal": "SELL", "SpotEntry": close, "OptionSymbol": opt_symbol,
                                "Strike": strike, "Expiry": expiry,
                                "OptionSellPrice": avg_price, "EntryTime": current_time,
                                "qty": qty,  "interval": config['INTERVAL'], "real_trade": config['REAL_TRADE'],
                                "EntryReason":"SIGNAL_GENERATED", "ExpiryType":config['EXPIRY'],
                                "Strategy":config['STRATEGY'], "Key":key,
                                "hedge_option_symbol":hedge_opt_symbol,
                                "hedge_strike":hedge_strike, "hedge_option_buy_price":hedge_avg_price,
                                "hedge_qty": qty if hedge_avg_price > 0 else "-", 
                                "hedge_entry_time": current_time if hedge_avg_price > 0 else "-"
                            })
                            
                            save_open_position(trade, config, user['id'])
                            position = "SELL"
                            msg = f"🔴 {key} | {user['user']} {SERVER} | Sell Signal {opt_symbol} | Avg ₹{avg_price:.2f} | Qty: {qty}. Hedge {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f}"
                            print(msg)
                            logging.info(msg)
                            market_vibe = "Bearish Momentum Detected"
                            entry_message = (
                                f"🚀 *ENTRY SIGNAL LOGGED*\n\n"
                                f"🔴 *SELL* {opt_symbol} @ ₹{avg_price:.2f}\n"
                                f"🟢 *BUY* (Fence) {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f}\n\n"
                                f"📊 Market Study | Nifty Update\n"
                                f"📍 Nifty Spot: {close}\n"
                                f"🌟 Market Mood: {market_vibe}\n\n"
                                f"My automated system shows current levels are favorable for a trend. I'm tracking this setup for my own study.\n\n"
                                f"⚠️ Note: This is an automated log for educational study. I am NOT a SEBI-registered advisor. Not a trading recommendation."
                            )
                            send_telegram_signals_users(entry_message, user['telegram_chat_id'], user['telegram_token'])

                    except Exception as e:
                        print(f"❌ {key} | {user['user']} {SERVER} | Error during SELL entry execution: {str(e)}")
                        logging.error(f"❌ {key} | {user['user']} {SERVER} | SELL Entry Execution Critical Error: {str(e)}")
                        send_telegram_message_admin(f"❌ {key} | {user['user']} {SERVER} | SELL Entry Execution Critical Error for {key} | {user['user']} | {SERVER}: {str(e)}")
                    # --- ENTRY CODE EXECUTION (SELL) :: END ---

                next_candle_time = get_next_candle_time(config['INTERVAL'])
                # ✅ Add this flag before the while loop
                target_hit = False
                while datetime.datetime.now() < next_candle_time:
                    # Actively monitor current position LTP
                    if trade and "OptionSymbol" in trade:
                        current_ltp = get_quotes_with_retry(trade["OptionSymbol"] ,user)
                        entry_ltp = trade["OptionSellPrice"]
                        if current_ltp != None and entry_ltp != None:
                            yestime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            percent_change = round(((current_ltp - entry_ltp) / entry_ltp) * 100,2)
                            print(f"{key} | {user['user']} | position at {yestime}: {trade['Signal']} | {trade['OptionSymbol']} | Entry LTP: ₹{entry_ltp:.2f} | Current LTP: ₹{current_ltp:.2f} | Chg % {percent_change} | Qty: {trade['qty']}")
                    
                    # ✅ Intraday  EXIT 
                    now = datetime.datetime.now()
                    
                    if now.time().hour == 15 and now.time().minute >= 15 and trade and "OptionSymbol" in trade and position:
                        if config['INTRADAY'] == "yes":
                            trade, position = close_position_and_no_new_trade(trade, position, close, ts,config, user, key)
                            print(f"⏰ {key}  | {user['user']} {SERVER}  | Intraday mode: No new trades after 3:15 PM. Waiting for market close.")
                            logging.info(f"⏰ {key}  | {user['user']} {SERVER}  | Intraday mode: No new trades after 3:15 PM. Waiting for market close.")
                            # send_telegram_message(f"⏰ {key}  | {user['user']} {SERVER}  | Intraday mode: No new trades after 3:15 PM. Waiting for market close.",user['telegram_chat_id'], user['telegram_token'])
                            break

                    if trade and "OptionSymbol" in trade and "OptionSellPrice" in trade and target_hit == False:
                        current_ltp = get_quotes_with_retry(trade["OptionSymbol"] ,user)
                        entry_ltp = trade["OptionSellPrice"]

                       
                        if check_trade_stoploss_hit(user, trade, config):
                            print(f"📥{key} | {user['user']} {SERVER} |  StopLoss Exit: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']} and {trade['hedge_option_symbol']}")
                            logging.info(f"📥{key} | {user['user']} {SERVER} |  StopLoss Exit: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']} and {trade['hedge_option_symbol']}")

                            # --- ROBUST EXIT EXECUTION ---
                            # We use DIFF to ensure BOTH legs exit on StopLoss
                            # Function will KILL thread if any mismatch or partial fill occurs
                            exit_qty, avg_price, hedge_avg_price = execute_robust_exit(
                                trade, 
                                config, 
                                user, 
                                expiry_match="DIFF" 
                            )
                            print(f"📤{key} | StopLoss Exit executed for {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty} And {trade['hedge_option_symbol']} with Avg price: ₹{hedge_avg_price:.2f} | Qty: {exit_qty}" )
                            logging.info(f"📤{key} | StopLoss Exit executed for {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty} And {trade['hedge_option_symbol']} with Avg price: ₹{hedge_avg_price:.2f} | Qty: {exit_qty}" )

                            if not is_valid_trade_data(exit_qty, avg_price, hedge_avg_price, hedge_required=True):
                                err_msg = f"⚠️ {key} | StopLoss Exit FAILED : Qty ({exit_qty}) or Price ({avg_price}) or ({hedge_avg_price}) is 0 for {trade['OptionSymbol']} or {trade['hedge_option_symbol']} . DB NOT updated."
                                logging.error(err_msg)
                                send_telegram_message_admin(err_msg)
                                update_trade_config_on_failure(config['KEY'], err_msg, user)
                                return 

                            trade.update({
                                "OptionBuyPrice": avg_price,
                                "SpotExit": close,
                                "ExitTime": current_time,
                                "PnL": trade["OptionSellPrice"] - avg_price,
                                "qty": exit_qty,
                                "ExitReason": "STOPLOSS_HIT",
                                "hedge_option_sell_price": hedge_avg_price,
                                "hedge_exit_time": current_time,
                                "hedge_pnl": (hedge_avg_price - trade["hedge_option_buy_price"]) if hedge_avg_price > 0 else 0,
                            })
                            
                            # Final PnL Calculation
                            trade["total_pnl"] = trade["PnL"] + trade.get("hedge_pnl", 0)

                            trade = get_clean_trade(trade)
                            record_trade(trade, config, user['id'])
                            delete_open_position(trade["OptionSymbol"], config, trade, user['id'])
                            
                            # NOTIFY
                            msg = (f"📤 {user['user']} {SERVER} | {key} | StopLoss Exit {trade['Signal']}\n"
                                f"{trade['OptionSymbol']} @ ₹{avg_price:.2f}\n"
                                f"Hedge: {trade['hedge_option_symbol']} @ ₹{hedge_avg_price:.2f}\n"
                                f"Total PnL/Qty: ₹{trade['total_pnl']:.2f}")
                            # send_telegram_message(msg, user['telegram_chat_id'], user['telegram_token'])
                            
                            logging.info(msg)

                            last_expiry = trade["Expiry"]
                            signal = trade["Signal"]
                            trade = {} 
                            position = None
                            break # Break out of the monitoring loop as position is closed
                        
                        # Target completed of 40%. Hence exiting current positions for Rollover.
                        if current_ltp != None and entry_ltp != None and entry_ltp != 0.0 and current_ltp <= ROLLOVER_CALC * entry_ltp:
                            
                            # --- TARGET EXIT PREPARATION ---
                            # Rollover position :: Started

                            # --- POST-EXIT RESTRICTION CHECK ---
                            if config['NEW_TRADE'].lower() == "no":
                                target_hit = True  # Set the flag to True to avoid multiple triggers
                                
                                print(f"📥 {key} | {SERVER} | Rollover Exit: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']} | Selling : {trade['hedge_option_symbol']}")
                                logging.info(f"📥{key} | {user['user']} {SERVER} |  Rollover Exit: Buying back {trade['OptionSymbol']} | Qty: {trade['qty']} | Selling : {trade['hedge_option_symbol']}")

                                # --- ROBUST EXIT EXECUTION ---
                                # Using DIFF ensures BOTH legs exit on Target Hit (Terminal Event)
                                # This handles NH/SEMI/FULL internally and kills thread on mismatch
                                exit_qty, avg_price, hedge_avg_price = execute_robust_exit(
                                    trade, 
                                    config, 
                                    user, 
                                    expiry_match="DIFF"
                                )

                                logging.info(f"📤{key} | Exited from {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty} And {trade['hedge_option_symbol']} with Avg price: ₹{hedge_avg_price:.2f} | Qty: {exit_qty}" )

                                if not is_valid_trade_data(exit_qty, avg_price, hedge_avg_price, hedge_required=True):
                                    err_msg = f"⚠️ {key} | FAILED EXIT:{trade['OptionSymbol']} or {trade['hedge_option_symbol']} of Qty ({exit_qty}) or Price ({avg_price}) or ({hedge_avg_price}) is 0 for {trade['OptionSymbol']} or {trade['hedge_option_symbol']}. Database NOT updated."
                                    logging.error(err_msg)
                                    send_telegram_message_admin(err_msg)
                                    update_trade_config_on_failure(config['KEY'], err_msg, user)
                                    return 

                                # UPDATE TRADE DATA
                                trade.update({
                                    "OptionBuyPrice": avg_price,
                                    "SpotExit": close,
                                    "ExitTime": current_time,
                                    "PnL": trade["OptionSellPrice"] - avg_price,
                                    "qty": exit_qty,
                                    "ExitReason": "TARGET_HIT",
                                    "hedge_option_sell_price": hedge_avg_price,
                                    "hedge_exit_time": current_time,
                                    "hedge_pnl": (hedge_avg_price - trade["hedge_option_buy_price"]) if hedge_avg_price > 0 else 0,
                                })

                                # Calculate Total PnL (Main + Hedge)
                                trade["total_pnl"] = trade["PnL"] + trade.get("hedge_pnl", 0)

                                # DATABASE ACTIONS
                                trade = get_clean_trade(trade)
                                record_trade(trade, config, user['id'])
                                delete_open_position(trade["OptionSymbol"], config, trade, user['id'])

                                # NOTIFICATIONS
                                # send_telegram_message(
                                #     f"📤 {key}  | {user['user']} {SERVER}  |  Rollover Exit {trade['Signal']}\n"
                                #     f"{trade['OptionSymbol']} @ ₹{avg_price:.2f}. "
                                #     f"Hedge Symbol {trade['hedge_option_symbol']} | @ ₹{hedge_avg_price:.2f} | "
                                #     f"Total Profit/Qty: {trade['total_pnl']:.2f}",
                                #     user['telegram_chat_id'], user['telegram_token']
                                # )
                                market_vibe = "Rollover Detected"
                                exit_message = (
                                    f"🏁 *EXIT SIGNAL LOGGED*\n\n"
                                    f"🟢 *BUY (Back)* {trade['OptionSymbol']} @ ₹{avg_price:.2f}\n"
                                    f"🔴 *SELL (Fence)* {hedge_option_symbol} @ ₹{hedge_avg_price:.2f}\n\n"
                                    f"💰 *Performance:* +₹{trade['total_pnl']:.2f} Per Qty\n"
                                    f"📊 Nifty Spot: {close}\n"
                                    f"🌟 Market Mood: {market_vibe}\n\n"
                                    f"The system identified a shift in trend and closed the setup in my personal log.\n\n"
                                    f"⚠️ Note: Educational log only. I am NOT SEBI-registered. Past performance does not guarantee future results."
                                )
                                send_telegram_signals_users(exit_message,user['telegram_chat_id'], user['telegram_token'])
                                print(f"🔴 {key} | {user['user']} {SERVER} | Target finalized for {trade['OptionSymbol']} at ₹{avg_price:.2f} | Hedge Symbol {trade['hedge_option_symbol']} | @ ₹{hedge_avg_price:.2f} | Total Profit/Qty: {trade['total_pnl']:.2f}")
                                logging.info(f"🔴 {key} | {user['user']} {SERVER} | Target finalized for {trade['OptionSymbol']} at ₹{avg_price:.2f} | Hedge Symbol {trade['hedge_option_symbol']} | @ ₹{hedge_avg_price:.2f} | Total Profit/Qty: {trade['total_pnl']:.2f}")
                                
                                # CLEANUP
                                last_expiry = trade["Expiry"]
                                signal = trade["Signal"]
                                trade = {} # Reset trade object

                                # NOTE: Hedge was already closed by execute_robust_exit(expiry_match="DIFF")
                                # No manual order needed here.

                                print(f"🚫  {key}  | {user['user']} {SERVER}  |  No new trades allowed after target exit.")
                                logging.info(f"🚫 {key} | {user['user']} {SERVER}  |  No new trades allowed after target exit.")
                                # send_telegram_message(f"🚫 {key} | {user['user']} {SERVER}  |  No new trades allowed after target exit.", user['telegram_chat_id'], user['telegram_token'])

                                # Reset position state
                                position = None

                                # Break out of the monitoring loop
                                break
                                
                            else:
                            # --- REENTRY / ROLLOVER LOGIC (STRICT INTEGRATION) ---
                            
                                result = (None, None, None, None, None)
                                signal = trade["Signal"]

                                # 1. PRIMARY SEARCH
                                for attempt in range(3):
                                    # Returns: opt_symbol, opt_strike, opt_expiry, opt_ltp, h_sym
                                    result = get_robust_optimal_option(
                                        signal, 
                                        close, 
                                        config['NEAREST_LTP'], 
                                        instruments_df, 
                                        config, 
                                        user, 
                                        hedge_offset=200 if config.get('HEDGE_TYPE') == "H-M200" else 100, 
                                        hedge_required=(config.get('HEDGE_TYPE') in ["H-M100", "H-M200"])
                                    )
                                    
                                    if result[0] is not None:
                                        break
                                    print(f"⚠️ {key}  |  Search Attempt {attempt+1} failed. Retrying in 2s...")
                                    logging.info(f"⚠️{key}  | Search Attempt {attempt+1} failed. Retrying in 2s...")
                                    time.sleep(2)

                                last_expiry = trade['Expiry']
                                if result is None or result[0] is None:
                                    print(f"❌ {key} | No expiry found after {last_expiry} for reentry.")
                                    logging.error(f"❌ {key} | No expiry found after {last_expiry} for reentry.")
                                    position = None
                                    continue
                                else:
                                    opt_symbol, strike, expiry, main_ltp, hedge_opt_symbol = result
                                    
                                    # 1. Determine Expiry Match
                                    expiry_match = "SAME" if expiry == last_expiry else "DIFF"
                                    
                                    # 2. Setup Symbols for Entry
                                    target_qty = int(config['QTY'])
                                    existing_qty = int(trade.get('qty', target_qty))
                                    qty_changed = (target_qty != existing_qty)

                                    hedge_strike = trade.get('hedge_strike')
                                    hedge_expiry = trade.get('expiry')
                                    hedge_ltp = get_quotes_with_retry(trade.get('hedge_option_symbol') , user)
                                    if expiry_match == "SAME" and not qty_changed:
                                        hedge_opt_symbol = trade.get('hedge_option_symbol')  # Force same hedge if expiry is same, even if search found a different one

                                    # 3. EXECUTE ROBUST EXIT
                                    exit_qty, exit_avg, exit_h_avg = execute_robust_exit(trade, config, user, expiry_match=expiry_match)
                                    if expiry_match == "SAME" and not qty_changed:
                                        exit_h_avg = hedge_ltp

                                    if exit_qty > 0 and exit_avg > 0 and exit_h_avg > 0: 
                                        # UPDATE TRADE DATA
                                        trade.update({
                                            "OptionBuyPrice": exit_avg,
                                            "SpotExit": close,
                                            "ExitTime": current_time,
                                            "PnL": (trade["OptionSellPrice"] - exit_avg),
                                            "qty": exit_qty,
                                            "ExitReason": "TARGET_HIT",
                                            "hedge_option_sell_price": exit_h_avg,
                                            "hedge_exit_time": current_time,
                                            "hedge_pnl": (exit_h_avg - trade["hedge_option_buy_price"]) if exit_h_avg > 0 else 0,
                                            "total_pnl": (trade["OptionSellPrice"] - exit_avg) + (exit_h_avg - trade["hedge_option_buy_price"])
                                        })
                                    else:
                                        reason = f"{user['user']} | {key} | Error in exit: {trade['OptionSymbol']} of Qty {exit_qty} with Avg of {exit_avg}, Hedge {trade['hedge_option_symbol']} with Avg of {exit_h_avg}"
                                        print(f"❌ {reason}")
                                        logging.error(f"❌ {reason}")
                                        send_telegram_message_admin(f"❌ {reason}")
                                        update_trade_config_on_failure(config['KEY'], reason, user)
                                        break
                                    
                                    # DATABASE ACTIONS
                                    trade = get_clean_trade(trade)
                                    record_trade(trade, config, user['id'])
                                    delete_open_position(trade["OptionSymbol"], config, trade, user['id'])
                                    # send_telegram_message(f"📤 {key} | {user['user']} {SERVER}  |  Rollover Exit {trade['Signal']}", user['telegram_chat_id'], user['telegram_token'])
                                    market_vibe = "Rollover Detected"
                                    exit_message = (
                                        f"🏁 *EXIT SIGNAL LOGGED*\n\n"
                                        f"🟢 *BUY (Back)* {trade['OptionSymbol']} @ ₹{exit_avg:.2f}\n"
                                        f"🔴 *SELL (Fence)* {trade['hedge_option_symbol']} @ ₹{exit_h_avg:.2f}\n\n"
                                        f"💰 *Performance:* +₹{trade['total_pnl']:.2f} Per Qty\n"
                                        f"📊 Nifty Spot: {close}\n"
                                        f"🌟 Market Mood: {market_vibe}\n\n"
                                        f"The system identified a shift in trend and closed the setup in my personal log.\n\n"
                                        f"⚠️ Note: Educational log only. I am NOT SEBI-registered. Past performance does not guarantee future results."
                                    )
                                    send_telegram_signals_users(exit_message,user['telegram_chat_id'], user['telegram_token'])
                                    
                                    # If we need a NEW hedge (Expiry change or forced refresh)
                                    if expiry_match == "DIFF" or config['HEDGE_ROLLOVER_TYPE'] == 'FULL':
                                        if config['HEDGE_TYPE'] == "H-P10":
                                            hedge_result = (None, None, None, None, None)
                                            for attempt in range(3):
                                                hedge_result = get_robust_optimal_option(signal, close, HEDGE_NEAREST_LTP, instruments_df, config, user, hedge_required=False)
                                                if hedge_result[0] is not None:
                                                    break
                                                print(f"⚠️{key} | Search Attempt {attempt+1} failed. Retrying...")
                                                logging.info(f"⚠️{key} | Search Attempt {attempt+1} failed. Retrying...")
                                                time.sleep(2)
                                            
                                            if hedge_result[0] is not None:
                                                hedge_opt_symbol = hedge_result[0]
                                                # Using strike and ltp from result indices as per your function return
                                                h_ltp_val = hedge_result[3] 
                                        
                                    # Note: M100/M200 hedge_opt_symbol is already populated from the first search result[4]

                                    # 4. PREPARE FOR ENTRY
                                    temp_trade_symbols = {
                                        "OptionSymbol": opt_symbol,
                                        "hedge_option_symbol": hedge_opt_symbol
                                    }
                                    
                                    skip_h_entry = False
                                    if config['HEDGE_TYPE'] == "NH":
                                        skip_h_entry = True
                                    elif config['HEDGE_ROLLOVER_TYPE'] == 'SEMI' and expiry_match == "SAME" and not qty_changed:
                                        skip_h_entry = True

                                    # 5. EXECUTE ROBUST ENTRY
                                    new_qty, new_avg, new_h_avg = execute_robust_entry(temp_trade_symbols, config, user, skip_hedge_override=skip_h_entry)

                                    if not is_valid_trade_data(new_qty, new_avg, new_h_avg, hedge_required=True):
                                        err_msg = f"⚠️ {key} | FAILED Entry: {opt_symbol} or {hedge_opt_symbol} Qty or Price is 0."
                                        logging.error(err_msg)
                                        send_telegram_message_admin(err_msg)
                                        break
                                    
                                    hedge_avg_price = trade.get('hedge_option_sell_price') if skip_h_entry and config['HEDGE_TYPE'] != "NH" else new_h_avg
                                    # 6. FINALIZE TRADE OBJECT
                                    trade = {
                                        "Signal": signal, "SpotEntry": close, "OptionSymbol": opt_symbol,
                                        "Strike": strike, "Expiry": expiry,
                                        "OptionSellPrice": new_avg, "EntryTime": current_time,
                                        "qty": new_qty, "interval": config['INTERVAL'], "real_trade": config['REAL_TRADE'],
                                        "EntryReason": "ROLLOVER_REENTRY", "Key": key,
                                        "hedge_option_symbol": hedge_opt_symbol,
                                        "hedge_strike": strike + ((200 if config.get('HEDGE_TYPE') == "H-M200" else 100) * (-1 if signal == "BUY" else 1)), 
                                        "hedge_option_buy_price": hedge_avg_price,
                                        "hedge_qty": new_qty if hedge_avg_price > 0 else "-",
                                        "hedge_entry_time": current_time if hedge_avg_price > 0 else "-"
                                    }
                                    
                                    trade = get_clean_trade(trade)
                                    save_open_position(trade, config, user['id'])
                                    print(f"🔁 {key} | {user['user']} {SERVER} | Rollover Reentry {signal} for {opt_symbol} at ₹{new_avg:.2f} with Hedge {hedge_opt_symbol} at ₹{hedge_avg_price:.2f}")
                                    logging.info(f"🔁 {key} | {user['user']} {SERVER} | Rollover Reentry {signal} for {opt_symbol} at ₹{new_avg:.2f} with Hedge {hedge_opt_symbol} at ₹{hedge_avg_price:.2f}")
                                    # send_telegram_message(f"🔁 {key} | Rollover Reentry {signal}\n {opt_symbol} @ ₹{new_avg:.2f} \n {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f}", user['telegram_chat_id'], user['telegram_token'])
                                    market_vibe = "Trend Continuation"
                                    entry_message = (
                                        f"🚀 *ENTRY SIGNAL LOGGED*\n\n"
                                        f"🔴 *SELL* {opt_symbol} @ ₹{new_avg:.2f}\n"
                                        f"🟢 *BUY* (Fence) {hedge_opt_symbol} @ ₹{hedge_avg_price:.2f}\n\n"
                                        f"📊 Market Study | Nifty Update\n"
                                        f"📍 Nifty Spot: {close}\n"
                                        f"🌟 Market Mood: {market_vibe}\n\n"
                                        f"My automated system shows current levels are favorable for a trend. I'm tracking this setup for my own study.\n\n"
                                        f"⚠️ Note: This is an automated log for educational study. I am NOT a SEBI-registered advisor. Not a trading recommendation."
                                    )
                                    send_telegram_signals_users(entry_message,user['telegram_chat_id'], user['telegram_token'])
                                # # Rollover position :: End
                    
                    random_number = random.randint(7, 15)
                    time.sleep(random_number)

            # NH STRATEGY (No Hedge) - Only execute main leg, skip all hedge logic
            elif config['HEDGE_TYPE'] == "NH":
                
                # ✅ BUY SIGNAL 
                if latest['buySignal'] and position != "BUY":
                    
                    # Exit without Hedge position and Enter new position on BUY Signal Generation.
                    if position == "SELL":
                        # 1. SETUP EXIT PARAMETERS
                        # Since this was a Main-only block, we ensure skip_hedge is True 
                        # unless the config says otherwise.
                        # EXIT CODE EXECUTION :: START
                        existing_qty = int(trade.get("qty", config['QTY']))
                        
                        print(f"📥{key} | {user['user']} {SERVER} |  Exit Signal Generated: Buying back {trade['OptionSymbol']}")
                        logging.info(f"📥{key} | {user['user']} {SERVER}  | Exit Signal Generated: Buying back {trade['OptionSymbol']}")

                        # 2. ROBUST EXIT EXECUTION
                        # This replaces place_option_hybrid_order and the avg_price None checks.
                        # It handles NH/SEMI/FULL logic. Kills thread on mismatch/failure.
                        exit_qty, avg_price, hedge_avg_price = execute_robust_exit(
                            trade, 
                            config, 
                            user, 
                            expiry_match="DIFF" # Standard signal flip forces full exit
                        )
                        print(f"📤{key} | Exited without Hedge position {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty}" )
                        logging.info(f"📤{key} | Exited without Hedge position {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty}" )

                        if not is_valid_trade_data(exit_qty, avg_price, hedge_avg_price, hedge_required=False):
                            err_msg = f"⚠️ {key} | FAILED EXIT:{trade['OptionSymbol']} or {trade['hedge_option_symbol']} of Qty ({exit_qty}) or Price ({avg_price}) is 0. Database NOT updated."
                            print(err_msg)
                            logging.error(err_msg)
                            send_telegram_message_admin(err_msg)
                            update_trade_config_on_failure(config['KEY'], err_msg, user)
                            return                         

                        # 3. UPDATE DATA & RECORD
                        trade.update({
                            "OptionBuyPrice": avg_price,
                            "SpotExit": close,
                            "ExitTime": current_time,
                            "PnL": trade["OptionSellPrice"] - avg_price,
                            "qty": exit_qty,
                            "ExitReason": "SIGNAL_GENERATED",
                            "hedge_option_sell_price": hedge_avg_price,
                            "hedge_exit_time": current_time,
                            "hedge_pnl": (hedge_avg_price - trade.get("hedge_option_buy_price", 0)) if hedge_avg_price > 0 else 0.0,
                        })
                        
                        trade["total_pnl"] = trade["PnL"] + trade.get("hedge_pnl", 0)

                        trade = get_clean_trade(trade)
                        record_trade(trade, config, user['id'])
                        delete_open_position(trade["OptionSymbol"], config, trade, user['id'])
                        
                        # send_telegram_message(f"📤 {key} | {user['user']} {SERVER} | Exit Signal Generated: Buy back {trade['OptionSymbol']} @ ₹{avg_price:.2f} \n {trade['hedge_option_symbol']} @ ₹{hedge_avg_price}. Profit/Qty: {trade['total_pnl']:.2f}", user['telegram_chat_id'], user['telegram_token'])
                        market_vibe = "Trend Reversal"
                        exit_message = (
                            f"🏁 *EXIT SIGNAL LOGGED*\n\n"
                            f"🟢 *BUY (Back)* {trade['OptionSymbol']} @ ₹{avg_price:.2f}\n"
                            f"🔴 *SELL (Fence)* {trade['hedge_option_symbol']} @ ₹{hedge_avg_price:.2f}\n\n"
                            f"💰 *Performance:* +₹{trade['total_pnl']:.2f} Per Qty\n"
                            f"📊 Nifty Spot: {close}\n"
                            f"🌟 Market Mood: {market_vibe}\n\n"
                            f"The system identified a shift in trend and closed the setup in my personal log.\n\n"
                            f"⚠️ Note: Educational log only. I am NOT SEBI-registered. Past performance does not guarantee future results."
                        )
                        send_telegram_signals_users(exit_message, user['telegram_chat_id'], user['telegram_token'])
                        # EXIT CODE EXECUTION :: END
                    # --- NEW TRADE CHECKS ---
                    if config['NEW_TRADE'].lower() == "no":
                        print(f"🚫 {user['user']} | {key} | No new trades allowed. Skipping BUY signal.")
                        logging.info(f"🚫 {user['user']} | {key} | No new trades allowed. Skipping BUY signal.")
                        break

                    if check_monthly_stoploss_hit(user, config):
                        print(f"🚫 {user['user']} | {key} | Monthly StopLoss hit. No new trades allowed for the rest of the month.")
                        logging.info(f"🚫 {user['user']} | {key} | Monthly StopLoss hit. No new trades allowed for the rest of the month.")
                        break

                    # BUY ENTRY CODE EXECUTION :: START

                    result = (None, None, None, None, None)

                    for attempt in range(3):
                        result = get_robust_optimal_option(
                            "BUY",
                            close,
                            config['NEAREST_LTP'],
                            instruments_df,
                            config,
                            user,
                            hedge_offset=None,
                            hedge_required=False   # ✅ EXACT same behavior as before
                        )
                        
                        # If valid symbol found
                        if result and result[0] is not None:
                            break
                        
                        print(f"⚠️{key} | {user['user']} {SERVER} | Search Attempt {attempt+1} failed to find an option within tolerance. Retrying in 2s...")
                        logging.info(f"⚠️{key} | {user['user']} {SERVER} | Search Attempt {attempt+1} failed to find an option within tolerance. Retrying in 2s...")
                        time.sleep(2)

                    # -------------------------------
                    # FAILURE CHECK
                    # -------------------------------
                    if not result or result[0] is None:
                        print(f"❌{key} | {user['user']} {SERVER} | No suitable option found for BUY signal.")
                        logging.error(f"❌{key} | {user['user']} {SERVER} | No suitable option found for BUY signal.")
                        continue

                    # -------------------------------
                    # UNPACK (ignore hedge output)
                    # -------------------------------
                    opt_symbol, strike, expiry, ltp, _ = result

                    # -------------------------------
                    # PREPARE ENTRY SYMBOLS (UNCHANGED)
                    # -------------------------------
                    temp_trade_symbols = {
                        "OptionSymbol": opt_symbol,
                        "hedge_option_symbol": '-'
                    }

                    print(f"📤 {key} | {user['user']} {SERVER} | Enter Signal Generated: Selling {opt_symbol} | LTP: ₹{ltp:.2f}")
                    logging.info(f"📤 {key} | {user['user']} {SERVER} | Enter Signal Generated: Selling {opt_symbol} | LTP: ₹{ltp:.2f}")

                    # -------------------------------
                    # ENTRY EXECUTION
                    # -------------------------------
                    new_qty, avg_price, hedge_avg_price = execute_robust_entry(
                        temp_trade_symbols,
                        config,
                        user
                    )

                    print(f"📤{key} | Entered without Hedge position {opt_symbol} with Avg price: ₹{avg_price:.2f} | Qty: {new_qty}.")
                    logging.info(f"📤{key} | Entered without Hedge position {opt_symbol} with Avg price: ₹{avg_price:.2f} | Qty: {new_qty}.")

                    # -------------------------------
                    # VALIDATION (UNCHANGED)
                    # -------------------------------
                    if not is_valid_trade_data(new_qty, avg_price, hedge_avg_price, hedge_required=False):
                        err_msg = f"⚠️ {key} | FAILED ENTRY:{opt_symbol} of Qty ({new_qty}) or Price ({avg_price}) is 0. Database NOT updated."
                        print(err_msg)
                        logging.error(err_msg)
                        send_telegram_message_admin(err_msg)
                        break

                    # -------------------------------
                    # SAVE TRADE
                    # -------------------------------
                    trade = {
                        "Signal": "BUY",
                        "SpotEntry": close,
                        "OptionSymbol": opt_symbol,
                        "Strike": strike,
                        "Expiry": expiry,

                        "OptionSellPrice": avg_price,
                        "EntryTime": current_time,
                        "qty": new_qty,

                        "interval": config['INTERVAL'],
                        "real_trade": config['REAL_TRADE'],
                        "EntryReason": "SIGNAL_GENERATED",
                        "ExpiryType": config['EXPIRY'],
                        "Strategy": config['STRATEGY'],
                        "Key": key,

                        "hedge_option_symbol": temp_trade_symbols["hedge_option_symbol"],
                        "hedge_strike": "-",
                        "hedge_option_buy_price": hedge_avg_price,
                        "hedge_qty": new_qty if hedge_avg_price > 0 else "-",
                        "hedge_entry_time": current_time if hedge_avg_price > 0 else "-"
                    }

                    trade = get_clean_trade(trade)
                    save_open_position(trade, config, user['id'])

                    position = "BUY"

                    print(f"✅ {key} | {user['user']} {SERVER} | BUY Entry Signal Executed: Sold {opt_symbol} | Avg Price: ₹{avg_price:.2f} | Qty: {new_qty}")
                    logging.info(f"✅ {key} | {user['user']} {SERVER} | BUY Entry Signal Executed: Sold {opt_symbol} | Avg Price: ₹{avg_price:.2f} | Qty: {new_qty}")
                    # send_telegram_message(
                    #     f"🟢{key} | BUY Entry Signal Generated\n Selling {opt_symbol} | Avg ₹{avg_price:.2f} | Qty: {new_qty}",
                    #     user['telegram_chat_id'],
                    #     user['telegram_token']
                    # )
                    
                    # BUY ENTRY CODE EXECUTION :: END

                # Exit the without Hedge position and Enter new position on Sell Signal Generation.
                elif latest['sellSignal'] and position != "SELL":
                    
                    if position == "BUY":

                        existing_qty = int(trade.get("qty", config['QTY']))

                        print(f"📥 {key} | {user['user']} {SERVER} | Exit Signal Generated: Buying back {trade['OptionSymbol']} | Qty: {existing_qty}")
                        logging.info(f"📥 {key} | {user['user']} {SERVER} | Exit Signal Generated: Buying back {trade['OptionSymbol']} | Qty: {existing_qty}")

                        exit_qty, avg_price, hedge_avg_price = execute_robust_exit(
                            trade,
                            config,
                            user,
                            expiry_match="DIFF"
                        )

                        logging.info(f"📤{key} | Exited without Hedge position {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty}" )

                        if not is_valid_trade_data(exit_qty, avg_price, hedge_avg_price, hedge_required=False):
                            err_msg = f"⚠️ {key} | FAILED EXIT:{trade['OptionSymbol']} of Qty ({exit_qty}) or Price ({avg_price}) is 0. Database NOT updated."
                            logging.error(err_msg)
                            send_telegram_message_admin(err_msg)
                            update_trade_config_on_failure(config['KEY'], err_msg, user)
                            return

                        trade.update({
                            "OptionBuyPrice": avg_price,
                            "SpotExit": close,
                            "ExitTime": current_time,
                            "PnL": trade["OptionSellPrice"] - avg_price,
                            "qty": exit_qty,
                            "ExitReason": "SIGNAL_GENERATED",
                            "hedge_option_sell_price": hedge_avg_price,
                            "hedge_exit_time": current_time,
                            "hedge_pnl": (hedge_avg_price - trade.get("hedge_option_buy_price", 0)) if hedge_avg_price else 0.0
                        })

                        trade["total_pnl"] = trade["PnL"] + trade.get("hedge_pnl", 0)

                        trade = get_clean_trade(trade)
                        record_trade(trade, config, user['id'])
                        delete_open_position(trade["OptionSymbol"], config, trade, user['id'])

                        # send_telegram_message(
                        #     f"📤 {user['user']} {SERVER} | {key} |  Exit Signal Generated:\n"
                        #     f" Buying {trade['OptionSymbol']} @ ₹{avg_price:.2f} | Profit/Qty: {trade['total_pnl']:.2f}",
                        #     user['telegram_chat_id'],
                        #     user['telegram_token']
                        # )

                    # --------------------------------
                    # NEW TRADE RESTRICTIONS
                    # --------------------------------
                    if config['NEW_TRADE'].lower() == "no":
                        print(f"🚫 {key} | {user['user']} | No new trades allowed. Skipping SELL signal.")
                        logging.info(f"🚫 {key} | {user['user']} | No new trades allowed. Skipping SELL signal.")
                        break

                    if check_monthly_stoploss_hit(user, config):
                        break

                    # --------------------------------
                    # Sell ENTRY Code Execution :: Start
                    # --------------------------------
                    result = (None, None, None, None, None)

                    for attempt in range(3):
                        result = get_robust_optimal_option(
                            "SELL",
                            close,
                            config['NEAREST_LTP'],
                            instruments_df,
                            config,
                            user,
                            hedge_offset=None,
                            hedge_required=False   # ✅ SAME behavior as original
                        )
                        
                        # If valid symbol found
                        if result and result[0] is not None:
                            break
                        print(f"⚠️ {key} | Search Attempt {attempt+1} failed to find an option within tolerance. Retrying in 2s...")
                        logging.info(f"⚠️ {key} | Search Attempt {attempt+1} failed to find an option within tolerance. Retrying in 2s...")
                        time.sleep(2)

                    # -------------------------------
                    # FAILURE CHECK
                    # -------------------------------
                    if not result or result[0] is None:
                        print(f"❌ {key} | No suitable option found for SELL signal.")
                        logging.error(f"❌ {key} | No suitable option found for SELL signal.")
                        # send_telegram_message(
                        #     f"❌ {key} | {user['user']} {SERVER} | No suitable option found for SELL signal.",
                        #     user['telegram_chat_id'],
                        #     user['telegram_token']
                        # )
                        continue

                    # -------------------------------
                    # UNPACK (ignore hedge output)
                    # -------------------------------
                    opt_symbol, strike, expiry, ltp, _ = result

                    print(f"📤 {key} | {user['user']} | SELL Enter Signal Generated : Selling {opt_symbol} | Strike: {strike} | Expiry: {expiry} | LTP ₹{ltp:.2f}")
                    logging.info(f"📤 {key} | {user['user']} | SELL Enter Signal Generated : Selling {opt_symbol} | Strike: {strike} | Expiry: {expiry} | LTP ₹{ltp:.2f}")

                    # -------------------------------
                    # PREPARE ENTRY SYMBOLS
                    # -------------------------------
                    temp_trade_symbols = {
                        "OptionSymbol": opt_symbol,
                        "hedge_option_symbol": "-"
                    }

                    # -------------------------------
                    # ENTRY EXECUTION
                    # -------------------------------
                    new_qty, avg_price, hedge_avg_price = execute_robust_entry(
                        temp_trade_symbols,
                        config,
                        user
                    )

                    print(f"📤{key} | Entered without Hedge position {opt_symbol} with Avg price: ₹{avg_price:.2f} | Qty: {new_qty}.")
                    logging.info(f"📤{key} | Entered without Hedge position {opt_symbol} with Avg price: ₹{avg_price:.2f} | Qty: {new_qty}.")

                    # -------------------------------
                    # VALIDATION (UNCHANGED)
                    # -------------------------------
                    if not is_valid_trade_data(new_qty, avg_price, hedge_avg_price, hedge_required=False):
                        err_msg = f"⚠️ {key} | FAILED ENTRY:{opt_symbol} of Qty ({new_qty}) or Price ({avg_price}) is 0. Database NOT updated."
                        print(err_msg)
                        logging.error(err_msg)
                        send_telegram_message_admin(err_msg)
                        break

                    # --------------------------------
                    # SAVE TRADE
                    # --------------------------------
                    trade = {
                        "Signal": "SELL",
                        "SpotEntry": close,
                        "OptionSymbol": opt_symbol,
                        "Strike": strike,
                        "Expiry": expiry,
                        "OptionSellPrice": avg_price,
                        "EntryTime": current_time,
                        "qty": new_qty,
                        "interval": config['INTERVAL'],
                        "real_trade": config['REAL_TRADE'],
                        "EntryReason": "SIGNAL_GENERATED",
                        "ExpiryType": config['EXPIRY'],
                        "Strategy": config['STRATEGY'],
                        "Key": key,
                        "hedge_option_symbol": temp_trade_symbols["hedge_option_symbol"],
                        "hedge_strike": "-",
                        "hedge_option_buy_price": hedge_avg_price,
                        "hedge_qty": new_qty if hedge_avg_price > 0 else "-",
                        "hedge_entry_time": current_time if hedge_avg_price > 0 else "-"
                    }

                    trade = get_clean_trade(trade)
                    save_open_position(trade, config, user['id'])

                    position = "SELL"

                    # send_telegram_message(
                    #     f"🔴{key} | SELL Enter Signal Generated\n"
                    #     f" Sell {opt_symbol} | Avg ₹{avg_price:.2f} | Qty: {new_qty}",
                    #     user['telegram_chat_id'],
                    #     user['telegram_token']
                    # )
                    print(f"🔴{key} | SELL Enter Signal Generated |  Sell {opt_symbol} | Avg ₹{avg_price:.2f} | Qty: {new_qty}")
                    logging.info(f"🔴{key} | SELL Enter Signal Generated |  Sell {opt_symbol} | Avg ₹{avg_price:.2f} | Qty: {new_qty}")
                    # --------------------------------
                    # Sell ENTRY Code Execution :: END
                    # --------------------------------

                next_candle_time = get_next_candle_time(config['INTERVAL'])
                # ✅ Add this flag before the while loop
                target_hit = False
                while datetime.datetime.now() < next_candle_time:
                    # --------------------------------
                    # POSITION MONITORING
                    # --------------------------------
                    if trade and "OptionSymbol" in trade:

                        current_ltp = get_quotes_with_retry(trade["OptionSymbol"], user)
                        entry_ltp = trade["OptionSellPrice"]

                        if current_ltp is not None and entry_ltp is not None:

                            yestime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            percent_change = round(((current_ltp - entry_ltp) / entry_ltp) * 100, 2)

                            print(
                                f"{user['user']} | {config['STRATEGY']} | {config['INTERVAL']} position at {yestime}: "
                                f"{trade['Signal']} | {trade['OptionSymbol']} | Entry LTP: ₹{entry_ltp:.2f} "
                                f"| Current LTP: ₹{current_ltp:.2f} | Chg % {percent_change} | Qty: {trade['qty']}"
                            )
                            

                    # --------------------------------
                    # INTRADAY EXIT
                    # --------------------------------
                    now = datetime.datetime.now()

                    if now.time().hour == 15 and now.time().minute >= 15 and trade and position:

                        if config['INTRADAY'] == "yes":

                            trade, position = close_position_and_no_new_trade(
                                trade, position, close, ts, config, user, key
                            )

                            msg = f"⏰ {key} | {user['user']} {SERVER} |  Intraday exit triggered at 3:15 PM. Exited {trade['OptionSymbol']} at ₹{trade.get('OptionBuyPrice',0):.2f} | PnL: ₹{trade.get('PnL',0):.2f}"

                            print(msg)
                            logging.info(msg)

                            # send_telegram_message(
                            #     msg,
                            #     user['telegram_chat_id'],
                            #     user['telegram_token']
                            # )

                            break


                    # --------------------------------
                    # TARGET / STOPLOSS MANAGEMENT
                    # --------------------------------
                    if trade and "OptionSymbol" in trade and "OptionSellPrice" in trade and target_hit == False:

                        current_ltp = get_quotes_with_retry(trade["OptionSymbol"], user)
                        entry_ltp = trade["OptionSellPrice"]

                        # STOPLOSS
                        if check_trade_stoploss_hit(user, trade, config):

                            trade, position = close_position_and_no_new_trade(
                                trade, position, close, ts, config, user, key
                            )

                            break

                        # Target completed of 40%. Hence exiting current positions for Rollover.
                        
                        if current_ltp and entry_ltp and entry_ltp != 0 and current_ltp <= ROLLOVER_CALC * entry_ltp:

                            target_hit = True

                            print(f"📥 {key} | {SERVER} | Current {trade['OptionSymbol']} of Qty {trade['qty']} hit the target of 40%. Hence exiting position for Rollover."
                            )
                            logging.info(f"📥 {key} | {SERVER} | Current {trade['OptionSymbol']} of Qty {trade['qty']} hit the target of 40%. Hence exiting position for Rollover.")

                            exit_qty, avg_price, hedge_avg = execute_robust_exit(
                                trade,
                                config,
                                user,
                                expiry_match="DIFF"
                            )
                            logging.info(f"📤{key} | Exited without Hedge position {trade['OptionSymbol']} with Avg price: ₹{avg_price:.2f} | Qty: {exit_qty}" )

                            if not is_valid_trade_data(exit_qty, avg_price, hedge_avg, hedge_required=False):
                                err_msg = f"⚠️ {key} | FAILED EXIT:{trade['OptionSymbol']} of Qty ({exit_qty}) or Price ({avg_price}) is 0. Database NOT updated."
                                logging.error(err_msg)
                                send_telegram_message_admin(err_msg)
                                update_trade_config_on_failure(config['KEY'], err_msg, user)
                                return

                            trade.update({
                                "SpotExit": close,
                                "ExitTime": current_time,
                                "OptionBuyPrice": avg_price,
                                "PnL": entry_ltp - avg_price,
                                "qty": exit_qty,
                                "ExitReason": "TARGET_HIT",
                                "hedge_option_sell_price": hedge_avg,
                                "hedge_exit_time": current_time,
                                "hedge_pnl": hedge_avg - trade.get("hedge_option_buy_price",0),
                                "total_pnl": (entry_ltp - avg_price) +
                                            (hedge_avg - trade.get("hedge_option_buy_price",0))
                            })

                            trade = get_clean_trade(trade)
                            record_trade(trade, config, user['id'])
                            delete_open_position(trade["OptionSymbol"], config, trade, user['id'])

                            # send_telegram_message(
                            #     f"📤 Exit {trade['Signal']}\n"
                            #     f"{trade['OptionSymbol']} @ ₹{avg_price:.2f} | "
                            #     f"PnL ₹{trade['total_pnl']:.2f}",
                            #     user['telegram_chat_id'],
                            #     user['telegram_token']
                            # )
                            logging.info(f"🔴 {key} | {user['user']} {SERVER} | Target triggered for {trade['OptionSymbol']} at ₹{current_ltp:.2f}")


                            last_expiry = trade["Expiry"]
                            signal = trade["Signal"]

                            trade = {}

                            # --------------------------------
                            # REENTRY RULES
                            # --------------------------------

                            if config['NEW_TRADE'].lower() == "no":
                                position = None
                                break

                            if check_monthly_stoploss_hit(user, config):
                                break

                            # Re-entry in Same Direction :: Start
                            result = (None, None, None, None, None)

                            for attempt in range(3):
                                result = get_robust_optimal_option(
                                    signal,
                                    close,
                                    config['NEAREST_LTP'],
                                    instruments_df,
                                    config,
                                    user,
                                    hedge_offset=None,
                                    hedge_required=False   # ✅ same behavior
                                )
                                
                                # If valid symbol found
                                if result and result[0] is not None:
                                    break
                                
                                print(f"⚠️ {key} | Search Attempt {attempt+1} failed to find an option within tolerance. Retrying in 2s...")
                                logging.info(f"⚠️ {key} | Search Attempt {attempt+1} failed to find an option within tolerance. Retrying in 2s...")
                                time.sleep(2)

                            # -------------------------------
                            # FAILURE CHECK
                            # -------------------------------
                            if not result or result[0] is None:
                                print(f"❌ {key} | No suitable option found for REENTRY signal")
                                logging.error(f"❌ {key} | No suitable option found for REENTRY signal")

                                position = None
                                continue

                            # -------------------------------
                            # UNPACK (ignore hedge output)
                            # -------------------------------
                            opt_symbol, strike, expiry, ltp, _ = result

                            print(f"🔁 {key} | Rollover Signal Generated {signal}: {opt_symbol} | Strike {strike} | Expiry {expiry}")
                            logging.info(f"🔁 {key} | Rollover Signal Generated {signal}: {opt_symbol} | Strike {strike} | Expiry {expiry}")

                            # -------------------------------
                            # ENTRY SYMBOLS
                            # -------------------------------
                            symbols = {
                                "OptionSymbol": opt_symbol,
                                "hedge_option_symbol": "-"
                            }

                            # -------------------------------
                            # ENTRY EXECUTION
                            # -------------------------------
                            new_qty, avg_price, hedge_avg = execute_robust_entry(
                                symbols,
                                config,
                                user
                            )
                            print(f"📤{key} | Entered without Hedge position {opt_symbol} with Avg price: ₹{avg_price:.2f} | Qty: {new_qty}.")
                            logging.info(f"📤{key} | Entered without Hedge position {opt_symbol} with Avg price: ₹{avg_price:.2f} | Qty: {new_qty}.")

                            # -------------------------------
                            # VALIDATION (UNCHANGED)
                            # -------------------------------
                            if not is_valid_trade_data(new_qty, avg_price, hedge_avg, hedge_required=False):
                                err_msg = f"⚠️ {key} | FAILED ENTRY:{opt_symbol}  Qty ({new_qty}) or Price ({avg_price}) is 0 for {opt_symbol}. db NOT updated."
                                print(err_msg)
                                logging.error(err_msg)
                                send_telegram_message_admin(err_msg)
                                break 

                            # -------------------------------
                            # SAVE TRADE
                            # -------------------------------
                            trade = {
                                "Signal": signal,
                                "SpotEntry": close,
                                "OptionSymbol": opt_symbol,
                                "Strike": strike,
                                "Expiry": expiry,
                                "OptionSellPrice": avg_price,
                                "EntryTime": current_time,
                                "qty": new_qty,
                                "interval": config['INTERVAL'],
                                "real_trade": config['REAL_TRADE'],
                                "EntryReason": "ROLLOVER",
                                "ExpiryType": config['EXPIRY'],
                                "Strategy": config['STRATEGY'],
                                "Key": key,
                                "hedge_option_symbol": symbols["hedge_option_symbol"],
                                "hedge_strike": "-",
                                "hedge_option_buy_price": hedge_avg,
                                "hedge_qty": new_qty if hedge_avg > 0 else "-",
                                "hedge_entry_time": current_time if hedge_avg > 0 else "-"
                            }

                            trade = get_clean_trade(trade)
                            save_open_position(trade, config, user['id'])

                            # send_telegram_message(
                            #     f"🔁 {key} | Reentry {signal}\n"
                            #     f"{opt_symbol} | Avg ₹{avg_price:.2f} | Qty {new_qty}",
                            #     user['telegram_chat_id'],
                            #     user['telegram_token']
                            # )

                            logging.info(f"🔁 {key} | Reentry {signal} {opt_symbol} | Avg ₹{avg_price:.2f} | Qty {new_qty}")
                            print(f"🔁 {key} | Reentry {signal} {opt_symbol} | Avg ₹{avg_price:.2f} | Qty {new_qty}")
                            position = signal  
                            # Re-entry in Same Direction :: END          
                    
                    random_number = random.randint(7, 15)
                    time.sleep(random_number)

                
        except ReadTimeout as re:
            # Ignore read timeout
            logging.error(f"⚠️ {user['user']} {SERVER}  |  {key}  | Exception: {re}", exc_info=True)
            send_telegram_message_admin(f"⚠️ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} ReadTimeout Error: {re}")
            pass


        except exceptions.NetworkException:
            # Ignore network exception
            pass

        
        except Exception as e:
            logging.error(f"{user['user']} {SERVER}  | Exception: {e}", exc_info=True)
            # send_telegram_message(f"⚠️ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Error: {e}",user['telegram_chat_id'], user['telegram_token'])
            send_telegram_message_admin(f"⚠️ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Error: {e}")
            time.sleep(60)



# ====== Run ======
def init_and_run(user):
    while True:
        try:
            who_tried(user)
            
            instruments_df = pd.read_csv(INSTRUMENTS_FILE)
            threads = []


            configs = get_trade_configs(user['id'])
            keys = configs.keys()
            
            for key in keys:
                config = configs[key]
                init_db()
                t = threading.Thread(target=live_trading, args=(instruments_df, config, key, user))
                t.start()
                threads.append(t)
            for t in threads:
                t.join()
            break
        except Exception as e:
            logging.error(f"Fatal error: {e}")
            logging.error("Restarting emalive in 10 seconds...")
            time.sleep(10)


def execute_robust_entry(trade, config, user, skip_hedge_override=None):
    """
    SINGLE-SHOT ENTRY:
    Executes Hedge and Main Leg with mismatch recovery logic.
    """
    target_qty = int(config.get('QTY', 0))
    h_type = str(config.get('HEDGE_TYPE', 'FULL')).upper()
    skip_hedge = skip_hedge_override if skip_hedge_override is not None else (h_type == "NH")

    main_filled_total = 0
    main_total_val = 0.0
    hedge_filled_total = 0
    hedge_total_val = 0.0

    print(f"🚀{config['KEY']} |  Starting execute_robust_entry for {user['user']} | {trade['OptionSymbol']} | Target Qty: {target_qty} | Skip Hedge: {skip_hedge}")
    logging.info(f"🚀{config['KEY']} |  Starting execute_robust_entry for {user['user']} | {trade['OptionSymbol']} | Target Qty: {target_qty} | Skip Hedge: {skip_hedge}")
    
    # PRE-TRADE PRICE VALIDATION
    if not validate_trade_prices(trade["OptionSymbol"], trade["hedge_option_symbol"], config, user):
        logging.warning(f"🛑 {config['KEY']} |  ENTRY ABORTED: Price validation failed for {user['user']} | {trade['OptionSymbol']}")
        print(f"🛑 {config['KEY']} |  ENTRY ABORTED: Price validation failed for {user['user']} | {trade['OptionSymbol']}")
        return 0, 0, 0
    
    if skip_hedge:
        print(f"⚡{config['KEY']} |  Skipping Hedge. Placing Main SELL order for {trade['OptionSymbol']} | Target Qty: {target_qty}")
        logging.info(f"⚡{config['KEY']} |  Skipping Hedge. Placing Main SELL order for {trade['OptionSymbol']} | Target Qty: {target_qty}")
        m_id, m_avg, m_f = simulate_robust_limit_order(trade["OptionSymbol"], target_qty, "SELL", config, user, action="ENTRY")
        if m_f > 0:
            main_total_val = (m_avg * m_f)
            main_filled_total = m_f
    else:
        print(f"⚡{config['KEY']} |  Placing Hedge BUY order for {trade['hedge_option_symbol']} | Target Qty: {target_qty}")
        logging.info(f"⚡{config['KEY']} |  Placing Hedge BUY order for {trade['hedge_option_symbol']} | Target Qty: {target_qty}")
        # Step 1: Hedge BUY
        h_id, h_avg, h_f = simulate_robust_limit_order(trade["hedge_option_symbol"], target_qty, "BUY", config, user, action="ENTRY")
        
        if h_f > 0:
            print(f"⚡{config['KEY']} |  Hedge BUY filled {h_f}/{target_qty} for {trade['hedge_option_symbol']} at Avg ₹{h_avg:.2f}. Now placing Main SELL order.")
            logging.info(f"⚡{config['KEY']} |  Hedge BUY filled {h_f}/{target_qty} for {trade['hedge_option_symbol']} at Avg ₹{h_avg:.2f}. Now placing Main SELL order.")
            # Step 2: Main SELL
            m_id, m_avg, m_f = simulate_robust_limit_order(trade["OptionSymbol"], h_f, "SELL", config, user, action="ENTRY")

            if m_f == h_f:
                print(f"⚡{config['KEY']} |  Both orders filled successfully for {trade['OptionSymbol']} and {trade['hedge_option_symbol']}.")
                logging.info(f"⚡{config['KEY']} |  Both orders filled successfully for {trade['OptionSymbol']} and {trade['hedge_option_symbol']}.")

                main_total_val = (m_avg * m_f); main_filled_total = m_f
                hedge_total_val = (h_avg * h_f); hedge_filled_total = h_f
            else:
                # Step 3: Mismatch Recovery
                unhedged = h_f - m_f
                print(f"⚠️ {config['KEY']} |  Mismatch detected! Main filled {m_f} vs Hedge filled {h_f}. Attempting to reverse unhedged {unhedged} from Hedge {trade['hedge_option_symbol']}...")
                logging.warning(f"⚠️ {config['KEY']} |  Mismatch detected! Main filled {m_f} vs Hedge filled {h_f}. Attempting to reverse unhedged {unhedged} from Hedge {trade['hedge_option_symbol']}...")
                _, _, r_f = simulate_robust_limit_order(trade["hedge_option_symbol"], unhedged, "SELL", config, user, action="EXIT")
                
                retained_h = h_f - r_f
                if retained_h == m_f:
                    logging.info(f"✅ {config['KEY']} |  Recovery Success: Balanced at {m_f}.")
                    print(f"✅ {config['KEY']} |  Recovery Success: Balanced at {m_f}.")
                    main_total_val = (m_avg * m_f); main_filled_total = m_f
                    hedge_total_val = (h_avg * retained_h); hedge_filled_total = retained_h
                else:
                    reason = f"CRITICAL MISMATCH: H:{retained_h} != M:{m_f} after reversal."
                    update_trade_config_on_failure(config['KEY'], reason, user)
                    logging.critical(f"☢️ {config['KEY']} |  {reason}")
                    print(f"☢️ {config['KEY']} |  {reason}")
                    sys.exit(reason)

    final_m_avg = main_total_val / main_filled_total if main_filled_total > 0 else 0
    final_h_avg = hedge_total_val / hedge_filled_total if hedge_filled_total > 0 else 0
    
    logging.info(f"🏁 ENTRY SUMMARY | Main: {main_filled_total} @ {round(final_m_avg, 2)} | Hedge: {hedge_filled_total} @ {round(final_h_avg, 2)}")
    return main_filled_total, final_m_avg, final_h_avg


def execute_robust_exit(trade, config, user, expiry_match="DIFF"):
    """
    SINGLE-SHOT STRICT EXIT:
    - Removes 3-attempt loop; relies on 5s robust price chasing.
    - If Main exits and Hedge fails (or vice versa), triggers KILL THREAD.
    """
    print(f"🚪 {config['KEY']} | Starting EXIT of Symbol {trade['OptionSymbol']}")
    logging.info(f"🚪 {config['KEY']} | Starting EXIT of Symbol {trade['OptionSymbol']}")
    target_qty_new = int(config.get('QTY', 0))
    existing_qty = int(trade.get('qty', 0))
    hr_type = str(config.get('HEDGE_ROLLOVER_TYPE', 'FULL')).upper()
    h_type = str(config.get('HEDGE_TYPE', 'FULL')).upper()
    qty_changed = (target_qty_new != existing_qty)

    # --- EXIT GATEKEEPER ---
    skip_hedge = False 
    if h_type == "NH":
        skip_hedge = True
    elif hr_type == "SEMI" and expiry_match == "SAME":
        
        # If qty changed, we must clear the old hedge too
        skip_hedge = False if qty_changed else True
        if skip_hedge:
            logging.info(f"⚡ {config['KEY']} |  Semi Rollover with SAME expiry and unchanged qty. Skipping Hedge exit.")   
            print(f"⚡ {config['KEY']} |  Semi Rollover with SAME expiry and unchanged qty. Skipping Hedge exit.")
        else:
            logging.info(f"⚡ {config['KEY']} |  Semi Rollover but qty changed. Hedge exit will be executed to clear old position.")
            print(f"⚡ {config['KEY']} |  Semi Rollover but qty changed. Hedge exit will be executed to clear old position.")

    main_filled_total = 0
    main_total_val = 0.0
    hedge_filled_total = 0
    hedge_total_val = 0.0

    print(f"🚪 {config['KEY']} | Starting EXIT | Target Qty: {existing_qty} | Skip Hedge: {skip_hedge}")
    logging.info(f"🚪 {config['KEY']} | Starting EXIT | Target Qty: {existing_qty} | Skip Hedge: {skip_hedge}")

    # 1. Main Leg Leads (BUY to exit a SELL position)
    m_id, m_avg, m_f = simulate_robust_limit_order(
        trade["OptionSymbol"], existing_qty, "BUY", config, user, action="EXIT"
    )
    
    if m_f > 0:
        print(f"🚪 {config['KEY']} | Main EXIT filled {m_f}/{existing_qty} for {trade['OptionSymbol']} at Avg ₹{m_avg:.2f}.")
        logging.info(f"🚪 {config['KEY']} | Main EXIT filled {m_f}/{existing_qty} for {trade['OptionSymbol']} at Avg ₹{m_avg:.2f}.")

        main_total_val = (m_avg * m_f)
        main_filled_total = m_f
        
        # 2. Exit Hedge if required (SELL to exit a BUY hedge)
        if not skip_hedge:
            # We exit only the amount of hedge that corresponds to the filled main leg
            h_id, h_avg, h_f = simulate_robust_limit_order(
                trade["hedge_option_symbol"], m_f, "SELL", config, user, action="EXIT"
            )
            if h_f > 0:
                hedge_total_val = (h_avg * h_f)
                hedge_filled_total = h_f

    # --- RECONCILIATION & KILL SWITCH ---
    # Case A: Hedge mismatch (Main filled 100, Hedge filled 50)
    mismatch = (not skip_hedge and main_filled_total != hedge_filled_total)
    # Case B: Incomplete exit (Target was 100, but only 80 filled)
    incomplete = (main_filled_total < existing_qty)

    if mismatch or incomplete:
        reason = f"EXIT FAILURE: M:{main_filled_total} H:{hedge_filled_total} vs Target:{existing_qty}"
        update_trade_config_on_failure(config['KEY'], reason, user)
        print(f"☢️ {user['user']} | THREAD KILLED: {reason}")
        logging.critical(f"☢️ {user['user']} | THREAD KILLED: {reason}")
        # Give some time for logs to flush before exiting
        time.sleep(5)
        sys.exit(reason)

    final_m_avg = main_total_val / main_filled_total
    final_h_avg = hedge_total_val / hedge_filled_total if hedge_filled_total > 0 else 0
    
    print(f"🏁 EXIT Complete | Main: {main_filled_total} @ ₹{round(final_m_avg, 2)} | Hedge: {hedge_filled_total} @ ₹{round(final_h_avg, 2)}")
    logging.info(f"🏁 EXIT Complete | Main: {main_filled_total} @ ₹{round(final_m_avg, 2)} | Hedge: {hedge_filled_total} @ ₹{round(final_h_avg, 2)}")
    return main_filled_total, final_m_avg, final_h_avg
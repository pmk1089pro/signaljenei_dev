
import pandas as pd
from commonFunction import get_hedge_option, get_optimal_option, get_trade_configs, save_open_position
from config import INSTRUMENTS_FILE, LOG_FILE, SERVER
from kitefunction import get_kite_client, place_option_hybrid_order
from kitelogin import do_login
from telegrambot import send_telegram_message
from userdtls import get_all_active_user
import logging
import time
import datetime
from datetime import timedelta

# ====== Setup Logging ======
logging.basicConfig(
    filename=LOG_FILE,
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def manualEntry(signal, close, config, instruments_df, user, key, current_time):
    result = get_optimal_option(signal, close, config['NEAREST_LTP'], instruments_df, config, user)
    strike = result[1]
    hedge_result = get_hedge_option(signal, close, strike, instruments_df, config, user)
    if result is None or result[0] is None or hedge_result is None or hedge_result[0] is None:
        logging.error(f"❌INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}: No suitable option found for SELL signal.")
        send_telegram_message(f"❌ {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']}: No suitable option found for SELL signal.",user['telegram_chat_id'], user['telegram_token'])
    
    else:
        opt_symbol, strike, expiry, ltp = result
        hedge_opt_symbol, hedge_strike, hedge_expiry, hedge_ltp = hedge_result

        print(f"📤INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Entering HEDGE BUY: {hedge_opt_symbol} | Strike: {hedge_strike} | Expiry: {hedge_expiry} | LTP: ₹{hedge_ltp:.2f}")
        logging.info(f"📤INTERVAL {config['INTERVAL']} | {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Entering HEDGE BUY: {hedge_opt_symbol} | Strike: {hedge_strike} | Expiry: {hedge_expiry} | LTP: ₹{hedge_ltp:.2f}")
        # hedge_order_id, hedge_avg_price, hedge_qty = place_option_hybrid_order(hedge_opt_symbol, config['QTY'], "BUY", config, user)
        hedge_order_id , hedge_avg_price, hedge_qty = None, None, None
        print(f"📤 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Entering SELL: {opt_symbol} | Strike: {strike} | Expiry: {expiry} | LTP: ₹{ltp:.2f}")
        logging.info(f"📤 {user['user']} {SERVER}  |  {key}  |  {config['INTERVAL']} Entering SELL: {opt_symbol} | Strike: {strike} | Expiry: {expiry} | LTP: ₹{ltp:.2f}")
        
        # order_id ,avg_price,qty = place_option_hybrid_order(opt_symbol, config['QTY'], signal, config, user)
        order_id ,avg_price,qty = None, None, None
        
        logging.info(f"order_id : {order_id} | opt_symbol : {opt_symbol} avg_price : {avg_price} | qty : {qty}")
        (opt_symbol, config['QTY'], signal)
        logging.info(f"📤 Entering {signal}: Selling {opt_symbol} | Qty: {config['QTY']}")
        time.sleep(2)
        
        if hedge_avg_price is None:
            hedge_avg_price = hedge_ltp
            hedge_qty = config['QTY']

        if avg_price is None:
            avg_price = ltp
            qty = config['QTY']

        trade = {
            "Signal": "SELL", "SpotEntry": close, "OptionSymbol": opt_symbol,
            "Strike": strike, "Expiry": expiry,
            "OptionSellPrice": avg_price, "EntryTime": current_time,
            "qty": qty,  "interval": config['INTERVAL'], "real_trade": config['TRADE'],
            "EntryReason":"SIGNAL_GENERATED", "ExpiryType":config['EXPIRY'],
            "Strategy":config['STRATEGY'], "Key":key,
            "hedge_option_symbol":hedge_opt_symbol,
            "hedge_strike":hedge_strike, "hedge_option_buy_price":hedge_avg_price,
            "hedge_qty":hedge_qty, "hedge_entry_time": current_time
        }
        save_open_position(trade, config, user['id'])

if __name__ == "__main__":
    instruments_df = pd.read_csv(INSTRUMENTS_FILE)

# update these variables as per current Market data and user
    close = 26202.0
    signal = "BUY"
    current_time = '2025-11-27 09:16:00'
    user = get_all_active_user()[1]
    # do_login(user)
    key = 'JPK_60_PE_NW_RO_HG'
    configs = get_trade_configs(user['id'])
    config = configs[key]

    # manualEntry(signal, close, config, instruments_df, user, key, current_time)
    kite = get_kite_client(user)
    positions = kite.positions()
    orders = kite.orders()
    print("Open orders:")
    orders_data = []
    for order in orders:
        orders_data.append({
            'Order ID': order['order_id'],
            'Symbol': order['tradingsymbol'],
            'Qty': order['quantity'],
            'Price': order['price'],
            'Status': order['status'],
            'Type': order['transaction_type']
        })

    orders_df = pd.DataFrame(orders_data)
    print(orders_df)
    
    # Convert positions to tabular format
    positions_data = []
    for position in positions['net']:
        positions_data.append({
            'Symbol': position['tradingsymbol'],
            'Qty': position['quantity'],
            'Price': position['close_price'],
            'Type': 'BUY' if position['quantity'] > 0 else 'SELL'
        })
    
    positions_df = pd.DataFrame(positions_data)
    print(positions_df)

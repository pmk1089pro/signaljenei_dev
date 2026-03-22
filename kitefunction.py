import json
import pandas as pd
import datetime, time
import os
import sqlite3
import logging
from kiteconnect import KiteConnect
from config import ACCESS_TOKEN_FILE, INSTRUMENTS_FILE, LOG_FILE, DB_FILE
from telegrambot import send_telegram_message


logging.basicConfig(
    filename=LOG_FILE,
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
# Load instruments.csv
instruments_df = pd.read_csv(INSTRUMENTS_FILE)


def get_kite_client(user):
    try:
        # Fetch token data from kite_session table
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            SELECT access_token, api_key, api_secret 
            FROM kite_session 
            WHERE user_id = ?
        """, (user['id'],))
        row = c.fetchone()
        conn.close()
        
        if not row:
            print(f"❌ No session found for user_id: {user['id']}")
            logging.error(f"No session found for user_id: {user['id']}")
            return None
        
        access_token, api_key, api_secret = row
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        return kite
    except Exception as e:
        print("❌ Could not load access token:", e)
        logging.error(f"Error loading access token: {e}")
        return None
    

def get_profile(user):
    kite = get_kite_client(user)
    if kite:
        try:
            profile = kite.profile()
            return profile["user_name"]
        except Exception as e:
            print("❌ Error fetching profile:", e)
            logging.error(f"Error fetching profile: {e}")
    return None



def get_token_for_symbol(symbol):
    df = instruments_df

    row = df[df["tradingsymbol"] == symbol]
    if row.empty:
        row = df[df["name"] == symbol]

    if not row.empty:
        return int(row["instrument_token"].values[0])
    else:
        print(f"❌ Symbol not found: {symbol}")
        logging.error(f"Symbol not found: {symbol}")
        return None



def get_historical_df(instrument_token, interval, days, user):
    kite = get_kite_client(user)
    now = datetime.datetime.now()
    from_date = (now - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    to_date = now.strftime('%Y-%m-%d')
    data = kite.historical_data(instrument_token, from_date, to_date, interval)
    return pd.DataFrame(data)

def get_entire_quote(symbol, user):
    kite = get_kite_client(user)
    try:
        full_symbol = f"NFO:{symbol}"
        quote = kite.quote([full_symbol])
        return quote[full_symbol]
    except Exception as e:
        print(f"❌{user['user']} | Error fetching quote for {full_symbol}: {e}")
        logging.error(f"{user['user']}  | Error fetching quote for {full_symbol}: {e}")
        return None

def get_quotes(symbol, user):
    kite = get_kite_client(user)
    try:
        full_symbol = f"NFO:{symbol}"
        quote = kite.ltp([full_symbol])
        return quote[full_symbol]['last_price']
    except Exception as e:
        print(f"❌ Error fetching quote for {symbol}: {e}")
        logging.error(f"{user['user']}  | Error fetching quote for {symbol}: {e}")
        return None

def get_quotes_with_retry(symbol, user, retries=3, delay=1):

    for attempt in range(retries):
        ltp = get_quotes(symbol, user)
        if ltp is not None and ltp > 0:
            return ltp
        print(f"⚠️ Attempt {attempt+1}: 503 Error or 0.0 for {symbol}. Retrying...")
        logging.warning(f"{user['user']} | Attempt {attempt+1}: 503 Error or 0.0 for {symbol}. Retrying...")
        time.sleep(delay)
    return None

def get_avgprice_from_positions(tradingsymbol, user):
    kite = get_kite_client(user)
    try:
        positions = kite.positions()["net"]
        for pos in positions:
            if pos["tradingsymbol"] == tradingsymbol:
                avg_price = pos.get("average_price", 0.0)
                qty = pos.get("quantity", 0)

                if qty < 0:
                    logging.info(f"🔃 Detected SELL entry for {tradingsymbol}, quantity {qty}")
                    qty = abs(qty)
                else:
                    logging.info(f"📥 Detected BUY entry for {tradingsymbol}, quantity {qty}")

                return avg_price, qty
    except Exception as e:
        print(f"⚠️ Error fetching LTP from positions {tradingsymbol}: {e}")
        logging.error(f"Error fetching LTP from positions {tradingsymbol}: {e}")
    return None, 0


def place_aggressive_limit_order(tradingsymbol, qty, ordertype, config, user, timeout=5):
    
    print(config)
    if config['REAL_TRADE'].lower() != "yes":
        print(f"⚠️ {config['KEY']} | Simulated Aggressive Limit Order placed (REAL_TRADE is not YES)")
        logging.info(f"⚠️ {config['KEY']} | Simulated Aggressive Limit Order placed (REAL_TRADE is not YES)")
        return "SIMULATED_ORDER", None, 0

    kite = get_kite_client(user)
    tx_type = kite.TRANSACTION_TYPE_SELL if ordertype.upper() == "SELL" else kite.TRANSACTION_TYPE_BUY
    symbol = "NFO:" + tradingsymbol

    filled_qty = 0
    avg_price = 0.0
    order_id = None
    start_time = time.time()

    try:
        while time.time() - start_time < timeout:
            quote = kite.quote(symbol)
            depth = quote[symbol].get("depth", {})

            if ordertype.upper() == "SELL":
                best_price = depth.get("buy", [{}])[0].get("price")
                if best_price is None:
                    best_price = get_quotes_with_retry(tradingsymbol, user)
                limit_price = round(best_price - 0.05, 1)  # slightly aggressive
            else:
                best_price = depth.get("sell", [{}])[0].get("price")
                if best_price is None:
                    best_price = get_quotes_with_retry(tradingsymbol, user)
                limit_price = round(best_price + 0.05, 1)  # slightly aggressive

            if not order_id:  # first time, place order
                order_id = kite.place_order(
                    variety=kite.VARIETY_REGULAR,
                    exchange="NFO",
                    tradingsymbol=tradingsymbol,
                    transaction_type=tx_type,
                    quantity=qty,
                    order_type=kite.ORDER_TYPE_LIMIT,
                    price=limit_price,
                    product=kite.PRODUCT_NRML
                )
            else:  # modify if already placed
                kite.modify_order(
                    variety=kite.VARIETY_REGULAR,
                    order_id=order_id,
                    price=limit_price
                )

            # Check fills
            history = get_historical_order(order_id, user)
            if history:
                filled_qty = sum(o["quantity"] for o in history if o["status"] == "COMPLETE")
                if filled_qty > 0:
                    avg_price = sum(
                        o["average_price"] * o["quantity"] for o in history if o["status"] == "COMPLETE") / filled_qty
                    avg_price = round(avg_price, 2)
                if filled_qty >= int(qty):
                    print(f"✅{config['KEY']} | Aggressive Limit Order Placed: {ordertype} {tradingsymbol} | Order ID: {order_id}")
                    logging.info(f"✅{config['KEY']} | Aggressive Limit Order Placed: {ordertype} {tradingsymbol} | Order ID: {order_id}")
                    return order_id, avg_price, filled_qty

            time.sleep(0.3)  # short polling delay

        # Timeout reached - cancel unfilled qty
        if filled_qty < int(qty) and order_id:
            try:
                kite.cancel_order(variety=kite.VARIETY_REGULAR, order_id=order_id)
                print(f"🛑 {config['KEY']} | Cancelled remaining {qty - filled_qty} qty for {tradingsymbol}")
                logging.info(f"{config['KEY']} | Cancelled remaining {qty - filled_qty} qty for {tradingsymbol}")
            except Exception as ce:
                print(f"⚠{config['KEY']} | Failed to cancel unfilled qty: {ce}")
                logging.error(f"{config['KEY']} | Failed to cancel unfilled qty: {ce}")
                return "SIMULATED_ORDER", None, 0

        print(f"⚠️{config['KEY']} | Timeout: Filled {filled_qty}/{qty} for {tradingsymbol}")
        logging.warning(f"{config['KEY']} | Timeout: Filled {filled_qty}/{qty} for {tradingsymbol}")
        return order_id, avg_price, filled_qty

    except Exception as e:
        print(f"❌ {config['KEY']} | Aggressive Limit Order failed: {e}")
        logging.error(f"{config['KEY']} | Aggressive Limit Order failed: {e}")
        return "SIMULATED_ORDER", None, 0



def get_historical_order(order_id, user):
    kite = get_kite_client(user)
    try:
        orders = kite.order_history(order_id)
        if not orders:
            print(f"⚠️ No order history found for Order ID: {order_id}")
            logging.warning(f"No order history for Order ID: {order_id}")
            return []

        order_details = []
        for order in orders:
            order_details.append({
                "order_id": order.get("order_id", ""),
                "tradingsymbol": order.get("tradingsymbol", ""),
                "transaction_type": order.get("transaction_type", ""),
                "quantity": order.get("quantity", 0),
                "status": order.get("status", ""),
                "average_price": order.get("average_price", 0.0),
                "placed_at": order.get("order_timestamp", "")
            })

        return order_details

    except Exception as e:
        print(f"❌ Error fetching order history for {order_id}: {e}")
        logging.error(f"Error fetching order history for {order_id}: {e}")
        return []

def place_option_market_order(tradingsymbol, qty, ordertype, config, user):
    if config['REAL_TRADE'].lower() != "yes":
        print(f"⚠️ {config['KEY']} | Simulated Market Order placed (REAL_TRADE is not YES)")
        logging.info(f"⚠️ {config['KEY']} | Simulated Market Order placed (REAL_TRADE is not YES)")
        return "SIMULATED_ORDER", None, 0

    kite = get_kite_client(user)
    avg_price = 0.0
    filled_qty = 0
    try:
        tx_type = kite.TRANSACTION_TYPE_SELL if ordertype.upper() == "SELL" else kite.TRANSACTION_TYPE_BUY
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange="NFO",
            tradingsymbol=tradingsymbol,
            transaction_type=tx_type,
            quantity=qty,
            order_type=kite.ORDER_TYPE_MARKET,
            product=kite.PRODUCT_NRML
        )
        history = get_historical_order(order_id, user)
        if history:
            filled_qty = sum(o["quantity"] for o in history if o["status"] == "COMPLETE")
            print(f"✅{config['KEY']} | filled_qty:  {filled_qty} | {tradingsymbol} | Order ID: {order_id}")
            logging.info(f"✅{config['KEY']} | filled_qty:  {filled_qty} | {tradingsymbol} | Order ID: {order_id}")
            if filled_qty > 0:
                avg_price = sum(
                    o["average_price"] * o["quantity"] for o in history if o["status"] == "COMPLETE") / filled_qty
                avg_price = round(avg_price, 2)
                print(f"✅{config['KEY']} | avg_price:  {avg_price} | filled_qty:  {filled_qty} | {tradingsymbol} | Order ID: {order_id}")
                logging.info(f"✅{config['KEY']} | avg_price:  {avg_price} | filled_qty:  {filled_qty} | {tradingsymbol} | Order ID: {order_id}")
            if filled_qty >= int(qty):
                print(f"✅{config['KEY']} | Market Order Placed: {ordertype} {tradingsymbol} | Order ID: {order_id}")
                logging.info(f"✅{config['KEY']} | Market Order Placed: {ordertype} {tradingsymbol} | Order ID: {order_id}")
        return order_id, avg_price, filled_qty
        
    except Exception as e:
        print(f"❌{config['KEY']} | Market Order failed for {tradingsymbol}: {e} | avg_price: {avg_price} | filled_qty: {filled_qty}")
        logging.error(f"{config['KEY']} | Market Order failed for {tradingsymbol}: {e} | avg_price: {avg_price} | filled_qty: {filled_qty}")
        send_telegram_message(f"❌{config['KEY']} | Market Order failed for {tradingsymbol}: {e} | avg_price: {avg_price} | filled_qty: {filled_qty}", user['telegram_chat_id'], user['telegram_token'])
        return "SIMULATED_ORDER", None, 0
    
def place_option_market_order_new(tradingsymbol, qty, ordertype, config, user, max_wait=20):
    
    if config['REAL_TRADE'].lower() != "yes":
        print(f"⚠️ {config['KEY']} | Simulated Market Order placed")
        logging.info(f"{config['KEY']} | Simulated Market Order placed")
        return "SIMULATED_ORDER", 0.0, 0

    kite = get_kite_client(user)

    try:
        tx_type = kite.TRANSACTION_TYPE_SELL if ordertype.upper() == "SELL" else kite.TRANSACTION_TYPE_BUY
        
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange="NFO",
            tradingsymbol=tradingsymbol,
            transaction_type=tx_type,
            quantity=qty,
            order_type=kite.ORDER_TYPE_MARKET,
            product=kite.PRODUCT_NRML
        )

        print(f"🟡 {config['KEY']} | Order Placed | Waiting for completion | ID: {order_id}")
        logging.info(f"{config['KEY']} | Order Placed | ID: {order_id}")

        start_time = time.time()
        filled_qty = 0
        avg_price = 0.0

        while True:
            history = get_historical_order(order_id, user)

            if history:
                completed_orders = [o for o in history if o["status"] == "COMPLETE"]
                filled_qty = sum(o["quantity"] for o in completed_orders)

                if filled_qty > 0:
                    avg_price = round(
                        sum(o["average_price"] * o["quantity"] for o in completed_orders) / filled_qty,
                        2
                    )

                # Fully filled
                if filled_qty >= int(qty):
                    print(f"✅ {config['KEY']} | FULLY FILLED {tradingsymbol} | Qty: {filled_qty} | Avg: {avg_price}")
                    logging.info(f"{config['KEY']} | FULLY FILLED {tradingsymbol}")
                    return order_id, avg_price, filled_qty

            # Timeout protection
            if time.time() - start_time > max_wait:
                print(f"⚠️ {config['KEY']} | Order Timeout | Filled: {filled_qty}/{qty}")
                logging.warning(f"{config['KEY']} | Order Timeout")
                send_telegram_message(
                    f"⚠️ {config['KEY']} | Order Timeout for {tradingsymbol} | Filled {filled_qty}/{qty}", user['telegram_chat_id'], user['telegram_token']
                )
                return order_id, avg_price, filled_qty

            time.sleep(1)  # Wait 1 second before checking again

    except Exception as e:
        logging.error(f"{config['KEY']} | Market Order failed for {tradingsymbol}: {str(e)}")
        send_telegram_message(
            f"❌ {config['KEY']} | Market Order failed for {tradingsymbol}: {str(e)}",user['telegram_chat_id'], user['telegram_token']
        )
        return None, 0.0, 0
    
def place_option_market_order_strict_one(
        tradingsymbol,
        qty,
        ordertype,
        config,
        user,
        max_wait=15,
        max_attempts=3):

    if config['REAL_TRADE'].lower() != "yes":
        logging.info(f"{config['KEY']} | Simulated Order")
        return "SIMULATED_ORDER", 0.0, 0

    kite = get_kite_client(user)

    required_qty = int(qty)
    total_filled = 0
    total_value = 0.0
    attempt = 0

    tx_type = kite.TRANSACTION_TYPE_SELL if ordertype.upper() == "SELL" \
        else kite.TRANSACTION_TYPE_BUY

    try:

        while total_filled < required_qty and attempt < max_attempts:

            remaining_qty = required_qty - total_filled
            order_id = kite.place_order(
                variety=kite.VARIETY_REGULAR,
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=tx_type,
                quantity=remaining_qty,
                order_type=kite.ORDER_TYPE_MARKET,
                product=kite.PRODUCT_NRML
            )

            logging.info(f"{config['KEY']} | Attempt {attempt+1} | "
                         f"Placed {remaining_qty} | ID {order_id}")

            start_time = time.time()
            filled_this_round = 0
            avg_price = 0.0

            # -------- WAIT FOR THIS ORDER TO COMPLETE --------
            while True:
                history = get_historical_order(order_id, user)

                if history:
                    completed = [
                        o for o in history if o["status"] == "COMPLETE"
                    ]

                    filled_this_round = sum(o["quantity"] for o in completed)
                    if filled_this_round > 0:
                        avg_price = round(
                            sum(o["average_price"] * o["quantity"]
                                for o in completed) / filled_this_round,
                            2
                        )

                # EXACT MATCH REQUIRED
                if filled_this_round == remaining_qty:
                    break

                # Timeout for this attempt
                if time.time() - start_time > max_wait:
                    logging.warning(f"{config['KEY']} | Timeout attempt {attempt+1}")
                    break
                time.sleep(1)

            # accumulate
            total_filled += filled_this_round
            total_value += filled_this_round * avg_price

            # if exact qty achieved → SUCCESS
            if total_filled == required_qty:
                final_avg = round(total_value / total_filled, 2)
                logging.info(f"{config['KEY']} | FULLY FILLED | Qty {total_filled}")
                return order_id, final_avg, total_filled

            attempt += 1
            time.sleep(1)

        # ==========================
        # AFTER ALL ATTEMPTS FAILED
        # ==========================

        if total_filled > 0:
            logging.error(f"{config['KEY']} | Partial fill after retries. "
                          f"Exiting {total_filled}")
            
            reverse_tx = kite.TRANSACTION_TYPE_BUY \
                if ordertype.upper() == "SELL" \
                else kite.TRANSACTION_TYPE_SELL
            
            kite.place_order(
                variety=kite.VARIETY_REGULAR,
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=reverse_tx,
                quantity=total_filled,
                order_type=kite.ORDER_TYPE_MARKET,
                product=kite.PRODUCT_NRML
            )
            send_telegram_message(
                f"❌ {config['KEY']} | Partial fill detected.\n"
                f"Exited {total_filled} qty.",user['telegram_chat_id'], user['telegram_token'])
        return None, 0.0, 0

    except Exception as e:
        logging.error(f"{config['KEY']} | Order failed: {str(e)}")

        send_telegram_message(
            f"❌ {config['KEY']} | Order failed: {str(e)}",user['telegram_chat_id'], user['telegram_token']
        )
        return None, 0.0, 0


#Only limit order 
def place_option_hybrid_order_old(tradingsymbol, qty, ordertype,config , user):

    return place_aggressive_limit_order(tradingsymbol, qty, ordertype, config, user)


#Hybrid order: Try market first, then aggressive limit if not filled
def place_option_hybrid_order(tradingsymbol, qty, ordertype,config , user):
    
    # order_id, avg_price, filled_qty = place_option_market_order(tradingsymbol, qty, ordertype,config , user)
    order_id, avg_price, filled_qty = place_option_market_order_strict_isolated(tradingsymbol, qty, ordertype,config , user)
    if order_id and order_id != "SIMULATED_ORDER":
        return order_id, avg_price, filled_qty
    else:
        logging.info(f"⚠️{config['KEY']} | market order not filled for {tradingsymbol}, {order_id}, {avg_price}, {filled_qty}")
        send_telegram_message(f"⚠️{config['KEY']} | market order not filled for {tradingsymbol}, {order_id}, {avg_price}, {filled_qty}",user['telegram_chat_id'], user['telegram_token'])
        # order_id, avg_price, filled_qty = place_aggressive_limit_order(tradingsymbol, qty, ordertype, config, user)
        return order_id, avg_price, filled_qty
   


def place_basket_order(orders, config, user):

    results = []
    for order in orders:
        tradingsymbol = order['tradingsymbol']
        qty = order['quantity']
        ordertype = order['ordertype']
        result = place_option_hybrid_order(tradingsymbol, qty, ordertype, config, user)
        results.append({
            "tradingsymbol": tradingsymbol,
            "quantity": qty,
            "ordertype": ordertype,
            "result": result
        })
    return results


def check_symbol_in_positions(tradingsymbol, user):
    kite = get_kite_client(user)
    try:
        positions = kite.positions()["net"]
        print(f"Checking positions for {tradingsymbol} - Total positions: {len(positions)}")
        print(f"Positions data: {positions}")
        for pos in positions:
            if pos["tradingsymbol"] == tradingsymbol and pos["quantity"] != 0:
                return True, pos["quantity"]
        return False, 0
    except Exception as e:
        print(f"❌ Error checking positions for {tradingsymbol}: {e}")
        logging.error(f"Error checking positions for {tradingsymbol}: {e}")
        return False,  0
    
def get_current_position_qty(kite, tradingsymbol):
    """
    Returns net position qty for given symbol.
    Positive = long
    Negative = short
    """
    positions = kite.positions()
    for p in positions["net"]:
        if p["tradingsymbol"] == tradingsymbol:
            return p["quantity"]
    return 0


def place_option_market_order_bulletproof(
        tradingsymbol,
        qty,
        ordertype,
        config,
        user,
        max_wait=15,
        max_attempts=3):

    if config['REAL_TRADE'].lower() != "yes":
        return "SIMULATED_ORDER", 0.0, 0

    kite = get_kite_client(user)

    required_qty = int(qty)
    attempt = 0
    total_value = 0.0

    direction = 1 if ordertype.upper() == "BUY" else -1
    tx_type = kite.TRANSACTION_TYPE_BUY if direction == 1 \
        else kite.TRANSACTION_TYPE_SELL

    try:

        initial_position = get_current_position_qty(kite, tradingsymbol)

        while attempt < max_attempts:

            # -----------------------------
            # CHECK ACTUAL POSITION FIRST
            # -----------------------------
            current_position = get_current_position_qty(kite, tradingsymbol)
            actual_filled = abs(current_position - initial_position)

            if actual_filled == required_qty:
                avg_price = 0.0  # optional: compute from order history
                logging.info(f"{config['KEY']} | Already fully filled via position check")
                return None, avg_price, required_qty

            remaining_qty = required_qty - actual_filled

            if remaining_qty <= 0:
                # Defensive guard
                return None, 0.0, required_qty

            # -----------------------------
            # PLACE ORDER FOR REMAINING ONLY
            # -----------------------------
            order_id = kite.place_order(
                variety=kite.VARIETY_REGULAR,
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=tx_type,
                quantity=remaining_qty,
                order_type=kite.ORDER_TYPE_MARKET,
                product=kite.PRODUCT_NRML
            )

            logging.info(f"{config['KEY']} | Attempt {attempt+1} | "
                         f"Placed {remaining_qty}")

            start_time = time.time()

            while True:

                current_position = get_current_position_qty(kite, tradingsymbol)
                actual_filled = abs(current_position - initial_position)

                if actual_filled == required_qty:
                    logging.info(f"{config['KEY']} | Fully filled confirmed by position")
                    return order_id, 0.0, required_qty

                if time.time() - start_time > max_wait:
                    logging.warning(f"{config['KEY']} | Timeout on attempt {attempt+1}")
                    break

                time.sleep(1)

            attempt += 1
            time.sleep(1)

        # --------------------------------
        # AFTER ALL ATTEMPTS
        # --------------------------------
        current_position = get_current_position_qty(kite, tradingsymbol)
        actual_filled = abs(current_position - initial_position)

        if actual_filled > 0:
            logging.error(f"{config['KEY']} | Partial fill detected. Squaring off {actual_filled}")

            reverse_tx = kite.TRANSACTION_TYPE_BUY if direction == -1 \
                else kite.TRANSACTION_TYPE_SELL

            kite.place_order(
                variety=kite.VARIETY_REGULAR,
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=reverse_tx,
                quantity=actual_filled,
                order_type=kite.ORDER_TYPE_MARKET,
                product=kite.PRODUCT_NRML
            )

        return None, 0.0, 0

    except Exception as e:
        logging.error(f"{config['KEY']} | Order failed: {str(e)}")
        return None, 0.0, 0

# Using kite.orders() to get fill details instead of positions (more direct)

def get_order_fill_details(kite, order_id):
    """
    Returns (filled_qty, avg_price, status)
    from kite.orders() for specific order_id
    """
    orders = kite.orders()
    for o in orders:
        if o["order_id"] == order_id:
            return (
                o.get("filled_quantity", 0),
                o.get("average_price", 0.0),
                o.get("status", "")
            )
    return 0, 0.0, "UNKNOWN"


def place_option_market_order_isolated(
        tradingsymbol,
        qty,
        ordertype,
        config,
        user,
        max_wait=15,
        max_attempts=3):

    if config['REAL_TRADE'].lower() != "yes":
        logging.info(f"{config['KEY']} | Simulated order")
        return "SIMULATED_ORDER", 0.0, 0

    kite = get_kite_client(user)

    required_qty = int(qty)
    total_filled = 0
    total_value = 0.0
    attempt = 0

    tx_type = kite.TRANSACTION_TYPE_SELL \
        if ordertype.upper() == "SELL" \
        else kite.TRANSACTION_TYPE_BUY

    try:

        while total_filled < required_qty and attempt < max_attempts:

            remaining_qty = required_qty - total_filled

            order_id = kite.place_order(
                variety=kite.VARIETY_REGULAR,
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=tx_type,
                quantity=remaining_qty,
                order_type=kite.ORDER_TYPE_MARKET,
                product=kite.PRODUCT_NRML
            )

            logging.info(f"{config['KEY']} | Attempt {attempt+1} | "
                         f"Placed {remaining_qty} | ID {order_id}")

            start_time = time.time()
            filled_this_round = 0
            avg_price = 0.0

            while True:

                filled_this_round, avg_price, status = \
                    get_order_fill_details(kite, order_id)

                # Exact match required
                if filled_this_round == remaining_qty:
                    break

                # If cancelled/rejected → stop this attempt
                if status in ["REJECTED", "CANCELLED"]:
                    logging.error(f"{config['KEY']} | OrderID {order_id} | Order {status}")
                    send_telegram_message(f"{config['KEY']} | OrderID {order_id} | Order {status}", user['telegram_chat_id'], user['telegram_token'])
                    break

                if time.time() - start_time > max_wait:
                    logging.warning(f"{config['KEY']} | Timeout attempt {attempt+1}")
                    break

                time.sleep(1)

            # accumulate safe fills
            total_filled += filled_this_round
            total_value += filled_this_round * avg_price

            # success condition
            if total_filled == required_qty:
                final_avg = round(total_value / total_filled, 2)
                logging.info(f"{config['KEY']} | FULLY FILLED | Qty {total_filled}")
                return order_id, final_avg, total_filled

            attempt += 1
            time.sleep(1)

        # ============================
        # AFTER ALL ATTEMPTS FAILED
        # ============================
        if total_filled > 0:
            logging.error(f"{config['KEY']} | Partial fill. "
                          f"Exiting {total_filled}")

            reverse_tx = kite.TRANSACTION_TYPE_BUY \
                if ordertype.upper() == "SELL" \
                else kite.TRANSACTION_TYPE_SELL

            exit_order_id = kite.place_order(
                variety=kite.VARIETY_REGULAR,
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=reverse_tx,
                quantity=total_filled,
                order_type=kite.ORDER_TYPE_MARKET,
                product=kite.PRODUCT_NRML
            )

            logging.info(f"{config['KEY']} | Exit Order ID {exit_order_id}")

        return None, 0.0, 0

    except Exception as e:
        logging.error(f"{config['KEY']} | OrderID {order_id} | Order failed: {str(e)}")
        send_telegram_message(f"{config['KEY']} | OrderID {order_id} | Order failed: {str(e)}",user['telegram_chat_id'], user['telegram_token'])
        return None, 0.0, 0
# 


# ==========================================
# Helper: Get Order Details by Order ID
# ==========================================
def get_order_fill_details(kite, order_id):
    """
    Returns:
        filled_qty (int),
        avg_price (float),
        status (str),
        pending_qty (int)
    """
    try:
        orders = kite.orders()
        for o in orders:
            if o["order_id"] == order_id:
                return (
                    o.get("filled_quantity", 0),
                    o.get("average_price", 0.0),
                    o.get("status", ""),
                    o.get("pending_quantity", 0)
                )
    except Exception as e:
        logging.warning(f"Order fetch failed for {order_id}: {str(e)}")

    return 0, 0.0, "UNKNOWN", 0


# ==========================================
# Strict All-Or-Nothing Market Order Engine
# ==========================================
def place_option_market_order_strict_isolated(
        tradingsymbol,
        qty,
        ordertype,
        config,
        user,
        max_wait=15,
        max_attempts=3):

    if config['REAL_TRADE'].lower() != "yes":
        logging.info(f"{config['KEY']} | Simulated Order")
        return "SIMULATED_ORDER", None, 0

    kite = get_kite_client(user)

    required_qty = int(qty)
    total_filled = 0
    total_value = 0.0
    attempt = 0

    tx_type = (
        kite.TRANSACTION_TYPE_SELL
        if ordertype.upper() == "SELL"
        else kite.TRANSACTION_TYPE_BUY
    )

    try:

        while total_filled < required_qty and attempt < max_attempts:

            remaining_qty = required_qty - total_filled

            order_id = kite.place_order(
                variety=kite.VARIETY_REGULAR,
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=tx_type,
                quantity=remaining_qty,
                order_type=kite.ORDER_TYPE_MARKET,
                product=kite.PRODUCT_NRML
            )

            logging.info(
                f"{config['KEY']} | Attempt {attempt+1} | "
                f"Placed {remaining_qty} | Order ID {order_id}"
            )

            start_time = time.time()
            filled_this_round = 0
            avg_price = 0.0

            # ------------------------------
            # WAIT FOR ORDER COMPLETION
            # ------------------------------
            while True:

                filled_this_round, avg_price, status, pending_qty = get_order_fill_details(kite, order_id)

                # 1️⃣ SUCCESS CONDITION
                if status == "COMPLETE":
                    if filled_this_round == remaining_qty:
                        break
                    else:
                        logging.error(
                            f"{config['KEY']} | COMPLETE but qty mismatch. "
                            f"Filled {filled_this_round}, Expected {remaining_qty}"
                        )
                        break

                # 2️⃣ TERMINAL FAILURE
                if status in ["REJECTED", "CANCELLED"]:
                    logging.error(
                        f"{config['KEY']} | Order {status}"
                    )
                    break

                # 3️⃣ STILL ACTIVE → WAIT
                # (OPEN, VALIDATION PENDING, TRIGGER PENDING, etc.)

                if time.time() - start_time > max_wait:
                    logging.warning(
                        f"{config['KEY']} | Timeout attempt {attempt+1}"
                    )
                    break

                time.sleep(1)

            # Accumulate safely
            total_filled += filled_this_round
            total_value += filled_this_round * avg_price

            # SUCCESS CHECK (STRICT)
            if total_filled == required_qty:
                final_avg = round(total_value / total_filled, 2)
                logging.info(
                    f"{config['KEY']} | FULLY FILLED | Qty {total_filled}"
                )
                return order_id, final_avg, total_filled

            attempt += 1
            time.sleep(1)

        # ==================================
        # AFTER ALL ATTEMPTS FAILED
        # ==================================
        if total_filled > 0:
            logging.error(
                f"{config['KEY']} | Partial fill after retries. "
                f"Exiting {total_filled}"
            )

            reverse_tx = (
                kite.TRANSACTION_TYPE_BUY
                if ordertype.upper() == "SELL"
                else kite.TRANSACTION_TYPE_SELL
            )

            exit_order_id = kite.place_order(
                variety=kite.VARIETY_REGULAR,
                exchange="NFO",
                tradingsymbol=tradingsymbol,
                transaction_type=reverse_tx,
                quantity=total_filled,
                order_type=kite.ORDER_TYPE_MARKET,
                product=kite.PRODUCT_NRML
            )

            logging.info(f"{config['KEY']} | Exit Order Placed | ID {exit_order_id}")

            send_telegram_message(
                f"❌ {config['KEY']} | Partial execution detected.\n"
                f"Exited {total_filled} qty.", user['telegram_chat_id'], user['telegram_token'])

        return None, 0.0, 0

    except Exception as e:
        logging.error( f"{config['KEY']} | Market Order Failed: {str(e)}")
        send_telegram_message(f"❌ {config['KEY']} | Market Order Failed:\n{str(e)}",user['telegram_chat_id'], user['telegram_token'] )

        return None, 0.0, 0


def place_robust_limit_order(tradingsymbol, qty, ordertype, config, user, action="ENTRY", timeout=5):
    """
    Balanced Price Chaser: 5s timeout, 0.5s sleep, max 3 modifications.
    Tracks and logs slippage against the initial market price.
    """
    if config.get('REAL_TRADE', '').lower() != "yes":
        print(f"📉{config['KEY']} | SIMULATED {action}: {ordertype} {qty} {tradingsymbol}")
        return "SIMULATED_ORDER", 0, 0

    logging.info(f"{config['KEY']} | Executing {action} for {tradingsymbol} | Qty: {qty}...")
    kite = get_kite_client(user)
    tx_type = kite.TRANSACTION_TYPE_SELL if ordertype.upper() == "SELL" else kite.TRANSACTION_TYPE_BUY
    
    # --- CAPTURE INITIAL LTP FOR SLIPPAGE ---
    initial_ltp = get_quotes_with_retry(tradingsymbol, user) or 0
    
    order_id = None
    start_time = time.time()
    mod_count = 0 
    current_ltp = initial_ltp
    mod_limit = 3
    sleep_interval = 0.5

    try:
        while (time.time() - start_time) < timeout:
            try:
                quote_resp = get_entire_quote(tradingsymbol, user)
                current_ltp = quote_resp.get("last_price", current_ltp)
                depth = quote_resp.get("depth", {})
                
                buy_list = depth.get("buy", [])
                sell_list = depth.get("sell", [])
                best_bid = buy_list[0].get("price", 0) if buy_list else 0
                best_ask = sell_list[0].get("price", 0) if sell_list else 0
            except Exception as e:
                logging.error(f"Depth fetch error: {e}")
                best_bid = best_ask = 0

            # Determine Limit Price (Tick size compliant 0.05)
            if ordertype.upper() == "SELL":
                raw_price = best_bid - 0.20 if best_bid > 0 else current_ltp - 0.20
            else:
                raw_price = best_ask + 0.20 if best_ask > 0 else current_ltp + 0.20
            
            limit_price = round(raw_price / 0.05) * 0.05

            if not order_id:
                order_id = kite.place_order(
                    variety=kite.VARIETY_REGULAR, exchange="NFO",
                    tradingsymbol=tradingsymbol, transaction_type=tx_type,
                    quantity=int(qty), order_type=kite.ORDER_TYPE_LIMIT,
                    price=limit_price, product=kite.PRODUCT_NRML
                )
                logging.info(f"Placed {ordertype} {order_id} at ₹{limit_price}")
            else:
                hist = kite.order_history(order_id)
                last_row = hist[-1]
                if last_row['status'] in ["COMPLETE", "REJECTED", "CANCELLED"]:
                    break 
                
                if abs(last_row['price'] - limit_price) >= 0.05 and mod_count < mod_limit:
                    try:
                        kite.modify_order(variety=kite.VARIETY_REGULAR, order_id=order_id, price=limit_price)
                        mod_count += 1
                        logging.info(f"Mod {mod_count}/{mod_limit}: New Price ₹{limit_price}")
                    except: pass 
            
            time.sleep(sleep_interval)

        # Final Cleanup
        final_row = kite.order_history(order_id)[-1]
        if final_row['status'] not in ["COMPLETE", "REJECTED", "CANCELLED"]:
            try:
                kite.cancel_order(variety=kite.VARIETY_REGULAR, order_id=order_id)
                time.sleep(0.3)
                final_row = kite.order_history(order_id)[-1]
            except: pass

        avg_price = final_row.get('average_price', 0.0)
        filled_qty = final_row.get('filled_quantity', 0)

        # --- LOG SLIPPAGE SUMMARY ---
        if filled_qty > 0 and initial_ltp > 0:
            slippage = avg_price - initial_ltp if ordertype.upper() == "BUY" else initial_ltp - avg_price
            logging.info(f"📊 SLIPPAGE SUMMARY | Symbol: {tradingsymbol} | Initial LTP: {initial_ltp} | Avg Price: {avg_price} | Slippage: {round(slippage, 2)}")

        return order_id, avg_price, filled_qty

    except Exception as e:
        logging.error(f"Execution Error: {e}")
        return None, 0, 0
    


def simulate_robust_limit_order(tradingsymbol, qty, ordertype, config, user, action="ENTRY", timeout=5):
    """
    STRICT REPLICA: Removes Kite placement/mod/cancel. 
    Maintains all calculation logic, offsets, and loop timing.
    """
    logging.info(f"🧪 SIMULATING {action} logic for {tradingsymbol}...")
    
    # --- CAPTURE INITIAL LTP FOR SLIPPAGE ---
    initial_ltp = get_quotes_with_retry(tradingsymbol, user) or 0
    
    start_time = time.time()
    mod_count = 0 
    current_ltp = initial_ltp
    mod_limit = 3
    sleep_interval = 0.5
    
    # Local trackers to replace kite.order_history and kite.place_order
    current_sim_price = 0.0
    is_placed = False 

    try:
        while (time.time() - start_time) < timeout:
            try:
                quote_resp = get_entire_quote(tradingsymbol, user)
                current_ltp = quote_resp.get("last_price", current_ltp)
                depth = quote_resp.get("depth", {})
                
                buy_list = depth.get("buy", [])
                sell_list = depth.get("sell", [])
                best_bid = buy_list[0].get("price", 0) if buy_list else 0
                best_ask = sell_list[0].get("price", 0) if sell_list else 0
            except Exception as e:
                logging.error(f"Depth fetch error: {e}")
                best_bid = best_ask = 0

            # Determine Limit Price (Logic Unchanged)
            if ordertype.upper() == "SELL":
                raw_price = best_bid - 0.20 if best_bid > 0 else current_ltp - 0.20
            else:
                raw_price = best_ask + 0.20 if best_ask > 0 else current_ltp + 0.20
            
            limit_price = round(raw_price / 0.05) * 0.05

            if not is_placed:
                # Simulated Placement
                current_sim_price = limit_price
                is_placed = True
                logging.info(f"Simulated {ordertype} Start: ₹{limit_price}")
            else:
                # Simulated Modification Logic (Checks price diff and mod limit)
                if abs(current_sim_price - limit_price) >= 0.05 and mod_count < mod_limit:
                    current_sim_price = limit_price
                    mod_count += 1
                    logging.info(f"Sim Mod {mod_count}/{mod_limit}: New Price ₹{limit_price}")
            
            time.sleep(sleep_interval)

        # Final Summary (Replica of your cleanup/slippage logic)
        avg_price = current_sim_price
        filled_qty = qty # Simulated as fully filled at last known price

        if filled_qty > 0 and initial_ltp > 0:
            slippage = avg_price - initial_ltp if ordertype.upper() == "BUY" else initial_ltp - avg_price
            logging.info(f"📊 SIM SLIPPAGE SUMMARY | Symbol: {tradingsymbol} | Initial LTP: {initial_ltp} | Avg Price: {avg_price} | Slippage: {round(slippage, 2)}")

        return "SIMULATED_ORDER", avg_price, filled_qty

    except Exception as e:
        logging.error(f"Simulation Error: {e}")
        return None, 0, 0
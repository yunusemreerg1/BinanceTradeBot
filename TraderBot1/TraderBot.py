from binance.client import Client
import time
import random
import numpy as np
import pandas as pd

#binance Api key
api_key = ""
api_secret = ""

# Binance istemcisi
client = Client(api_key, api_secret)

# Botun başlangıç değerleri
free_balance = 1000.0  # Kullanılabilir bakiye
used_balance = 0.0  # Kullanılan bakiye
total_balance = 1000.0  # Toplam bakiye
positions = []  # Açık pozisyonlar
max_total_position_size = 200  # Aynı anda açık pozisyonların toplam büyüklüğü (USD)
max_open_positions = 3  # Aynı anda açılacak maksimum işlem sayısı


# RSI hesaplama fonksiyonu (Pandas ile)
def calculate_rsi(symbol="ETHUSDT", interval="1h", period=14):
    klines = client.get_historical_klines(symbol, interval, f"{period} hours ago UTC")
    closes = [float(kline[4]) for kline in klines]  # Kapanış fiyatları
    df = pd.DataFrame(closes, columns=['close'])
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]  # last RSI balance


# Hareketli Ortalama (MA) hesaplama fonksiyonu (Pandas ile)
def calculate_moving_average(symbol="ETHUSDT", interval="1h", short_period=50, long_period=200):
    klines = client.get_historical_klines(symbol, interval, f"{long_period} hours ago UTC")
    closes = [float(kline[4]) for kline in klines]  # Kapanış fiyatları
    df = pd.DataFrame(closes, columns=['close'])

    short_ma = df['close'].rolling(window=short_period).mean().iloc[-1]  # Kısa vadeli hareketli ortalama
    long_ma = df['close'].rolling(window=long_period).mean().iloc[-1]  # Uzun vadeli hareketli ortalama
    return short_ma, long_ma


# MACD calculation function  by pandas
def calculate_macd(symbol="ETHUSDT", interval="1h", fast_period=12, slow_period=26, signal_period=9):
    klines = client.get_historical_klines(symbol, interval, f"{slow_period} hours ago UTC")
    closes = [float(kline[4]) for kline in klines]
    df = pd.DataFrame(closes, columns=['close'])

    short_ema = df['close'].ewm(span=fast_period, adjust=False).mean()
    long_ema = df['close'].ewm(span=slow_period, adjust=False).mean()
    macd = short_ema - long_ema
    signal = macd.ewm(span=signal_period, adjust=False).mean()

    return macd.iloc[-1], signal.iloc[-1]


# İşlem açma fonksiyonu
def execute_trade(price, trade_type, leverage=1):
    global free_balance, used_balance, positions, total_balance

    # Aynı anda açık pozisyonların toplam büyüklüğünü kontrol et
    total_position_size = sum([position["amount"] for position in positions])
    if total_position_size >= max_total_position_size:
        print("Maksimum pozisyon büyüklüğüne ulaşıldı. Yeni işlem açılamaz.")
        return


    # Limiting the size of each position
    trade_amount = min(free_balance * 0.1,
                       max_total_position_size - total_position_size)  # %10'luk risk ve toplam pozisyon sınırı
    if trade_amount < 10:  # Minimum işlem tutarı
        print("Yetersiz bakiye, işlem yapılamıyor!")
        return

    # Maximum number of open positions control
    if len(positions) >= max_open_positions:
        print("Maksimum açık pozisyon sayısına ulaşıldı. Yeni işlem açılmayacak.")
        return


    if leverage == 1:
        # Spot tradeing
        print(f"Spot işlem açılıyor! Fiyat: {price}")
        free_balance -= trade_amount
        used_balance += trade_amount
        position_id = len(positions) + 1  # Alış işlemi için benzersiz ID
        positions.append({
            "id": position_id,
            "type": trade_type,
            "price": price,
            "amount": trade_amount,
            "leverage": leverage,
        })
        print(f"Spot işlem başarıyla açıldı! Fiyat: {price}, Kullanılabilir Bakiye: {free_balance:.2f}")
        return

    #min leverage
    if leverage < 5:
        leverage = 5

    # LEVERAGE positions
    liquidation_price = calculate_liquidation_price(price, leverage, trade_type)
    print(f"Likidasyon Seviyesi: {liquidation_price:.2f}")
    if (trade_type == "long" and liquidation_price < 0) or (trade_type == "short" and liquidation_price > 2 * price):
        print("Likidasyon riski yüksek, işlem yapılmıyor!")
        return

    # Pozisyon oluşturma
    trade_value = trade_amount * leverage
    position_id = len(positions) + 1  # Assigning a unique ID to each position
    positions.append({
        "id": position_id,
        "type": trade_type,
        "price": price,
        "amount": trade_amount,
        "leverage": leverage,
        "liquidation_price": liquidation_price,
    })

    free_balance -= trade_amount
    used_balance += trade_amount

    print(f"{trade_type.capitalize()} işlem açıldı! Fiyat: {price}, Kaldıraç: {leverage}x")
    print(f"Kullanılan Bakiye: {used_balance:.2f}, Kullanılabilir Bakiye: {free_balance:.2f}")
    print(f"Alınan ETH Fiyatı: {price:.2f} USD, İşlem Tutarı: {trade_amount:.2f} USD")


# Reporting function on trading decisions and why not buying or selling
def decide_trade_action(rsi, macd, signal, short_ma, long_ma):
    trade_type = None
    reasons = []

    # Alış sinyali (long)
    if rsi < 30 and macd > signal and short_ma > long_ma:
        trade_type = "long"
    else:
        if not (rsi < 30):
            reasons.append(f"RSI ({rsi:.2f}) 30'dan küçük değil.")
        if not (macd > signal):
            reasons.append(f"MACD ({macd:.2f}) Signal'in üstünde değil.")
        if not (short_ma > long_ma):
            reasons.append(f"Kısa vadeli MA ({short_ma:.2f}) uzun vadeli MA'dan ({long_ma:.2f}) büyük değil.")

    # short
    if rsi > 70 and macd < signal and short_ma < long_ma:
        trade_type = "short"
    else:
        if not (rsi > 70):
            reasons.append(f"RSI ({rsi:.2f}) 70'ten büyük değil.")
        if not (macd < signal):
            reasons.append(f"MACD ({macd:.2f}) Signal'in altında değil.")
        if not (short_ma < long_ma):
            reasons.append(f"Kısa vadeli MA ({short_ma:.2f}) uzun vadeli MA'dan ({long_ma:.2f}) küçük değil.")

    return trade_type, reasons


# Description
def display_summary():
    global free_balance, used_balance, total_balance, positions

    print("\n--- Bot Durumu ---")
    print(f"Toplam Bakiye: {total_balance:.2f} USD")
    print(f"Kullanılabilir Bakiye: {free_balance:.2f} USD")
    print(f"Kullanılan Bakiye: {used_balance:.2f} USD")
    print(f"Açık Pozisyonlar: {len(positions)}")

    if len(positions) > 0:
        for position in positions:
            print(f"Pozisyon {position['id']}: {position['type']} - Fiyat: {position['price']:.2f} USD - Miktar: {position['amount']:.2f} ETH")


# Main Loop
def run_bot():
    global free_balance, used_balance, total_balance

    start_time = time.time()
    while time.time() - start_time < 3600:  # 1 hour work time
        if total_balance <= 0:
            print("Bakiye sıfırlandı, bot durduruldu!")
            break

        current_price = float(client.get_symbol_ticker(symbol="ETHUSDT")['price'])
        print(f"ETH/USDT Fiyatı: {current_price:.2f}")

        # Analys
        rsi = calculate_rsi()
        short_ma, long_ma = calculate_moving_average()
        macd, signal = calculate_macd()

        # Make transaction decision
        trade_type, reasons = decide_trade_action(rsi, macd, signal, short_ma, long_ma)

        if trade_type:
            leverage = random.randint(5, 10)  # Kaldıraç en az 5x olacak
            execute_trade(current_price, trade_type, leverage)
        else:
            if reasons:
                print(f"İşlem yapılmadı çünkü:")
                for reason in reasons:
                    print(f" - {reason}")
            else:
                print("İşlem yapılmadı, ancak herhangi bir neden belirtilmedi.")

        # Botun durumunu göster
        display_summary()  # Bu fonksiyonu burada çağırıyoruz
        time.sleep(5)  # 5 saniye bekleyin



run_bot()
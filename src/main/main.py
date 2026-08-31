import time
from ibapi.scanner import ScannerSubscription
from ibapi.tag_value import TagValue

from src.main.IBClient.ohlc.Data import IBConnection
from src.main.IBClient.Scanner.ScannerManager import ScannerManager
from src.main.IBClient.PositionManager import PositionManager, Notifier
from src.main.IBClient.Strategy.Strategy import LONG10MIN, LONG10MIN2

#  SETTINGS
HOST      = "127.0.0.1"
PORT      = 7496      # real
# PORT    = 7497        # paper trading
CLIENT_ID = 1

MAX_POSITIONS  = 5
RISK_PER_TRADE = 1000   # $ per position
TP_PCT         = 0.20   # tp
SL_PCT         = 0.05   # sl
LOOP_INTERVAL  = 10    

# Notifier
notifier = Notifier(
    email_from="",
    email_to="",
    email_password=""
)

def main():
    # Broker connection
    connection = IBConnection()
    connection.connect(HOST, PORT, CLIENT_ID)
    connection.start()
    time.sleep(2)

    # PositionManager for both strategys
    pm = PositionManager(
        max_positions=MAX_POSITIONS,
        risk_per_trade=RISK_PER_TRADE,
        notifier=notifier
    )

    #  ScannerManager 1 — LONG10MIN (9:40-9:50 ET)
    #    Premarket volume máx 1M
    manager = ScannerManager(connection, pm) # default 1M de PMVol 

    #  ScannerManager 2 — LONG10MIN2 (9:30-9:40 ET)
    #    Premarket volume máx 300k
    manager2 = ScannerManager(connection, pm)
    manager2.MAX_PREMARKET_VOLUME = 300_000 

    #  Recover open positions if the bot restarted
    connection.request_existing_positions(manager)
    time.sleep(2)

    # Scanner 1
    scanner = manager.new_scanner()
    scan = ScannerSubscription()
    scan.instrument    = "STK"
    scan.locationCode  = "STK.US.MAJOR"
    scan.scanCode      = "TOP_PERC_GAIN"
    scan.marketCapBelow = 2e8

    filters = [
        TagValue("changePercAbove", "5"),   # gap mínimo 5%
    ]
    scanner.init_scanner(scan, filters)

    # Scanner 2
    scanner2 = manager2.new_scanner()
    scan2 = ScannerSubscription()
    scan2.instrument    = "STK"
    scan2.locationCode  = "STK.US.MAJOR"
    scan2.scanCode      = "TOP_PERC_GAIN"
    scan2.marketCapBelow = 2e8
    scan2.abovePrice    = 1  # min

    filters2 = []  
    scanner2.init_scanner(scan2, filters2)

    print("[BOT] Arrancado. Esperando datos del scanner...")
    time.sleep(10)
    
    # MAIN LOOP
    while True:
        # STRATEGY 2: LONG10MIN2 (9:30-9:40 ET)
        for symbol, ohlc in list(manager2.ohlc_by_symbol.items()):
            if len(ohlc.data) < 5:
             continue
            if LONG10MIN2(ohlc).check():
             pm.try_enter(ohlc, tp_pct=TP_PCT, sl_pct=SL_PCT)

        # STRATEGY 1: LONG10MIN (9:40-9:50 ET)
        for symbol, ohlc in list(manager.ohlc_by_symbol.items()):
            if len(ohlc.data) < 5:
             continue
            if LONG10MIN(ohlc).check():
             pm.try_enter(ohlc, tp_pct=TP_PCT, sl_pct=SL_PCT)

        pm.status()
        time.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    main()

import time
from ibapi.scanner import ScannerSubscription
from ibapi.tag_value import TagValue

from src.main.IBClient.ohlc.Data import IBConnection
from src.main.IBClient.Scanner.ScannerManager import ScannerManager
from src.main.IBClient.PositionManager import PositionManager, Notifier
from src.main.IBClient.Strategy.Strategy import LONG10MIN, LONG10MIN2

# ─────────────────────────────────────────────
#  CONFIGURACIÓN
# ─────────────────────────────────────────────
HOST      = "127.0.0.1"
PORT      = 7496      # real
# PORT    = 7497        # paper trading
CLIENT_ID = 1

MAX_POSITIONS  = 5
RISK_PER_TRADE = 1000  # $ por posición
TP_PCT         = 0.20   # 20%
SL_PCT         = 0.05   # 5%
LOOP_INTERVAL  = 10     # segundos entre comprobaciones de señal

# Notificador — deja vacío para solo consola
notifier = Notifier(
    email_from="",
    email_to="",
    email_password=""
)

# ─────────────────────────────────────────────
#  ARRANQUE
# ─────────────────────────────────────────────
def main():
    # 1. Conexión única al broker
    connection = IBConnection()
    connection.connect(HOST, PORT, CLIENT_ID)
    connection.start()
    time.sleep(2)

    # 2. PositionManager compartido por ambas estrategias
    pm = PositionManager(
        max_positions=MAX_POSITIONS,
        risk_per_trade=RISK_PER_TRADE,
        notifier=notifier
    )

    # 3. ScannerManager 1 — LONG10MIN (9:40-9:50 ET)
    #    Premarket volume máx 1M
    manager = ScannerManager(connection, pm) # Por default 1M de PMVol 

    # 4. ScannerManager 2 — LONG10MIN2 (9:30-9:40 ET)
    #    Premarket volume máx 300k
    manager2 = ScannerManager(connection, pm)
    manager2.MAX_PREMARKET_VOLUME = 300_000 

    # 5. Recuperar posiciones abiertas si el bot se reinició
    connection.request_existing_positions(manager)
    time.sleep(2)

    # 6. Scanner 1
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

    # 7. Scanner 2
    scanner2 = manager2.new_scanner()
    scan2 = ScannerSubscription()
    scan2.instrument    = "STK"
    scan2.locationCode  = "STK.US.MAJOR"
    scan2.scanCode      = "TOP_PERC_GAIN"
    scan2.marketCapBelow = 2e8
    scan2.abovePrice    = 1  # precio mínimo $1

    filters2 = []  # change_from_open > 2 ya está en el check()
    scanner2.init_scanner(scan2, filters2)

    print("[BOT] Arrancado. Esperando datos del scanner...")
    time.sleep(10)

    # ─────────────────────────────────────────
    #  LOOP PRINCIPAL
    # ─────────────────────────────────────────
    while True:
        # ── Estrategia 2: LONG10MIN2 (9:30-9:40 ET)
        for symbol, ohlc in list(manager2.ohlc_by_symbol.items()):
            if len(ohlc.data) < 5:
             continue
            if LONG10MIN2(ohlc).check():
             pm.try_enter(ohlc, tp_pct=TP_PCT, sl_pct=SL_PCT)

        # ── Estrategia 1: LONG10MIN (9:40-9:50 ET)
        for symbol, ohlc in list(manager.ohlc_by_symbol.items()):
            if len(ohlc.data) < 5:
             continue
            if LONG10MIN(ohlc).check():
             pm.try_enter(ohlc, tp_pct=TP_PCT, sl_pct=SL_PCT)

        pm.status()
        time.sleep(LOOP_INTERVAL)

if __name__ == "__main__":
    main()
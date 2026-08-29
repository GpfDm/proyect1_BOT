import time
import threading
from datetime import datetime
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
import pytz
from ibapi.contract import Contract


class TestPremarket(EClient, EWrapper):
    def __init__(self):
        EClient.__init__(self, self)
        self._next_id = 0
        self._lock = threading.Lock()
        self.hilo = None
        self.volumes_premarket = []
        self.done = False

    def next_id(self):
        with self._lock:
            self._next_id += 1
            return self._next_id

    def start(self):
        self.hilo = threading.Thread(target=self.run, daemon=True)
        self.hilo.start()

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        if errorCode not in {2104, 2106, 2107, 2108, 2158, 2103, 2105, 2157}:
            print(f"[ERROR] reqId={reqId} code={errorCode} msg={errorString}")

    def historicalData(self, reqId, bar):
     try:
        import pytz
        bar_time_local = datetime.strptime(bar.date.strip(), "%Y%m%d %H:%M:%S")
        local_tz = pytz.timezone("Europe/Madrid")
        et_tz = pytz.timezone("America/New_York")
        bar_time_et = local_tz.localize(bar_time_local).astimezone(et_tz)
        print(f"[VELA] {bar_time_et.strftime('%H:%M')} ET open={bar.open} vol={bar.volume}")
        if bar_time_et.hour < 9 or (bar_time_et.hour == 9 and bar_time_et.minute < 30):
            self.volumes_premarket.append(bar.volume)
            print(f"  → PREMARKET vol={bar.volume}")
     except Exception as e:
        print(f"[ERROR fecha] {e} raw={bar.date!r}")

    def historicalDataEnd(self, reqId, start, end):
        total = sum(self.volumes_premarket)
        print(f"\n{'='*50}")
        print(f"TOTAL VOLUMEN PREMARKET: {total:,}")
        print(f"Velas premarket encontradas: {len(self.volumes_premarket)}")
        print(f"{'='*50}")
        self.done = True


def main():
    # Símbolo a testearpm 
    SYMBOL = "UPC"

    conn = TestPremarket()
    conn.connect("127.0.0.1", 7496, clientId=99)  # clientId distinto para no chocar con el bot
    conn.start()
    time.sleep(2)

    contract = Contract()
    contract.symbol   = SYMBOL
    contract.secType  = "STK"
    contract.exchange = "SMART"
    contract.currency = "USD"

    req_id = conn.next_id()
    print(f"[TEST] Pidiendo datos históricos premarket de {SYMBOL} (reqId={req_id})")
    print(f"[TEST] useRTH=0 → debe incluir velas de 4:00 a 9:30 ET\n")

    conn.reqHistoricalData(
        reqId=req_id,
        contract=contract,
        endDateTime="",        # hasta ahora
        durationStr="1 D",     # último día
        barSizeSetting="1 min",
        whatToShow="TRADES",
        useRTH=0,              # 0 = incluye premarket y aftermarket
        formatDate=1,          # 1 = formato legible "YYYYMMDD HH:MM:SS"
        keepUpToDate=False,
        chartOptions=[]
    )

    # Esperar hasta 30 segundos a que lleguen los datos
    timeout = 30
    t_start = time.time()
    while not conn.done and (time.time() - t_start) < timeout:
        time.sleep(0.1)

    if not conn.done:
        print("[TEST] Timeout — no llegaron datos en 30 segundos")
    else:
        print("[TEST] Test completado")

    conn.disconnect()


if __name__ == "__main__":
    main()
    '''
    Si bar.date viene en formato "20260623 04:15:00" → el strptime funciona y el problema es otro
    Si viene como número tipo 1750000000 → es epoch y hay que cambiar strptime por datetime.fromtimestamp()
    Si no llega ninguna vela antes de las 9:30 → IB no devuelve premarket para ese símbolo con tu suscripción
    Si el timeout salta → historicalDataEnd no llega, mismo problema de threading que teníamos antes
    '''
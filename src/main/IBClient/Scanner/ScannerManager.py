import time
from typing import Optional
from src.main.IBClient.Scanner.ScannerClient import ScannerClient
from src.main.IBClient.ohlc.Data import Ohlc
from src.main.IBClient.PositionManager import PositionManager
import yfinance as yf


class ScannerManager():
    def __init__(self, connection, position_manager: PositionManager):
        self.connection = connection
        self.position_manager = position_manager
        self.scanners: dict[int, ScannerClient] = {}
        self.ID_contador = 0
        self.ohlc_by_symbol: dict[str, Ohlc] = {}

        # Máximo de premarket volume permitido
        self.MAX_PREMARKET_VOLUME = 1_000_000

    def new_scanner(self) -> ScannerClient:
        try:
            scan = ScannerClient(self.connection, self)
            scan.id = self.ID_contador
            self.scanners[scan.id] = scan
            self.ID_contador += 1
        except Exception as e:
            print(f"[ERROR new_scanner] {e}")
            return None
        return scan

    # ─── Filtro premarket volume ──────────────────────────────────
    def _check_premarket_volume(self, symbol: str, contract) -> bool:
        '''
        Pide datos premarket (useRTH=0) y suma volumen antes de 9:30 ET.
        Usa el registro normal de IBConnection (_premarket_callbacks),
        igual que el resto de reqId del bot, en vez de sustituir
        callbacks temporalmente (eso era frágil con el wrapper de ibapi).
        Devuelve True si el volumen premarket <= MAX_PREMARKET_VOLUME.
        '''
        req_id = self.connection.next_id()

        self.connection._premarket_callbacks[req_id] = {
            "volumes": [],
            "done": False,
            "symbol": symbol
        }

        try:
            self.connection.reqHistoricalData(
                reqId=req_id,
                contract=contract,
                endDateTime="",
                durationStr="1 D",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=0,           # 0 = incluye premarket
                formatDate=1,
                keepUpToDate=False,
                chartOptions=[]
            )
        except Exception as e:
            print(f"[FILTRO PREMARKET] {symbol}: error pidiendo datos -> {e}")
            self.connection._premarket_callbacks.pop(req_id, None)
            return True  # si falla, dejamos pasar (conservador)

        # Esperar respuesta máximo 10 segundos
        timeout = 10
        t_start = time.time()
        entry = self.connection._premarket_callbacks[req_id]
        while not entry["done"] and (time.time() - t_start) < timeout:
            time.sleep(0.1)

        entry = self.connection._premarket_callbacks.pop(req_id, None)

        if entry is None or not entry["done"]:
            print(f"[FILTRO PREMARKET] {symbol}: timeout esperando datos, se permite pasar")
            return True  # conservador: si no hay respuesta, dejamos pasar

        premarket_vol = sum(entry["volumes"])
        ok = premarket_vol <= self.MAX_PREMARKET_VOLUME
        print(f"[FILTRO PREMARKET] {symbol}: vol premarket={premarket_vol:,} "
              f"(máx={self.MAX_PREMARKET_VOLUME:,}) -> "
              f"{'✅ OK' if ok else '❌ DESCARTADO'}")
        return ok

    # ─── Nuevo símbolo detectado por el scanner ───────────────────
    def on_new_symbol(self, symbol: str, contract) -> Optional[Ohlc]:
        '''
        Llamado por ScannerClient en scannerDataEnd.
        Lanza un thread separado para no bloquear el hilo de IB
        mientras espera la respuesta del filtro premarket.
        '''
        if symbol in self.ohlc_by_symbol:
         return

        import threading
        t = threading.Thread(target=self._process_new_symbol,args=(symbol, contract),daemon=True)
        t.start()
    def _process_new_symbol(self, symbol: str, contract) -> None:
        '''
        Corre en thread separado. Contiene toda la lógica que antes
        estaba en on_new_symbol: filtro premarket + creación de Ohlc.
        '''
        # Doble check por si el símbolo llegó dos veces mientras arrancaba el thread
        if symbol in self.ohlc_by_symbol:
         return

        # ── Filtro premarket volume ──
        if not self._check_premarket_volume(symbol, contract):
         print(f"[FILTRO] {symbol} descartado: premarket volume > {self.MAX_PREMARKET_VOLUME:,}")
         return
        # Filtro de float:
        if not self._check_float(symbol, contract):
         return
        
        #── Crear Ohlc ──
        ohlc = Ohlc(symbol, self.connection, contract)
        ohlc.data_historic.set_duration_str("1 D")
        ohlc.data_historic.set_bar_size_setting("1 min")
        ohlc.data_historic.set_keep_up_to_date(True)
        ohlc.data_historic.set_format_date(1)
        ohlc.position_manager = self.position_manager
        ohlc.start()
        self.ohlc_by_symbol[symbol] = ohlc
        print(f"[NUEVO SIMBOLO] {symbol} -> Ohlc creado (reqId={ohlc.req_id})")
    # ─── Resto de métodos ─────────────────────────────────────────
    def remove_symbol(self, symbol: str):
        ohlc = self.ohlc_by_symbol.pop(symbol, None)
        if ohlc:
            ohlc.cancelar_suscrpdatos()
    def delete_scanner(self, scan_id: int):
        scan = self.scanners.get(scan_id)
        if scan is None:
            print("[ERROR] Scanner no encontrado")
            return
        try:
            scan.stop()
        except Exception as e:
            print(f"[ERROR stopping scanner] {e}")
        del self.scanners[scan_id]

    def see_list_scanner(self):
        print(self.scanners)

    def see_scan_stocks(self, scan_id: int):
        screener = self.scanners.get(scan_id)
        if screener is None:
            print("[ERROR] Scanner no encontrado")
            return
        print(screener.scanner_live)

    def update_scanner(self, scan_id: int, port: int, server: str):
        scan = self.scanners.get(scan_id)
        if scan is None:
            print("[ERROR] Scanner no encontrado")
            return
        updated = False
        if port > 0:
            scan.PORT = port
            updated = True
        if server != "":
            scan.SERVER = server
            updated = True
        if updated:
            scan.ADDR = (scan.SERVER, scan.PORT)
        scan.reconnect(scan.get_id(), [])
    def _check_float(self, symbol: str, contract) -> bool:
        MAX_FLOAT = 20_000_000
        try:
         ticker = yf.Ticker(symbol)
         info = ticker.info
         float_shares = info.get("floatShares", None)
        
         if float_shares is None:
            print(f"[FILTRO FLOAT] {symbol}: sin datos, se permite pasar")
            return True
            
         ok = float_shares <= MAX_FLOAT
         print(f"[FILTRO FLOAT] {symbol}: float={float_shares:,} -> {'✅ OK' if ok else '❌ DESCARTADO'}")
         return ok
        except Exception as e:
         print(f"[FILTRO FLOAT] {symbol}: error -> {e}, se permite pasar")
         return True
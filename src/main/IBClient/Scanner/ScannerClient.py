from __future__ import annotations
import time
from ibapi.scanner import ScannerSubscription
from ibapi.tag_value import TagValue
from ibapi.contract import ContractDetails
from src.main.IBClient.ohlc.Data import IBConnection

#from src.main.IBClient.Scanner.ScannerManager import ScannerManager


class ScannerClient():
    '''
    Ya NO hereda de EClient/EWrapper. Usa la IBConnection compartida
    para mandar requests, y recibe callbacks ruteados desde ella.
    '''
    def __init__(self, connection, manager):
        self.connection = connection
        self.manager = manager
        self.scanner_buffer = {}  # resultados temporales mientras llegan
        self.scanner_live = {}    # resultados finales tras scannerDataEnd
        self.state_loop = False
        self.req_id = None
        self.id = None
        self.hilo = None

    def init_scanner(self, Scan: ScannerSubscription, Filters: list[TagValue]):
        '''
        Suscribe este scanner. Se registra en la connection para
        que pueda rutear scannerData/scannerDataEnd hacia aquí.
        '''
        try:
            self.req_id = self.connection.next_id()
            self.connection.scanner_by_reqid[self.req_id] = self
            self.connection.reqScannerSubscription(
                reqId=self.req_id,
                subscription=Scan,
                scannerSubscriptionOptions=[],
                scannerSubscriptionFilterOptions=Filters
            )
        except Exception as e:
            print(f"[ERROR init_scanner] {e}")

    def scannerData(self, reqId: int, rank: int, contractDetails: ContractDetails,
                     distance: str, benchmark: str, projection: str, legsStr: str):
        '''
        Llamado (vía connection) por cada resultado del scanner.
        '''
        c = contractDetails.contract
        self.scanner_buffer[c.symbol] = {
            "rank": rank,
            "contract": c
        }

    def scannerDataEnd(self, reqId: int):
        '''
        Llamado (vía connection) cuando termina el envío de resultados.
        Aquí pasamos los resultados a "live" y avisamos al manager
        de cada símbolo para que cree su Ohlc si es nuevo.
        '''
        self.scanner_live = self.scanner_buffer
        self.scanner_buffer = {}

        for symbol, info in self.scanner_live.items():
            self.manager.on_new_symbol(symbol, info["contract"])

    def scan_loop(self, scan: ScannerSubscription, interval: int = 5):
        '''
        Re-suscribe el scanner periódicamente para refrescar resultados.
        Pensado para correr en un thread propio.
        '''
        self.state_loop = True
        while self.state_loop:
            try:
                if self.req_id is not None:
                    self.connection.cancelScannerSubscription(self.req_id)
            except Exception:
                pass

            time.sleep(1)
            self.init_scanner(scan, [])
            time.sleep(interval)

    def stop(self):
        '''
        Detiene el scanner. Ya no toca el socket/hilo directamente:
        eso lo gestiona IBConnection.
        '''
        self.state_loop = False
        try:
            if self.req_id is not None:
                self.connection.cancelScannerSubscription(self.req_id)
                self.connection.scanner_by_reqid.pop(self.req_id, None)
        except Exception:
            pass

# Ejemplo de uso aislado (requiere una IBConnection ya conectada
# y un ScannerManager para registrar Ohlc de los símbolos detectados)

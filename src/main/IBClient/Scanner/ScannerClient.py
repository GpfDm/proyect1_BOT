from __future__ import annotations
import time
from ibapi.scanner import ScannerSubscription
from ibapi.tag_value import TagValue
from ibapi.contract import ContractDetails
from src.main.IBClient.ohlc.Data import IBConnection

#from src.main.IBClient.Scanner.ScannerManager import ScannerManager


class ScannerClient():
    '''
    It does not inherit from EClient/EWrapper. It uses the shared IBConnection
    to send requests and receives callbacks routed from it.
    '''
    def __init__(self, connection, manager):
        self.connection = connection
        self.manager = manager
        self.scanner_buffer = {}  # before scannerdataend
        self.scanner_live = {}    # after scannerdataend
        self.state_loop = False
        self.req_id = None
        self.id = None
        self.hilo = None

    def init_scanner(self, Scan: ScannerSubscription, Filters: list[TagValue]):
        '''
        Subscribe this scanner. Register it on the connection 
        so that it can route scannerData/scannerDataEnd here.
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
        Called (via connection) for each scanner result.        
        '''
        c = contractDetails.contract
        self.scanner_buffer[c.symbol] = {
            "rank": rank,
            "contract": c
        }

    def scannerDataEnd(self, reqId: int):
        '''
        A call is made (via connection) when the results transmission is complete.
        Here we move the results to "live" and notify the manager
        of each symbol to create its Ohlc if it's new.
        '''
        self.scanner_live = self.scanner_buffer
        self.scanner_buffer = {}

        for symbol, info in self.scanner_live.items():
            self.manager.on_new_symbol(symbol, info["contract"])

    def scan_loop(self, scan: ScannerSubscription, interval: int = 5):
        '''
        Resubscribe the scanner periodically to refresh results.
        Designed to run in its own thread.
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
        Stops the scanner
        '''
        self.state_loop = False
        try:
            if self.req_id is not None:
                self.connection.cancelScannerSubscription(self.req_id)
                self.connection.scanner_by_reqid.pop(self.req_id, None)
        except Exception:
            pass

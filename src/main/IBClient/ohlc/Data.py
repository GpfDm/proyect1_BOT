
#  DATA FOR STRATEGY
class Data_for_Strategy():
    '''
    Parameters used by reqHistoricalData.
    '''
    def __init__(self):
        self.contract: Contract         # assigned via set_contract()
        self.endDateTime: str = ""
        self.durationStr: str = ""
        self.bar_size_setting: str = ""
        self.what_to_show: str = "TRADES"
        self.useRTH: int = 1
        self.format_date: int = None
        self.keep_up_to_date: bool = True
        self.charOptions: list[TagValue] = []

    def set_end_datetime(self, v: str):       self.endDateTime = v
    def set_contract(self, v: Contract):      self.contract = v
    def set_duration_str(self, v: str):       self.durationStr = v
    def set_bar_size_setting(self, v: str):   self.bar_size_setting = v
    def set_what_to_show(self, v: str):       self.what_to_show = v
    def set_use_rth(self, v: int):            self.useRTH = v
    def set_format_date(self, v):             self.format_date = v
    def set_keep_up_to_date(self, v: bool):   self.keep_up_to_date = v
    def set_duration_to_show(self, v: str):   self.duration_to_show = v



#  TRADE LOGGER
class TradeLogger():
    '''
    Persists every trade to a CSV file.
    Columns: symbol, entry_time, exit_time, entry_price, exit_price,
             planned_entry, tp_price, sl_price, quantity, pnl,
             slippage_entry, slippage_exit, reason
    '''

    LOG_PATH = "trades_log.csv"
    HEADERS = [
        "symbol", "entry_time", "exit_time",
        "entry_price", "exit_price", "planned_entry",
        "tp_price", "sl_price", "quantity",
        "pnl", "slippage_entry", "slippage_exit", "reason"
    ]

    def __init__(self):
        # Create the CSV with headers if it doesn't exist
        if not os.path.exists(self.LOG_PATH):
            with open(self.LOG_PATH, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=self.HEADERS).writeheader()

    def log(self, record: dict):
        with open(self.LOG_PATH, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=self.HEADERS).writerow(record)
        print(f"[LOG] Trade guardado: {record}")


_trade_logger = TradeLogger()  # global instance shared by all Ohlc objects


#  OHLC  (one instance per symbol)
class Ohlc():
    '''
    One instance per symbol. Uses the shared IBConnection for broker communication.
    '''

    def __init__(self, symbol: str, connection, contract: Contract = None):
        self.symbol = symbol
        self.connection = connection
        self.req_id: Optional[int] = None
        self.id_data: Optional[int] = None
        self.estado_data: bool = False # Controls whether data is being streamed
        self.data_historic = Data_for_Strategy()
        if contract is not None:
            self.data_historic.set_contract(contract)

        self.data: list[dict] = []   # list of bars for this symbol
        self.quantity: float = 0
        self.risk: float = 200

        # ── Position state ──
        self.in_position: bool = False
        self.entry_price: float = 0.0
        self.tp_price: Optional[float] = None
        self.sl_price: Optional[float] = None
        self.last_price: Optional[float] = None
        self.tick_req_id: Optional[int] = None
        self.hard_stop_order_id: Optional[int] = None
        self._planned_entry: Optional[float] = None
        self.entry_order_id: Optional[int] = None
        self._entry_time: Optional[str] = None

        # ── PositionManager (assigned externally when the Ohlc is created) ──
        self.position_manager = None    # reference to the shared PositionManager

        # ── Liquidity ──
        self.MIN_VOLUME_BARS = 2       # minimum number of bars with volume to consider the stock liquid
        self.MIN_AVG_VOLUME = 5000    # minimum average volume per bar
        self.MAX_SPREAD_PCT = 0.015     # maximum allowed spread (1.5%)

    # ─── Historical data ───────────────────────────────────────
    def start(self):
        self.req_id = self.connection.next_id()
        self.connection.register(self.req_id, self)
        try:
            self.connection.reqHistoricalData(
                reqId=self.req_id,
                contract=self.data_historic.contract,
                endDateTime=self.data_historic.endDateTime,
                durationStr=self.data_historic.durationStr,
                barSizeSetting=self.data_historic.bar_size_setting,
                whatToShow=self.data_historic.what_to_show,
                useRTH=self.data_historic.useRTH,
                formatDate=self.data_historic.format_date,
                keepUpToDate=self.data_historic.keep_up_to_date,
                chartOptions=self.data_historic.charOptions
            )
            self.estado_data = True
            self.id_data = self.req_id
        except Exception as e:
            print(f"[ERROR start] {self.symbol}: {e}")

    def cancelar_suscrpdatos(self):
        try:
            if self.estado_data:
                print(f"[{self.symbol}] Cancelamos datos históricos")
                self.connection.cancelHistoricalData(self.id_data)
                self.connection.unregister(self.req_id)
                self.estado_data = False
        except Exception as e:
            print(f"[ERROR cancelar_suscrpdatos] {self.symbol}: {e}")

    def on_historical_data(self, bar):
        self.data.append({
            "date": bar.date, "open": bar.open, "high": bar.high,
            "low": bar.low,   "close": bar.close, "volume": bar.volume
        })

    def on_historical_data_update(self, bar):
        new_bar = {
            "date": bar.date, "open": bar.open, "high": bar.high,
            "low": bar.low,   "close": bar.close, "volume": bar.volume
        }
        if not self.data or self.data[-1]["date"] != bar.date:
            self.data.append(new_bar)
        else:
            self.data[-1] = new_bar

    # ─── Liquidity ────────────────────────────────────────────────
    def is_liquid(self, bid: float, ask: float) -> bool:
        '''
        Checks minimum volume and maximum spread before entering a trade.
        Called from enter_position (Strategy.py).
        '''
        if len(self.data) < self.MIN_VOLUME_BARS:
            print(f"[{self.symbol}] ILÍQUIDO: pocas velas ({len(self.data)})")
            return False

        recent = self.data[-self.MIN_VOLUME_BARS:]
        avg_vol = sum(b["volume"] for b in recent) / len(recent)
        if avg_vol < self.MIN_AVG_VOLUME:
            print(f"[{self.symbol}] ILÍQUIDO: volumen medio {avg_vol:.0f} < {self.MIN_AVG_VOLUME}")
            return False

        if bid > 0 and ask > 0:
            spread_pct = (ask - bid) / ask
            if spread_pct > self.MAX_SPREAD_PCT:
                print(f"[{self.symbol}] SPREAD ALTO: {spread_pct*100:.2f}% > {self.MAX_SPREAD_PCT*100:.2f}%")
                return False

        return True

    # ─── Orders ─────────────────────────────────────────────────
    def calcular_Quantity(self, riesgo: float) -> float:
        if not self.data:
            return 0
        close = self.data[-1]["close"]
        if close <= 0:
            return 0
        qty = int(riesgo / close)
        return min(qty, 10000)  # max 10,000 shares as a safety limit

    def buy_order(self) -> Order:
        order = Order()
        order.action = "BUY"
        order.orderType = "MKT"
        order.totalQuantity = self.calcular_Quantity(self.risk)
        order.eTradeOnly = False    
        order.firmQuoteOnly = False
        self.quantity = order.totalQuantity
        print(f"[ORDER] {self.symbol} BUY qty={self.quantity} risk={self.risk}")
        return order

    def sell_order(self) -> Order:
        order = Order()
        order.action = "SELL"
        order.orderType = "MKT"
        order.totalQuantity = self.quantity
        order.eTradeOnly = False    # ← REQUIRED for the buy order to work.
        order.firmQuoteOnly = False # ← REQUIRED for the buy order to work.
        return order

    def stop_loss_order(self, stop_price: float) -> Order:
        order = Order()
        order.action = "SELL"
        order.orderType = "STP"
        order.totalQuantity = self.quantity
        order.eTradeOnly = False    # ← REQUIRED for the buy order to work.
        order.firmQuoteOnly = False # ← REQUIRED for the buy order to work.
        order.auxPrice = stop_price   # price that triggers the stop
        order.tif = "GTC"            # remains active even if the bot/TWS goes down
        return order

    @staticmethod
    def create_stock_contract(symbol: str) -> Contract:
        contract = Contract()
        contract.symbol = symbol
        contract.secType = "STK"
        contract.exchange = "SMART"
        contract.currency = "USD"
        return contract

    # ─── Tick data (real-time TP/SL monitoring) ───────────────
    def request_tick_data(self):
        self.tick_req_id = self.connection.next_id()
        self.connection.register_tick(self.tick_req_id, self)
        try:
            self.connection.reqMktData(
                reqId=self.tick_req_id,
                contract=self.data_historic.contract,
                genericTickList="",
                snapshot=False,
                regulatorySnapshot=False,
                mktDataOptions=[]
            )
        except Exception as e:
            print(f"[ERROR tick data] {self.symbol}: {e}")

    def cancel_tick_data(self):
        if self.tick_req_id is not None:
            try:
                self.connection.cancelMktData(self.tick_req_id)
            except Exception:
                pass
            self.connection.unregister_tick(self.tick_req_id)
            self.tick_req_id = None

    # ─── Position management ─────────────────────────────────────
    def open_position(self, entry_price: float, tp_price: float, sl_price: float):
        self.in_position = True
        self._planned_entry = entry_price
        self.entry_price = entry_price   # overwritten later with the actual fill price
        self.tp_price = tp_price
        self.sl_price = sl_price
        self._entry_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Hard backup stop at the broker (GTC, remains active if the bot goes down)
        stop_order = self.stop_loss_order(sl_price)
        self.hard_stop_order_id = self.connection.next_order_id()
        try:
            self.connection.placeOrder(
                self.hard_stop_order_id,
                self.data_historic.contract,
                stop_order
            )
            # Register the hard stop so we can detect if it gets filled while the bot is down
            self.connection.register_order(self.hard_stop_order_id, self)
            print(f"[{self.symbol}] Stop duro enviado a {sl_price} (id={self.hard_stop_order_id})")
        except Exception as e:
            print(f"[ERROR stop duro] {self.symbol}: {e}")

        self.request_tick_data()
        print(f"[{self.symbol}] Posición abierta | entry≈{entry_price} TP={tp_price} SL={sl_price}")

    def on_tick_price(self, price: float):
        '''
        Called by IBConnection.tickPrice (tickType LAST).
        Filters invalid ticks and checks them against the TP/SL levels.
        '''
        # ── Filter invalid ticks ──
        if price is None or price <= 0:
            return

        self.last_price = price

        # ── Detect HALT by price (TWS sends -1.0 during a halt) ──
        if price < 0:
            print(f"[{self.symbol}] ⚠️  POSIBLE HALT detectado (precio={price})")
            return

        if not self.in_position:
            return

        if self.tp_price is not None and price >= self.tp_price:
            self._close_position(reason="TP", exit_price=price)
        elif self.sl_price is not None and price <= self.sl_price:
            self._close_position(reason="SL", exit_price=price)

    def on_halted(self):
        '''
        Called by IBConnection.tickString when tickType=HALTED.
        Logs the halt and does not attempt to send orders while the symbol is halted.
        '''
        print(f"[{self.symbol}] 🛑 HALT detectado. Posición={'ABIERTA' if self.in_position else 'SIN POSICIÓN'}. "
              f"El stop duro en broker (id={self.hard_stop_order_id}) sigue activo.")

    def on_resumed(self):
        '''
        Called when the symbol resumes trading after a halt (tickType resumed).
        '''
        print(f"[{self.symbol}] ✅ Reanudado tras halt. Revisando posición...")

    def _close_position(self, reason: str, exit_price: float):
        '''
        Closes the position with a market order and logs the trade.
        '''
        order = self.sell_order()
        order_id = self.connection.next_order_id()
        try:
            self.connection.placeOrder(order_id, self.data_historic.contract, order)
            print(f"[{self.symbol}] CIERRE por {reason} a ~{exit_price} (orden id={order_id})")
        except Exception as e:
            print(f"[ERROR cierre {reason}] {self.symbol}: {e}")
            return

        # Cancel the hard stop since it is no longer needed
        if self.hard_stop_order_id is not None:
            try:
                self.connection.cancelOrder(self.hard_stop_order_id)
            except Exception:
                pass
            self.connection.ohlc_by_order_id.pop(self.hard_stop_order_id, None)
            self.hard_stop_order_id = None

        # ── Log the trade ──
        pnl = (exit_price - self.entry_price) * self.quantity
        slippage_entry = (self.entry_price - self._planned_entry) if self._planned_entry else 0
        slippage_exit = 0   # updated in on_exec_details for the exit if implemented
        _trade_logger.log({
            "symbol":          self.symbol,
            "entry_time":      self._entry_time,
            "exit_time":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "entry_price":     self.entry_price,
            "exit_price":      exit_price,
            "planned_entry":   self._planned_entry,
            "tp_price":        self.tp_price,
            "sl_price":        self.sl_price,
            "quantity":        self.quantity,
            "pnl":             round(pnl, 4),
            "slippage_entry":  round(slippage_entry, 4),
            "slippage_exit":   slippage_exit,
            "reason":          reason
        })

        self.in_position = False
        self.tp_price = None
        self.sl_price = None
        self.cancel_tick_data()

        # Notify PositionManager so it can free up the slot
        if self.position_manager is not None:
            self.position_manager.on_position_closed(self.symbol, reason, round(pnl, 4))

    def on_hard_stop_filled(self, fill_price: float):
        '''
        Called by IBConnection.orderStatus when the hard stop is filled
        (e.g. the bot was down or there was a gap).
        Clears the internal state without sending another order.
        '''
        print(f"[{self.symbol}] ⚠️  Stop duro ejecutado a {fill_price} (el bot estaba caído o hubo gap)")
        pnl = (fill_price - self.entry_price) * self.quantity
        slippage_exit = fill_price - self.sl_price if self.sl_price else 0
        _trade_logger.log({
            "symbol":          self.symbol,
            "entry_time":      self._entry_time,
            "exit_time":       datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "entry_price":     self.entry_price,
            "exit_price":      fill_price,
            "planned_entry":   self._planned_entry,
            "tp_price":        self.tp_price,
            "sl_price":        self.sl_price,
            "quantity":        self.quantity,
            "pnl":             round(pnl, 4),
            "slippage_entry":  round((self.entry_price - self._planned_entry), 4) if self._planned_entry else 0,
            "slippage_exit":   round(slippage_exit, 4),
            "reason":          "STOP_DURO"
        })
        self.in_position = False
        self.hard_stop_order_id = None
        self.tp_price = None
        self.sl_price = None
        self.cancel_tick_data()

        # Notify PositionManager so it can free up the slot
        if self.position_manager is not None:
            self.position_manager.on_position_closed(self.symbol, "STOP_DURO", round(pnl, 4))

    def restore_position(self, quantity: float, avg_cost: float):
        '''
        Called when the bot starts up and reqPositions detects
        that there is already an open position in the account (bot restart).
        Restores the minimum state required for TP/SL monitoring.
        NOTE: TP/SL levels are lost after a restart — conservative values
        are used here; adjust them as needed.
        '''
        print(f"[{self.symbol}] Posición existente detectada al arrancar: qty={quantity} cost={avg_cost}")
        self.quantity = quantity
        self.entry_price = avg_cost
        self._planned_entry = avg_cost
        self._entry_time = "RECUPERADO_AL_ARRANCAR"
        self.tp_price = avg_cost * 1.10   # Conservative 10% TP (adjust as needed)
        self.sl_price = avg_cost * 0.95   # Conservative 5% SL (adjust as needed)
        self.in_position = True
        self.request_tick_data()
        print(f"[{self.symbol}] Estado restaurado | TP={self.tp_price:.4f} SL={self.sl_price:.4f}")

    # ─── execDetails: actual entry price ─────────────────────
    def on_exec_details(self, order_id: int, fill_price: float):
        if self.entry_order_id is None:      # ← first: has it already been processed?
            return
        if order_id != self.entry_order_id:  # ← second: is this our order?
            return

        planned = self._planned_entry
        self.entry_price = fill_price

        if self.tp_price is not None and planned:
            tp_pct = (self.tp_price / planned) - 1
            self.tp_price = fill_price * (1 + tp_pct)
        if self.sl_price is not None and planned:
            sl_pct = 1 - (self.sl_price / planned)
            self.sl_price = fill_price * (1 - sl_pct)

        print(f"[{self.symbol}] Fill real={fill_price} (estimado={planned}) "
              f"-> TP={self.tp_price:.4f} SL={self.sl_price:.4f}")

        self.entry_order_id = None  # mark as processed


# ─────────────────────────────────────────────
#  IBCONNECTION  (single broker connection)
# ─────────────────────────────────────────────
class IBConnection(EClient, EWrapper):
    def __init__(self):
        EClient.__init__(self, self)
        self._next_id = 0
        self._lock = threading.Lock()
        self.hilo = None
        self._premarket_callbacks: dict = {}
        self._next_order_id = 0  # updated by nextValidId

        # Routing maps
        self.ohlc_by_reqid:    dict[int, Ohlc] = {}   # historical data
        self.tick_by_reqid:    dict[int, Ohlc] = {}   # tick data
        self.ohlc_by_order_id: dict[int, Ohlc] = {}   # orders (entry + hard stop)
        self.scanner_by_reqid: dict[int, object] = {}  # ScannerClient

        # Bid/ask by symbol for is_liquid()
        self._bid: dict[str, float] = {}
        self._ask: dict[str, float] = {}

    # ─── Connection ────────────────────────────────────────────────
    def start(self):
        self.hilo = threading.Thread(target=self.run, daemon=True)
        self.hilo.start()

    def next_id(self) -> int:
        with self._lock:
            self._next_id += 1
            return self._next_id

    # ─── Registration ───────────────────────────────────────────────
    def register(self, req_id: int, ohlc: Ohlc):
        self.ohlc_by_reqid[req_id] = ohlc

    def unregister(self, req_id: int):
        self.ohlc_by_reqid.pop(req_id, None)

    def register_tick(self, req_id: int, ohlc: Ohlc):
        self.tick_by_reqid[req_id] = ohlc

    def unregister_tick(self, req_id: int):
        self.tick_by_reqid.pop(req_id, None)

    def register_order(self, order_id: int, ohlc: Ohlc):
        self.ohlc_by_order_id[order_id] = ohlc

    # ─── Historical data callbacks ─────────────────────────────────────
    def historicalData(self, reqId, bar):
        if reqId in self._premarket_callbacks:
            try:
                bar_time_local = datetime.strptime(bar.date.strip(), "%Y%m%d %H:%M:%S")
                local_tz = pytz.timezone("Europe/Madrid")
                et_tz = pytz.timezone("America/New_York")
                bar_time_et = local_tz.localize(bar_time_local).astimezone(et_tz)
                if bar_time_et.hour < 9 or (bar_time_et.hour == 9 and bar_time_et.minute < 30):
                    self._premarket_callbacks[reqId]["volumes"].append(bar.volume)
            except Exception as e:
                print(f"[DEBUG premarket] {e} raw={bar.date!r}")
            return

        ohlc = self.ohlc_by_reqid.get(reqId)
        if ohlc:
            ohlc.on_historical_data(bar)
         
    def historicalDataUpdate(self, reqId, bar):
        ohlc = self.ohlc_by_reqid.get(reqId)
        if ohlc:
            ohlc.on_historical_data_update(bar)

    def historicalDataEnd(self, reqId, start, end):
        '''
        Signals that IB has finished sending all historical bars.
        Used by _check_premarket_volume in ScannerManager to know
        when it can stop waiting.
        '''
        if reqId in self._premarket_callbacks:
            self._premarket_callbacks[reqId]["done"] = True
            return
        pass

    # ─── Tick data callbacks ──────────────────────────────────────
    def tickPrice(self, reqId, tickType, price, attrib):
        '''
        tickType 1=BID, 2=ASK, 4=LAST
        Store bid/ask for is_liquid() and route LAST to Ohlc.
        '''
        from ibapi.ticktype import TickTypeEnum
        ohlc = self.tick_by_reqid.get(reqId)
        if ohlc is None:
            return

        if tickType == TickTypeEnum.BID:
            self._bid[ohlc.symbol] = price
        elif tickType == TickTypeEnum.ASK:
            self._ask[ohlc.symbol] = price
        elif tickType == TickTypeEnum.LAST:
            if price > 0:
                ohlc.on_tick_price(price)

    def tickString(self, reqId, tickType, value):
        '''
        tickType 49 = HALTED
        value "0" = normal trading, "1" or "2" = halted
        '''
        HALTED_TICK = 49
        if tickType != HALTED_TICK:
            return
        ohlc = self.tick_by_reqid.get(reqId)
        if ohlc is None:
            return
        if value in ("1", "2"):
            ohlc.on_halted()
        elif value == "0":
            ohlc.on_resumed()

    # ─── Order callbacks ────────────────────────────────────────
    def execDetails(self, reqId, contract, execution):
        '''
        Receives fills for any order and routes them to the corresponding Ohlc by orderId.
        '''
        ohlc = self.ohlc_by_order_id.get(execution.orderId)
        if ohlc:
            ohlc.on_exec_details(execution.orderId, execution.avgPrice)

    def orderStatus(self, orderId, status, filled, remaining,
                    avgFillPrice, permId, parentId, lastFillPrice,
                    clientId, whyHeld, mktCapPrice):
        '''
        Detects when the hard stop is filled (e.g. the bot was down).
        Status "Filled" with filled > 0 means the hard stop was triggered.
        '''
        if status != "Filled" or filled <= 0:
            return
        ohlc = self.ohlc_by_order_id.get(orderId)
        if ohlc is None:
            return

        # Only handle the hard stop, not the entry or active exit order
        if orderId == ohlc.hard_stop_order_id:
            ohlc.on_hard_stop_filled(avgFillPrice)
            self.ohlc_by_order_id.pop(orderId, None)

    # ─── reqPositions: restore state on startup ───────────────
    def request_existing_positions(self, manager):
        '''
        Calls reqPositions when the bot starts.
        If there are open positions in the account, restores the state
        of the corresponding Ohlc (or creates one if it doesn't exist).
        '''
        self._position_manager_ref = manager
        self.reqPositions()

    def position(self, account, contract, position, avgCost):
        '''
        Callback for reqPositions. Called once for each open position.
        '''
        if position == 0:
            return  # position is closed, ignore

        symbol = contract.symbol
        manager = getattr(self, "_position_manager_ref", None)
        if manager is None:
            return

        print(f"[ARRANQUE] Posición existente detectada: {symbol} qty={position} cost={avgCost}")

        # If we already have an Ohlc for this symbol, restore its state
        ohlc = manager.ohlc_by_symbol.get(symbol)
        if ohlc is None:
            # Create a minimal Ohlc to manage the existing position
            ohlc = Ohlc(symbol, self, contract)
            ohlc.data_historic.set_duration_str("1 D")
            ohlc.data_historic.set_bar_size_setting("1 min")
            ohlc.data_historic.set_keep_up_to_date(True)
            ohlc.start()
            manager.ohlc_by_symbol[symbol] = ohlc

        ohlc.restore_position(quantity=position, avg_cost=avgCost)

    def positionEnd(self):
        print("[ARRANQUE] reqPositions completado.")

    # ─── Scanner callbacks ────────────────────────────────────────
    def scannerData(self, reqId, rank, contractDetails, distance, benchmark, projection, legsStr):
        scanner = self.scanner_by_reqid.get(reqId)
        if scanner:
            scanner.scannerData(reqId, rank, contractDetails, distance, benchmark, projection, legsStr)

    def scannerDataEnd(self, reqId):
        scanner = self.scanner_by_reqid.get(reqId)
        if scanner:
            scanner.scannerDataEnd(reqId)

    def nextValidId(self, orderId: int):
        '''
        IB calls this when connecting with the first valid order ID.
        All placeOrder calls must use IDs greater than or equal to this one.
        '''
        self._next_order_id = orderId
        print(f"[IB] nextValidId recibido: {orderId}")

    def next_order_id(self) -> int:
        '''
        Use this only for orders (placeOrder).
        next_id() is still used for reqHistoricalData, reqMktData, etc.
        '''
        with self._lock:
            oid = self._next_order_id
            self._next_order_id += 1
            return oid

    # ─── Errors ─────────────────────────────────────────────────
    # Relevant IB error codes:
    # 200 = No security definition   → invalid symbol
    # 354 = Requested market data    → no market data permission
    # 2104/2106 = Farm connection OK → informational, not actual errors
    # 10197 = No market data         → delayed data or no subscription
    INFORMATIONAL_CODES = {2104, 2106, 2107, 2108, 2158, 2103, 2105, 2157}

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        #print(f"[ERROR RAW] reqId={reqId} code={errorCode} msg={errorString}")
        
        if errorCode in self.INFORMATIONAL_CODES:
            # Connection status messages, not actual errors
            return

        print(f"[ERROR IB] reqId={reqId} code={errorCode} msg={errorString}")

        if errorCode == 200:
            print(f"  → Símbolo no encontrado (reqId={reqId}). Eliminando del registro.")
            ohlc = self.ohlc_by_reqid.get(reqId)
            if ohlc:
                print(f"  → Símbolo afectado: {ohlc.symbol}")

        elif errorCode == 354:
            print(f"  → Sin permiso de market data para reqId={reqId}. Revisa suscripciones en TWS.")

        elif errorCode == 10197:
            print(f"  → Sin market data (delayed/sin suscripción) para reqId={reqId}.")

        elif errorCode in (1100, 1101, 1102):
            # Disconnection / reconnection
            print(f"  → Conectividad con TWS: code={errorCode}. "
                  f"{'Reconectado.' if errorCode == 1102 else 'Desconectado.'}")

        elif errorCode == 201:
            print(f"  → Orden rechazada (reqId={reqId}): {errorString}")
            ohlc = self.ohlc_by_order_id.get(reqId)
            if ohlc:
                print(f"  → Orden afectada: símbolo={ohlc.symbol}")

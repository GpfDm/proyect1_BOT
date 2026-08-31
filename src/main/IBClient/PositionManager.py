import threading
import smtplib
from email.mime.text import MIMEText
from src.main.IBClient.ohlc.Data import Ohlc


#  NOTIFICATIONS
class Notifier():
    '''
    Sends notifications when the bot cannot enter a signal
    because the maximum number of positions has been reached.

    For now, it prints everything to the console (always works)
    and can optionally send an email if credentials are configured.
    '''
    def __init__(self, email_from: str = "", email_to: str = "", email_password: str = ""):
        self.email_from = email_from
        self.email_to = email_to
        self.email_password = email_password
        self.email_enabled = bool(email_from and email_to and email_password)

    def send(self, subject: str, body: str):
        # Always print to the console
        print(f"\n{'='*50}")
        print(f"[NOTIFICACIÓN] {subject}")
        print(f"{body}")
        print(f"{'='*50}\n")

        # Email (optional)
        if self.email_enabled:
            try:
                msg = MIMEText(body)
                msg["Subject"] = subject
                msg["From"] = self.email_from
                msg["To"] = self.email_to
                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                    server.login(self.email_from, self.email_password)
                    server.sendmail(self.email_from, self.email_to, msg.as_string())
                print(f"[NOTIFICACIÓN] Email enviado a {self.email_to}")
            except Exception as e:
                print(f"[NOTIFICACIÓN] Error enviando email: {e}")

    def signal_missed(self, symbol: str, reason: str, last_price: float,
                      active_positions: list[str]):
        subject = f"⚠️ Señal perdida: {symbol}"
        body = (
            f"Símbolo:            {symbol}\n"
            f"Precio aproximado:  {last_price}\n"
            f"Motivo:             {reason}\n"
            f"Posiciones activas: {', '.join(active_positions) if active_positions else 'ninguna'}\n"
        )
        self.send(subject, body)

    def position_opened(self, symbol: str, entry_price: float,
                        tp: float, sl: float, slot: int, max_slots: int):
        subject = f"✅ Entrada: {symbol}"
        body = (
            f"Símbolo:   {symbol}\n"
            f"Entry≈:    {entry_price:.4f}\n"
            f"TP:        {tp:.4f}  (+{((tp/entry_price)-1)*100:.1f}%)\n"
            f"SL:        {sl:.4f}  (-{(1-(sl/entry_price))*100:.1f}%)\n"
            f"Slots:     {slot}/{max_slots}\n"
        )
        self.send(subject, body)

    def position_closed(self, symbol: str, reason: str, pnl: float,
                        active_positions: list[str]):
        emoji = "🟢" if pnl >= 0 else "🔴"
        subject = f"{emoji} Cierre {reason}: {symbol}  P&L={pnl:+.2f}$"
        body = (
            f"Símbolo:            {symbol}\n"
            f"Motivo cierre:      {reason}\n"
            f"P&L:                {pnl:+.4f}$\n"
            f"Posiciones activas: {', '.join(active_positions) if active_positions else 'ninguna'}\n"
        )
        self.send(subject, body)


#  POSITION MANAGER─
class PositionManager():
    '''
    Manages the maximum number of simultaneous positions and the total capital at risk.

    Configuration:
      max_positions : int    → maximum number of open positions at once (default 5)
      risk_per_trade: float  → $ amount at risk per position (default $200)

    Flow:
      - try_enter(ohlc, tp_pct, sl_pct) → attempts to open a position; sends a notification if it cannot.
      - on_position_closed(symbol)       → call when Ohlc closes a position (TP/SL/hard stop).
      - active_symbols()                 → returns a list of symbols with an open position.
    '''

    def __init__(self,
                 max_positions: int = 5,
                 risk_per_trade: float = 200.0,
                 notifier: Notifier = None):
        self.max_positions = max_positions
        self.risk_per_trade = risk_per_trade
        self.notifier = notifier or Notifier()  # no email by default
        self._lock = threading.Lock()

        # symbol → Ohlc instance for currently open positions
        self._active: dict[str, Ohlc] = {}

    # Queries 
    def active_symbols(self) -> list[str]:
        with self._lock:
            return list(self._active.keys())

    def num_active(self) -> int:
        with self._lock:
            return len(self._active)

    def is_full(self) -> bool:
        with self._lock:
            return len(self._active) >= self.max_positions

    def has_position(self, symbol: str) -> bool:
        with self._lock:
            return symbol in self._active

    # Entry attempt 
    def try_enter(self, ohlc: Ohlc, tp_pct: float = 0.20, sl_pct: float = 0.05) -> bool:
        '''
        Attempts to open a position in `ohlc`.
        Returns True if the position was opened, False if the signal was ignored (with notification).

        Reasons why the entry may be rejected:
          - There is already an open position in that symbol.
          - The maximum number of simultaneous positions has been reached.
          - The symbol is illiquid (is_liquid fails).
        '''
        symbol = ohlc.symbol
        last_price = ohlc.data[-1]["close"] if ohlc.data else 0

        # Already in a position? 
        if self.has_position(symbol):
            return False  # silent, this is expected on every loop iteration

        # Maximum reached?
        if self.is_full():
            self.notifier.signal_missed(
                symbol=symbol,
                reason=f"Máximo de posiciones alcanzado ({self.max_positions}/{self.max_positions})",
                last_price=last_price,
                active_positions=self.active_symbols()
            )
            return False

        # Is the symbol liquid?
        bid = ohlc.connection._bid.get(symbol, 0)
        ask = ohlc.connection._ask.get(symbol, 0)
        if not ohlc.is_liquid(bid, ask):
            self.notifier.signal_missed(
                symbol=symbol,
                reason="Símbolo ilíquido (volumen bajo o spread alto)",
                last_price=last_price,
                active_positions=self.active_symbols()
            )
            return False

        # Set risk and execute entry
        ohlc.risk = self.risk_per_trade
        self._execute_entry(ohlc, tp_pct, sl_pct)
        return True

    def _execute_entry(self, ohlc: Ohlc, tp_pct: float, sl_pct: float):
        '''
        Sends the order, registers the position, and sends a notification.
        '''
        #from src.main.IBClient.Strategy.Strategy import _place_order  
        # # local import to avoid circular import  # local import to avoid circular import: CRASHES, DON'T ADD

        symbol = ohlc.symbol
        order = ohlc.buy_order()
        order_id = ohlc.connection.next_order_id()
        ohlc.entry_order_id = order_id
        ohlc.connection.placeOrder(order_id, ohlc.data_historic.contract, order)
        ohlc.connection.register_order(order_id, ohlc)

        entry_price = ohlc.data[-1]["close"]
        tp_price = entry_price * (1 + tp_pct)
        sl_price = entry_price * (1 - sl_pct)

        # Register as active BEFORE open_position (which is synchronous)
        with self._lock:
            self._active[symbol] = ohlc

        ohlc.open_position(entry_price, tp_price, sl_price)

        # Notify about the entry
        self.notifier.position_opened(
            symbol=symbol,
            entry_price=entry_price,
            tp=tp_price,
            sl=sl_price,
            slot=len(self._active),
            max_slots=self.max_positions
        )
        print(f"[PM] Posición abierta: {symbol} | "
              f"slots={len(self._active)}/{self.max_positions} | "
              f"riesgo=${self.risk_per_trade}")

    # Position close
    def on_position_closed(self, symbol: str, reason: str, pnl: float):
        '''
        Called from Ohlc._close_position and Ohlc.on_hard_stop_filled
        to free up the slot and send a notification.
        '''
        with self._lock:
            self._active.pop(symbol, None)

        self.notifier.position_closed(
            symbol=symbol,
            reason=reason,
            pnl=pnl,
            active_positions=self.active_symbols()
        )
        print(f"[PM] Posición cerrada: {symbol} | "
              f"reason={reason} | pnl={pnl:+.4f}$ | "
              f"slots libres={self.max_positions - len(self._active)}/{self.max_positions}")

    # Status
    def status(self):
        with self._lock:
            print(f"\n[PM STATUS] {len(self._active)}/{self.max_positions} posiciones abiertas")
            for symbol, ohlc in self._active.items():
                print(f"  {symbol}: entry={ohlc.entry_price:.4f} "
                      f"TP={ohlc.tp_price:.4f} SL={ohlc.sl_price:.4f} "
                      f"last={ohlc.last_price}")
                

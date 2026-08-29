import threading
import smtplib
from email.mime.text import MIMEText
from src.main.IBClient.ohlc.Data import Ohlc


# ─────────────────────────────────────────────
#  NOTIFICACIONES
# ─────────────────────────────────────────────
class Notifier():
    '''
    Envía notificaciones cuando el bot no puede entrar en una señal
    por haber llegado al máximo de posiciones.

    Por ahora imprime en consola (siempre funciona) y opcionalmente
    manda un email si configuras las credenciales.
    '''
    def __init__(self, email_from: str = "", email_to: str = "", email_password: str = ""):
        self.email_from = email_from
        self.email_to = email_to
        self.email_password = email_password
        self.email_enabled = bool(email_from and email_to and email_password)

    def send(self, subject: str, body: str):
        # Siempre imprime en consola
        print(f"\n{'='*50}")
        print(f"[NOTIFICACIÓN] {subject}")
        print(f"{body}")
        print(f"{'='*50}\n")

        # Email (opcional)
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


# ─────────────────────────────────────────────
#  POSITION MANAGER
# ─────────────────────────────────────────────
class PositionManager():
    '''
    Gestiona el límite de posiciones simultáneas y el capital total en riesgo.

    Configuración:
      max_positions : int    → máximo de posiciones abiertas a la vez (default 5)
      risk_per_trade: float  → $ arriesgados por posición (default $200)

    Flujo:
      - try_enter(ohlc, tp_pct, sl_pct) → intenta abrir posición; notifica si no puede.
      - on_position_closed(symbol)       → llamar cuando Ohlc cierra posición (TP/SL/stop duro).
      - active_symbols()                 → lista de símbolos con posición abierta.
    '''

    def __init__(self,
                 max_positions: int = 5,
                 risk_per_trade: float = 200.0,
                 notifier: Notifier = None):
        self.max_positions = max_positions
        self.risk_per_trade = risk_per_trade
        self.notifier = notifier or Notifier()  # sin email por defecto
        self._lock = threading.Lock()

        # symbol → Ohlc de posiciones actualmente abiertas
        self._active: dict[str, Ohlc] = {}

    # ─── Consultas ───────────────────────────────────────────────
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

    # ─── Intento de entrada ──────────────────────────────────────
    def try_enter(self, ohlc: Ohlc, tp_pct: float = 0.20, sl_pct: float = 0.05) -> bool:
        '''
        Intenta abrir una posición en `ohlc`.
        Devuelve True si entró, False si fue ignorada (con notificación).

        Motivos por los que no entra:
          - Ya hay posición abierta en ese símbolo.
          - Se ha llegado al máximo de posiciones simultáneas.
          - El símbolo es ilíquido (is_liquid falla).
        '''
        symbol = ohlc.symbol
        last_price = ohlc.data[-1]["close"] if ohlc.data else 0

        # ── ¿Ya tiene posición? ──────────────────────────────────
        if self.has_position(symbol):
            return False  # silencioso, es normal en cada vuelta del loop

        # ── ¿Máximo alcanzado? ───────────────────────────────────
        if self.is_full():
            self.notifier.signal_missed(
                symbol=symbol,
                reason=f"Máximo de posiciones alcanzado ({self.max_positions}/{self.max_positions})",
                last_price=last_price,
                active_positions=self.active_symbols()
            )
            return False

        # ── ¿Líquido? ────────────────────────────────────────────
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

        # ── Asignar riesgo y ejecutar entrada ────────────────────
        ohlc.risk = self.risk_per_trade
        self._execute_entry(ohlc, tp_pct, sl_pct)
        return True

    def _execute_entry(self, ohlc: Ohlc, tp_pct: float, sl_pct: float):
        '''
        Manda la orden, registra la posición y notifica.
        '''
        #from src.main.IBClient.Strategy.Strategy import _place_order  
        # # import local para evitar circular  # import local para evitar circular: CRASHEA NO METER

        symbol = ohlc.symbol
        order = ohlc.buy_order()
        order_id = ohlc.connection.next_order_id()
        ohlc.entry_order_id = order_id
        ohlc.connection.placeOrder(order_id, ohlc.data_historic.contract, order)
        ohlc.connection.register_order(order_id, ohlc)

        entry_price = ohlc.data[-1]["close"]
        tp_price = entry_price * (1 + tp_pct)
        sl_price = entry_price * (1 - sl_pct)

        # Registrar como activa ANTES de open_position (que es síncrono)
        with self._lock:
            self._active[symbol] = ohlc

        ohlc.open_position(entry_price, tp_price, sl_price)

        # Notificar entrada
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

    # ─── Cierre de posición ──────────────────────────────────────
    def on_position_closed(self, symbol: str, reason: str, pnl: float):
        '''
        Llamar desde Ohlc._close_position y Ohlc.on_hard_stop_filled
        para liberar el slot y notificar.
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

    # ─── Estado ──────────────────────────────────────────────────
    def status(self):
        with self._lock:
            print(f"\n[PM STATUS] {len(self._active)}/{self.max_positions} posiciones abiertas")
            for symbol, ohlc in self._active.items():
                print(f"  {symbol}: entry={ohlc.entry_price:.4f} "
                      f"TP={ohlc.tp_price:.4f} SL={ohlc.sl_price:.4f} "
                      f"last={ohlc.last_price}")

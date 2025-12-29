"""
TSI Trading Bot para Interactive Brokers
=========================================
Estrategia: Solo cortos (shorts)

Entrada (tick a tick):
- TSI < -10 (calculado con velas cerradas de 5 min)
- MA70 con pendiente descendente (velas cerradas)
- Precio en tiempo real cruza la MA70 hacia abajo → orden inmediata

Salida (al cierre de vela):
- El high de la vela de 5 min cierra por encima del Parabolic SAR
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from ib_insync import *
import logging

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Conexión IBKR
HOST = '127.0.0.1'
PORT = 7497  # 7496 para real, 7497 para paper trading
CLIENT_ID = 1

# Contrato (Bitcoin en Paxos - 24/7)
SYMBOL = 'BTC'
EXCHANGE = 'PAXOS'
CURRENCY = 'USD'

# Parámetros de la estrategia
TIMEFRAME_MINUTES = 5
MA_PERIOD = 70
TSI_FAST = 13
TSI_SLOW = 25
TSI_SIGNAL = 13  # No usado en esta estrategia, pero disponible
TSI_THRESHOLD = -10
PSAR_AF = 0.02
PSAR_MAX_AF = 0.2

# Cantidad a operar
QUANTITY = 0.1

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('tsi_trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# INDICADORES
# =============================================================================

def calculate_tsi(close: pd.Series, fast: int = 13, slow: int = 25) -> pd.Series:
    """
    Calcula el True Strength Index (TSI).
    TSI = 100 * EMA(EMA(momentum, slow), fast) / EMA(EMA(abs(momentum), slow), fast)
    """
    momentum = close.diff()
    
    # Doble suavizado del momentum
    ema_slow = momentum.ewm(span=slow, adjust=False).mean()
    ema_fast = ema_slow.ewm(span=fast, adjust=False).mean()
    
    # Doble suavizado del momentum absoluto
    abs_ema_slow = momentum.abs().ewm(span=slow, adjust=False).mean()
    abs_ema_fast = abs_ema_slow.ewm(span=fast, adjust=False).mean()
    
    tsi = 100 * ema_fast / abs_ema_fast
    return tsi


def calculate_parabolic_sar(high: pd.Series, low: pd.Series, 
                            af_start: float = 0.02, af_max: float = 0.2) -> pd.Series:
    """
    Calcula el Parabolic SAR.
    """
    length = len(high)
    sar = pd.Series(index=high.index, dtype=float)
    af = af_start
    uptrend = True
    ep = low.iloc[0]  # Extreme point
    sar.iloc[0] = high.iloc[0]
    
    for i in range(1, length):
        if uptrend:
            sar.iloc[i] = sar.iloc[i-1] + af * (ep - sar.iloc[i-1])
            sar.iloc[i] = min(sar.iloc[i], low.iloc[i-1], low.iloc[i-2] if i >= 2 else low.iloc[i-1])
            
            if low.iloc[i] < sar.iloc[i]:
                uptrend = False
                sar.iloc[i] = ep
                ep = low.iloc[i]
                af = af_start
            else:
                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + af_start, af_max)
        else:
            sar.iloc[i] = sar.iloc[i-1] + af * (ep - sar.iloc[i-1])
            sar.iloc[i] = max(sar.iloc[i], high.iloc[i-1], high.iloc[i-2] if i >= 2 else high.iloc[i-1])
            
            if high.iloc[i] > sar.iloc[i]:
                uptrend = True
                sar.iloc[i] = ep
                ep = high.iloc[i]
                af = af_start
            else:
                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + af_start, af_max)
    
    return sar


# =============================================================================
# CLASE PRINCIPAL DEL BOT
# =============================================================================

class TSITradingBot:
    def __init__(self):
        self.ib = IB()
        self.contract = None
        self.bars_5min = pd.DataFrame()
        self.current_bar = {'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0}
        self.bar_start_time = None
        
        # Estado de la estrategia
        self.in_position = False
        self.position_entry_price = None
        self.last_price = None
        self.price_was_above_ma = None  # Para detectar cruce
        
        # Indicadores actuales
        self.current_tsi = None
        self.current_ma70 = None
        self.ma70_slope = None
        self.current_sar = None
        
    def connect(self):
        """Conecta a TWS/IB Gateway."""
        logger.info(f"Conectando a IBKR en {HOST}:{PORT}...")
        self.ib.connect(HOST, PORT, clientId=CLIENT_ID)
        logger.info("Conectado exitosamente")
        
        # Definir contrato Bitcoin
        self.contract = Crypto(SYMBOL, EXCHANGE, CURRENCY)
        self.ib.qualifyContracts(self.contract)
        logger.info(f"Contrato: {self.contract.localSymbol}")
        
    def disconnect(self):
        """Desconecta de IBKR."""
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Desconectado de IBKR")
    
    def load_historical_data(self):
        """Carga datos históricos para calcular indicadores iniciales."""
        logger.info("Cargando datos históricos...")
        
        # Necesitamos suficientes barras para calcular MA70 + TSI
        bars_needed = MA_PERIOD + TSI_SLOW + 50  # Margen extra
        
        bars = self.ib.reqHistoricalData(
            self.contract,
            endDateTime='',
            durationStr='2 D',  # Pedir 2 días de datos
            barSizeSetting=f'{TIMEFRAME_MINUTES} mins',
            whatToShow='AGGTRADES',  # AGGTRADES para crypto
            useRTH=False,
            formatDate=1
        )
        
        if not bars:
            raise ValueError("No se pudieron obtener datos históricos")
        
        # Convertir a DataFrame
        self.bars_5min = util.df(bars)
        self.bars_5min.set_index('date', inplace=True)
        
        logger.info(f"Cargadas {len(self.bars_5min)} barras de {TIMEFRAME_MINUTES} min")
        logger.info(f"Desde: {self.bars_5min.index[0]} hasta: {self.bars_5min.index[-1]}")
        
        # Calcular indicadores iniciales
        self._update_indicators()
        
    def _update_indicators(self):
        """Recalcula los indicadores con los datos actuales."""
        if len(self.bars_5min) < MA_PERIOD:
            return
            
        # MA70
        self.bars_5min['MA70'] = self.bars_5min['close'].rolling(MA_PERIOD).mean()
        
        # Pendiente de MA70 (comparando con valor anterior)
        self.bars_5min['MA70_slope'] = self.bars_5min['MA70'].diff()
        
        # TSI
        self.bars_5min['TSI'] = calculate_tsi(
            self.bars_5min['close'], 
            fast=TSI_FAST, 
            slow=TSI_SLOW
        )
        
        # Parabolic SAR
        self.bars_5min['PSAR'] = calculate_parabolic_sar(
            self.bars_5min['high'],
            self.bars_5min['low'],
            af_start=PSAR_AF,
            af_max=PSAR_MAX_AF
        )
        
        # Actualizar valores actuales
        self.current_ma70 = self.bars_5min['MA70'].iloc[-1]
        self.ma70_slope = self.bars_5min['MA70_slope'].iloc[-1]
        self.current_tsi = self.bars_5min['TSI'].iloc[-1]
        self.current_sar = self.bars_5min['PSAR'].iloc[-1]
        
        logger.debug(f"Indicadores - MA70: {self.current_ma70:.2f}, "
                    f"Slope: {self.ma70_slope:.4f}, TSI: {self.current_tsi:.2f}, "
                    f"SAR: {self.current_sar:.2f}")
    
    def _get_bar_start_time(self, timestamp: datetime) -> datetime:
        """Calcula el inicio de la barra de 5 minutos para un timestamp dado."""
        minutes = (timestamp.minute // TIMEFRAME_MINUTES) * TIMEFRAME_MINUTES
        return timestamp.replace(minute=minutes, second=0, microsecond=0)
    
    def _on_tick(self, ticker: Ticker):
        """Callback para cada tick recibido."""
        if ticker.last is None or np.isnan(ticker.last):
            return
            
        price = ticker.last
        now = datetime.now()
        
        # Actualizar barra actual
        bar_start = self._get_bar_start_time(now)
        
        if self.bar_start_time != bar_start:
            # Nueva barra - cerrar la anterior y abrir nueva
            if self.bar_start_time is not None and self.current_bar['open'] is not None:
                self._close_bar()
            
            self.bar_start_time = bar_start
            self.current_bar = {
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': 0
            }
            logger.info(f"Nueva barra iniciada: {bar_start}")
        else:
            # Actualizar barra actual
            self.current_bar['high'] = max(self.current_bar['high'], price)
            self.current_bar['low'] = min(self.current_bar['low'], price)
            self.current_bar['close'] = price
        
        self.last_price = price
        
        # Verificar condiciones de trading
        self._check_entry_conditions(price)
        
    def _close_bar(self):
        """Cierra la barra actual y la añade al histórico."""
        if self.current_bar['open'] is None:
            return
            
        # Añadir barra al DataFrame
        new_bar = pd.DataFrame([{
            'open': self.current_bar['open'],
            'high': self.current_bar['high'],
            'low': self.current_bar['low'],
            'close': self.current_bar['close'],
            'volume': self.current_bar['volume']
        }], index=[self.bar_start_time])
        
        self.bars_5min = pd.concat([self.bars_5min, new_bar])
        
        # Mantener solo las últimas N barras para no consumir memoria
        max_bars = MA_PERIOD + TSI_SLOW + 100
        if len(self.bars_5min) > max_bars:
            self.bars_5min = self.bars_5min.iloc[-max_bars:]
        
        # Recalcular indicadores
        self._update_indicators()
        
        logger.info(f"Barra cerrada: O={self.current_bar['open']:.2f} "
                   f"H={self.current_bar['high']:.2f} L={self.current_bar['low']:.2f} "
                   f"C={self.current_bar['close']:.2f}")
        
        # Verificar salida al cierre de vela
        self._check_exit_conditions()
    
    def _check_entry_conditions(self, price: float):
        """Verifica condiciones de entrada en tiempo real."""
        if self.in_position:
            return
            
        if self.current_ma70 is None or self.current_tsi is None:
            return
        
        # Determinar si el precio está por encima o por debajo de MA70
        price_above_ma = price > self.current_ma70
        
        # Inicializar estado si es la primera vez
        if self.price_was_above_ma is None:
            self.price_was_above_ma = price_above_ma
            return
        
        # Detectar cruce hacia abajo
        crossed_down = self.price_was_above_ma and not price_above_ma
        
        # Actualizar estado
        self.price_was_above_ma = price_above_ma
        
        if crossed_down:
            logger.info(f"Cruce detectado: precio {price:.2f} cruzó MA70 {self.current_ma70:.2f}")
            
            # Verificar otras condiciones
            ma_descending = self.ma70_slope < 0
            tsi_below_threshold = self.current_tsi < TSI_THRESHOLD
            
            logger.info(f"Condiciones - MA descendente: {ma_descending} (slope: {self.ma70_slope:.4f}), "
                       f"TSI < {TSI_THRESHOLD}: {tsi_below_threshold} (TSI: {self.current_tsi:.2f})")
            
            if ma_descending and tsi_below_threshold:
                self._enter_short(price)
    
    def _check_exit_conditions(self):
        """Verifica condiciones de salida al cierre de vela."""
        if not self.in_position:
            return
            
        if self.current_sar is None:
            return
        
        # Salida: high de la vela cerrada >= SAR
        last_high = self.bars_5min['high'].iloc[-1]
        
        if last_high >= self.current_sar:
            logger.info(f"Señal de salida: High {last_high:.2f} >= SAR {self.current_sar:.2f}")
            self._exit_short()
    
    def _enter_short(self, price: float):
        """Ejecuta entrada en corto."""
        logger.info(f">>> ENTRADA CORTO a {price:.2f}")
        
        order = MarketOrder('SELL', QUANTITY)
        trade = self.ib.placeOrder(self.contract, order)
        
        # Esperar confirmación
        self.ib.sleep(1)
        
        if trade.orderStatus.status == 'Filled':
            self.in_position = True
            self.position_entry_price = trade.orderStatus.avgFillPrice
            logger.info(f"Orden ejecutada: SELL {QUANTITY} @ {self.position_entry_price:.2f}")
        else:
            logger.warning(f"Estado de orden: {trade.orderStatus.status}")
    
    def _exit_short(self):
        """Ejecuta salida del corto."""
        logger.info(f">>> SALIDA CORTO")
        
        order = MarketOrder('BUY', QUANTITY)
        trade = self.ib.placeOrder(self.contract, order)
        
        # Esperar confirmación
        self.ib.sleep(1)
        
        if trade.orderStatus.status == 'Filled':
            exit_price = trade.orderStatus.avgFillPrice
            pnl = self.position_entry_price - exit_price
            logger.info(f"Orden ejecutada: BUY {QUANTITY} @ {exit_price:.2f}")
            logger.info(f"PnL: {pnl:.2f} puntos")
            
            self.in_position = False
            self.position_entry_price = None
        else:
            logger.warning(f"Estado de orden: {trade.orderStatus.status}")
    
    def run(self):
        """Ejecuta el bot."""
        try:
            self.connect()
            self.load_historical_data()
            
            # Suscribirse a datos en tiempo real
            logger.info("Suscribiendo a datos en tiempo real...")
            ticker = self.ib.reqMktData(self.contract, '', False, False)
            ticker.updateEvent += self._on_tick
            
            logger.info("Bot iniciado. Esperando señales...")
            if self.current_ma70 is not None:
                logger.info(f"Indicadores actuales - MA70: {self.current_ma70:.2f}, "
                           f"TSI: {self.current_tsi:.2f}, SAR: {self.current_sar:.2f}")
            else:
                logger.warning("Indicadores no disponibles - insuficientes datos históricos")
            
            # Mantener el bot corriendo
            self.ib.run()
            
        except KeyboardInterrupt:
            logger.info("Bot detenido por el usuario")
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
        finally:
            self.disconnect()


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    bot = TSITradingBot()
    bot.run()
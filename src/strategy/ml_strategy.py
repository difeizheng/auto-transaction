"""
机器学习策略模块
使用 XGBoost 等模型进行预测和选股
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import joblib
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

import xgboost as xgb

from src.strategy.base_strategy import BaseStrategy, Signal, BaseMultiAssetStrategy
from src.data_collector.data_manager import data_manager
from src.utils.helpers import calculate_ma, calculate_rsi, calculate_macd, calculate_momentum, calculate_volatility
from config.logging_config import strategy_logger


class MLStrategy(BaseMultiAssetStrategy):
    """
    机器学习选股策略

    使用机器学习模型预测股票未来收益率，选取预测值最高的股票
    """

    def __init__(
        self,
        name: str = "ml_strategy",
        model_type: str = "xgboost",
        lookback_days: int = 60,
        predict_horizon: int = 5,
        top_n: int = 10,
        rebalance_days: int = 5
    ):
        """
        初始化 ML 策略

        Args:
            name: 策略名称
            model_type: 模型类型 (xgboost/random_forest/logistic)
            lookback_days: 回看天数
            predict_horizon: 预测周期 (天)
            top_n: 选取预测值最高的 N 只股票
            rebalance_days: 调仓周期
        """
        super().__init__(name)

        self.model_type = model_type
        self.lookback_days = lookback_days
        self.predict_horizon = predict_horizon
        self.top_n = top_n
        self.rebalance_days = rebalance_days

        # 模型和 scaler
        self.model = None
        self.scaler = StandardScaler()

        # 特征列表
        self.feature_columns = [
            'ma_ratio',      # 均线比率
            'rsi',           # RSI
            'macd',          # MACD
            'momentum_5',    # 5 日动量
            'momentum_10',   # 10 日动量
            'momentum_20',   # 20 日动量
            'volatility',    # 波动率
            'volume_ratio'   # 成交量比率
        ]

        # 状态变量
        self.current_holdings: List[str] = []
        self.last_rebalance_date: str = ""
        self.price_history: Dict[str, pd.DataFrame] = {}
        self_predictions: Dict[str, float] = {}

    def on_init(self):
        """策略初始化"""
        super().on_init()
        self.current_holdings = []
        self.last_rebalance_date = ""
        self.price_history = {}
        self.predictions = {}

        # 初始化或加载模型
        self._init_model()

    def _init_model(self):
        """初始化模型"""
        if self.model_type == "xgboost":
            self.model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                use_label_encoder=False,
                eval_metric='logloss'
            )
        elif self.model_type == "random_forest":
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=6,
                random_state=42
            )
        elif self.model_type == "logistic":
            self.model = LogisticRegression(
                max_iter=1000,
                random_state=42
            )
        else:
            raise ValueError(f"不支持的模型类型：{self.model_type}")

        strategy_logger.info(f"初始化模型：{self.model_type}")

    def train_model(self, training_data: pd.DataFrame):
        """
        训练模型

        Args:
            training_data: 训练数据
                          包含特征列和 target 列
        """
        strategy_logger.info(f"开始训练模型，数据量：{len(training_data)}")

        # 准备数据
        X = training_data[self.feature_columns].dropna()
        y = training_data.loc[X.index, 'target']

        if len(X) < 100:
            strategy_logger.warning("训练数据不足")
            return

        # 划分训练集和测试集
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, shuffle=False
        )

        # 标准化
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # 训练模型
        self.model.fit(X_train_scaled, y_train)

        # 评估
        y_pred = self.model.predict(X_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)
        strategy_logger.info(f"模型准确率：{accuracy:.4f}")

        # 打印分类报告
        report = classification_report(y_test, y_pred, output_dict=True)
        strategy_logger.info(f"F1 Score: {report['weighted avg']['f1-score']:.4f}")

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        """
        预测

        Args:
            features: 特征数据

        Returns:
            预测概率
        """
        if self.model is None:
            raise ValueError("模型未训练")

        X_scaled = self.scaler.transform(features)
        predictions = self.model.predict_proba(X_scaled)

        # 返回上涨概率
        if predictions.shape[1] > 1:
            return predictions[:, 1]
        return predictions.flatten()

    def _extract_features(self, ts_code: str, df: pd.DataFrame) -> Optional[Dict[str, float]]:
        """
        从行情数据提取特征

        Args:
            ts_code: 股票代码
            df: 行情 DataFrame

        Returns:
            特征字典
        """
        if len(df) < self.lookback_days:
            return None

        close = df['close']
        vol = df['vol']

        features = {}

        # 1. 均线比率 (当前价格/20 日均线)
        ma20 = close.rolling(20).mean()
        features['ma_ratio'] = close.iloc[-1] / ma20.iloc[-1] - 1

        # 2. RSI
        rsi_series = calculate_rsi(close, 14)
        features['rsi'] = rsi_series.iloc[-1] / 100.0  # 归一化到 0-1

        # 3. MACD
        macd_data = calculate_macd(close, 12, 26, 9)
        features['macd'] = macd_data['macd'].iloc[-1]

        # 4. 动量指标
        features['momentum_5'] = calculate_momentum(close, 5).iloc[-1]
        features['momentum_10'] = calculate_momentum(close, 10).iloc[-1]
        features['momentum_20'] = calculate_momentum(close, 20).iloc[-1]

        # 5. 波动率
        features['volatility'] = calculate_volatility(close, 20).iloc[-1]

        # 6. 成交量比率 (当日成交量/5 日均量)
        vol_ma5 = vol.rolling(5).mean()
        features['volume_ratio'] = vol.iloc[-1] / vol_ma5.iloc[-1] - 1

        # 处理 NaN 和无穷值
        for key, value in features.items():
            if pd.isna(value) or np.isinf(value):
                features[key] = 0.0

        return features

    def _prepare_training_data(
        self,
        ts_codes: List[str],
        end_date: str
    ) -> pd.DataFrame:
        """
        准备训练数据

        Args:
            ts_codes: 股票代码列表
            end_date: 截止日期

        Returns:
            训练数据 DataFrame
        """
        all_data = []

        for ts_code in ts_codes[:100]:  # 限制数量
            df = data_manager.get_daily_quotes(ts_code)
            if df.empty or len(df) < self.lookback_days + self.predict_horizon:
                continue

            df = df.copy()
            df['trade_date'] = pd.to_datetime(df['trade_date'])
            df = df.sort_values('trade_date').reset_index(drop=True)

            # 计算 target: 未来 N 日收益率
            df['future_return'] = df['close'].shift(-self.predict_horizon) / df['close'] - 1
            df['target'] = (df['future_return'] > 0).astype(int)  # 二分类：涨/跌

            # 提取特征
            for i in range(self.lookback_days, len(df) - self.predict_horizon):
                hist_df = df.iloc[i - self.lookback_days:i]
                features = self._extract_features(ts_code, hist_df)

                if features:
                    features['ts_code'] = ts_code
                    features['trade_date'] = df.iloc[i]['trade_date']
                    features['target'] = df.iloc[i]['target']
                    all_data.append(features)

        if not all_data:
            return pd.DataFrame()

        return pd.DataFrame(all_data)

    def _should_rebalance(self, current_date: str) -> bool:
        """判断是否需要调仓"""
        if not self.last_rebalance_date:
            return True

        try:
            last_date = datetime.strptime(self.last_rebalance_date, "%Y%m%d")
            curr_date = datetime.strptime(current_date, "%Y%m%d")
            return (curr_date - last_date).days >= self.rebalance_days
        except ValueError:
            return False

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        if not self.initialized:
            self.on_init()

        signals = []

        # 检查是否需要调仓
        if not self._should_rebalance(current_date):
            return signals

        # 更新价格历史
        for ts_code, bar in data.items():
            if ts_code not in self.price_history:
                self.price_history[ts_code] = []

            self.price_history[ts_code].append({
                'trade_date': current_date,
                'open': bar.get('open', 0),
                'high': bar.get('high', 0),
                'low': bar.get('low', 0),
                'close': bar.get('close', 0),
                'vol': bar.get('vol', 0)
            })

            # 保留足够的数据
            if len(self.price_history[ts_code]) > self.lookback_days * 2:
                self.price_history[ts_code] = self.price_history[ts_code][-self.lookback_days:]

        # 为每只股票预测
        predictions = {}
        for ts_code in self.price_history.keys():
            if len(self.price_history[ts_code]) < self.lookback_days:
                continue

            df = pd.DataFrame(self.price_history[ts_code])
            features = self._extract_features(ts_code, df)

            if features:
                features_df = pd.DataFrame([features])[self.feature_columns]

                try:
                    pred = self.predict(features_df)
                    predictions[ts_code] = pred[0] if len(pred) > 0 else 0
                except Exception:
                    predictions[ts_code] = 0.5

        if not predictions:
            return signals

        # 选取预测值最高的股票
        sorted_predictions = sorted(predictions.items(), key=lambda x: x[1], reverse=True)
        top_stocks = [ts for ts, pred in sorted_predictions[:self.top_n] if pred > 0.5]

        # 生成调仓信号
        signals = self._generate_rebalance_signals(
            target_holdings=top_stocks,
            current_holdings=self.current_holdings,
            data=data
        )

        self.current_holdings = top_stocks
        self.last_rebalance_date = current_date

        return signals

    def _generate_rebalance_signals(
        self,
        target_holdings: List[str],
        current_holdings: List[str],
        data: Dict[str, Any]
    ) -> List[Signal]:
        """生成调仓信号"""
        signals = []

        to_buy = set(target_holdings) - set(current_holdings)
        to_sell = set(current_holdings) - set(target_holdings)

        capital = self.engine.capital if self.engine else 1000000

        # 买入信号
        for ts_code in to_buy:
            if ts_code in data:
                price = data[ts_code].get('close', 0)
                if price > 0:
                    weight = 1.0 / len(target_holdings) if target_holdings else 0
                    target_value = capital * weight
                    volume = int(target_value / price / 100) * 100

                    if volume > 0:
                        signals.append(self.generate_signal(
                            ts_code=ts_code,
                            direction='buy',
                            price=price,
                            volume=volume,
                            weight=weight,
                            reason=f"ML 模型买入 (预测上涨概率：{self.predictions.get(ts_code, 0):.2%})"
                        ))

        # 卖出信号
        for ts_code in to_sell:
            if ts_code in data:
                price = data[ts_code].get('close', 0)
                signals.append(self.generate_signal(
                    ts_code=ts_code,
                    direction='sell',
                    price=price,
                    volume=100000,
                    reason="ML 模型卖出"
                ))

        return signals

    def save_model(self, path: str):
        """保存模型"""
        model_path = Path(path)
        model_path.parent.mkdir(exist_ok=True, parents=True)

        joblib.dump({
            'model': self.model,
            'scaler': self.scaler,
            'feature_columns': self.feature_columns
        }, model_path)

        strategy_logger.info(f"模型保存到 {model_path}")

    def load_model(self, path: str):
        """加载模型"""
        model_path = Path(path)

        if not model_path.exists():
            strategy_logger.warning(f"模型文件不存在：{model_path}")
            return False

        data = joblib.load(model_path)
        self.model = data['model']
        self.scaler = data['scaler']
        self.feature_columns = data['feature_columns']

        strategy_logger.info(f"模型从 {model_path} 加载")
        return True


# 简单的 LSTM 预测策略 (需要 TensorFlow/Keras)
class LSTMPredictionStrategy(BaseStrategy):
    """
    LSTM 时间序列预测策略

    注意：需要安装 tensorflow 才能使用
    """

    def __init__(
        self,
        name: str = "lstm_strategy",
        lookback_days: int = 60,
        predict_horizon: int = 5
    ):
        super().__init__(name)
        self.lookback_days = lookback_days
        self.predict_horizon = predict_horizon
        self.model = None
        self.price_history: Dict[str, List[float]] = {}

    def build_lstm_model(self, input_shape: tuple) -> Any:
        """
        构建 LSTM 模型

        需要安装 tensorflow
        """
        try:
            from tensorflow.keras.models import Sequential
            from tensorflow.keras.layers import LSTM, Dense, Dropout
        except ImportError:
            strategy_logger.error("需要安装 TensorFlow")
            return None

        model = Sequential([
            LSTM(50, return_sequences=True, input_shape=input_shape),
            Dropout(0.2),
            LSTM(50),
            Dropout(0.2),
            Dense(25),
            Dense(1)
        ])

        model.compile(optimizer='adam', loss='mse')
        return model

    def on_bar(self, data: Dict[str, Any], current_date: str) -> List[Signal]:
        """K 线数据回调"""
        # 简化实现，实际需要完整的 LSTM 训练和预测逻辑
        return []

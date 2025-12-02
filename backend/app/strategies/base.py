from abc import ABC, abstractmethod
from typing import Tuple, Type, List
import pandas as pd
from pydantic import BaseModel

class BaseStrategy(ABC):
    """Abstract Base Class for all trading strategies."""
    strategy_id: str
    name: str
    params_model: Type[BaseModel]

    @abstractmethod
    def generate_signals(
        self, 
        df: pd.DataFrame, 
        params: BaseModel
    ) -> Tuple[pd.Series, pd.Series, List[pd.Series]]:
        """
        Calculates entries and exits using vectorbt indicators.
        Returns: Tuple[pd.Series (entries), pd.Series (exits), List[pd.Series] (indicators for plotting)]
        """
        pass
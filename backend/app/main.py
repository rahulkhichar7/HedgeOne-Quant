from fastapi import FastAPI
from backend.app.api.v1.data import router as data_router
from backend.app.api.v1.backtest import router as backtest_router
from backend.app.api.v1.user import router as user_router

app = FastAPI(title="HedgeOne Quant API")

# Register all routers
app.include_router(data_router, prefix="/api/v1/data")
app.include_router(backtest_router, prefix="/api/v1/backtest")
app.include_router(user_router, prefix="/api/v1/user")

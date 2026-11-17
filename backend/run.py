"""Start the HedgeOne server:   python run.py   (from the backend/ folder)"""
import os
import sys
from pathlib import Path

import uvicorn

HERE = Path(__file__).resolve().parent
os.chdir(HERE)
sys.path.insert(0, str(HERE))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")),
                reload=True, reload_dirs=[str(HERE / "app"), str(HERE / "strategies")])

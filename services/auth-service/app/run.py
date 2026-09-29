import uvicorn

from .main import app

uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None, access_log=False)

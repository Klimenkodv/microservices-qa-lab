import uvicorn

uvicorn.run("app.main:app", host="0.0.0.0", port=8003, log_config=None, access_log=False)

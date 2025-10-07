from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import os

app = FastAPI()

def _auth(password: str) -> None:
    if password != os.getenv("DASH_PASSWORD", ""):
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/")
async def root():
    return {"status": "ok"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        await websocket.send_json({"hello": "world"})
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        pass

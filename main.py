import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from llama_agent import LlamaFraudAgent
from ml_engine import MLFraudDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

QUEUE_CAPACITY = 1000
transaction_queue: asyncio.Queue[tuple[dict[str, Any], asyncio.Future | None]] = (
    asyncio.Queue(maxsize=QUEUE_CAPACITY)
)
ml_detector = MLFraudDetector()
try:
    llama_agent: LlamaFraudAgent | None = LlamaFraudAgent()
except ValueError as exc:
    logger.warning("Agent Groq indisponible : %s", exc)
    llama_agent = None

system_state = {
    "fail_safe_active": llama_agent is None,
    "reason": (
        "Agent Groq indisponible : protection locale activée"
        if llama_agent is None
        else "Mode cloud nominal"
    ),
}


class PaymentNotification(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    transaction_id: str = Field(
        default_factory=lambda: f"tx_{uuid.uuid4().hex[:12]}",
        min_length=1,
        max_length=128,
    )
    amount: float = Field(gt=0, le=1_000_000)
    velocity: int = Field(ge=0, le=1_000_000)
    country_risk: int = Field(ge=0, le=2)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        min_length=1,
        max_length=64,
    )


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)
        await websocket.send_text(json.dumps({
            "type": "SYSTEM_STATE",
            "fail_safe_active": system_state["fail_safe_active"],
            "reason": system_state["reason"],
        }))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        failed_connections = []
        serialized = json.dumps(message)
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(serialized)
            except Exception:
                logger.warning("Connexion WebSocket perdue pendant la diffusion.")
                failed_connections.append(connection)
        for connection in failed_connections:
            self.disconnect(connection)


manager = ConnectionManager()


async def set_fail_safe(reason: str) -> None:
    was_active = system_state["fail_safe_active"]
    system_state["fail_safe_active"] = True
    system_state["reason"] = reason
    if not was_active:
        await manager.broadcast({
            "type": "SYSTEM_STATE",
            "fail_safe_active": True,
            "reason": reason,
        })


async def process_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    analysis = await asyncio.to_thread(
        ml_detector.predict,
        transaction,
        force_local_failsafe=system_state["fail_safe_active"],
    )
    ai_report = None

    if analysis["status"] == "GREY_ZONE":
        if system_state["fail_safe_active"] or llama_agent is None:
            if llama_agent is None and not system_state["fail_safe_active"]:
                await set_fail_safe("Agent Groq non configuré : protection locale activée")
            analysis = await asyncio.to_thread(
                ml_detector.predict, transaction, force_local_failsafe=True
            )
        else:
            try:
                ai_result = await asyncio.to_thread(
                    llama_agent.analyze_grey_zone, transaction, analysis["score"]
                )
                decision = ai_result["decision"]
                analysis["action"] = decision
                analysis["status"] = {
                    "BLOCK": "BLOCKED_AI",
                    "CHALLENGE_2FA": "CHALLENGE_2FA",
                    "ALLOW": "SAFE_AI",
                }[decision]
                ai_report = ai_result["aml_report"]
                analysis["reason"] = f"Arbitrage Meta Llama : {ai_report}"
            except Exception:
                logger.exception("Échec de l'arbitrage cloud; activation du mode local.")
                await set_fail_safe("Erreur Groq : protection locale activée")
                analysis = await asyncio.to_thread(
                    ml_detector.predict, transaction, force_local_failsafe=True
                )
                ai_report = (
                    "Le service cloud est indisponible. La transaction a été "
                    "réévaluée par la politique locale de secours."
                )

    payload = {
        "type": "TRANSACTION_PROCESSED",
        "transaction": transaction,
        "analysis": analysis,
        "ai_report": ai_report,
        "fail_safe_mode": system_state["fail_safe_active"],
    }
    await manager.broadcast(payload)
    return payload


async def transaction_worker() -> None:
    while True:
        transaction, result_future = await transaction_queue.get()
        try:
            payload = await process_transaction(transaction)
            if result_future is not None and not result_future.done():
                result_future.set_result(payload)
        except Exception as exc:
            logger.exception("Échec du traitement de la transaction.")
            if result_future is not None and not result_future.done():
                result_future.set_exception(exc)
        finally:
            transaction_queue.task_done()


async def background_transaction_generator() -> None:
    while True:
        await asyncio.sleep(3)
        await transaction_queue.put((ml_detector.generate_mock_transaction(), None))


@asynccontextmanager
async def lifespan(_: FastAPI):
    worker_task = asyncio.create_task(transaction_worker())
    generator_task = asyncio.create_task(background_transaction_generator())
    logger.info("Serveur Meta ShieldFin démarré; file de traitement active.")
    try:
        yield
    finally:
        generator_task.cancel()
        worker_task.cancel()
        await asyncio.gather(generator_task, worker_task, return_exceptions=True)


app = FastAPI(title="Meta ShieldFin API", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "queue_size": transaction_queue.qsize(),
        "fail_safe_active": system_state["fail_safe_active"],
        "cloud_available": llama_agent is not None and not system_state["fail_safe_active"],
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "TOGGLE_FAIL_SAFE":
                system_state["fail_safe_active"] = not system_state["fail_safe_active"]
                system_state["reason"] = (
                    "Simulation de panne cloud activée"
                    if system_state["fail_safe_active"]
                    else "Mode cloud nominal"
                )
                await manager.broadcast({
                    "type": "SYSTEM_STATE",
                    "fail_safe_active": system_state["fail_safe_active"],
                    "reason": system_state["reason"],
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/api/toggle-failsafe")
async def toggle_failsafe() -> dict[str, Any]:
    system_state["fail_safe_active"] = not system_state["fail_safe_active"]
    system_state["reason"] = (
        "Simulation de panne cloud activée"
        if system_state["fail_safe_active"]
        else "Mode cloud nominal"
    )
    await manager.broadcast({
        "type": "SYSTEM_STATE",
        "fail_safe_active": system_state["fail_safe_active"],
        "reason": system_state["reason"],
    })
    return {
        "success": True,
        "fail_safe_active": system_state["fail_safe_active"],
        "reason": system_state["reason"],
    }


@app.post("/api/webhook/payment-notification")
async def receive_payment_webhook(transaction: PaymentNotification) -> dict[str, Any]:
    transaction_data = transaction.model_dump()
    result_future = asyncio.get_running_loop().create_future()
    try:
        transaction_queue.put_nowait((transaction_data, result_future))
    except asyncio.QueueFull as exc:
        raise HTTPException(
            status_code=503,
            detail="File de traitement saturée; réessayez ultérieurement.",
            headers={"Retry-After": "1"},
        ) from exc

    result = await result_future
    return {"status": "success", "analysis": result["analysis"]}


frontend_dir = Path(__file__).parent / "frontend"
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

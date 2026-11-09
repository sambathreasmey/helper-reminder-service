import os
import logging
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
import httpx
import uvicorn
from pytz import timezone

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Helper Reminder Bot", version="1.0.0")

# Telegram Bot Token from Environment
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")

# Initialize APScheduler
# Note: For production persistence across restarts, swap MemoryJobStore for SQLAlchemyJobStore
jobstores = {'default': MemoryJobStore()}
scheduler = AsyncIOScheduler(jobstores=jobstores)


# --- Helper to Send Telegram Notifications ---
async def send_telegram_message(chat_id: int, text: str):
    """Sends a notification directly via the Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info(f"Successfully sent reminder to chat_id {chat_id}")
            else:
                logger.error(f"Telegram API Error: {response.text}")
        except Exception as e:
            logger.error(f"Exception while sending telegram message: {e}")


# --- Pydantic Schema for Dynamic Reminders ---
class ReminderRequest(BaseModel):
    chat_id: int
    message: str
    hour: int
    minute: int


# --- FastAPI Lifecycle Events ---
@app.on_event("startup")
async def startup_event():
    scheduler.start()
    logger.info("APScheduler started successfully and running in background.")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    logger.info("APScheduler shut down safely.")


# --- Health Check / Ping Endpoint ---
@app.get("/", status_code=status.HTTP_200_OK)
async def root():
    return {
        "status": "online",
        "service": "helper-reminder-bot",
        "active_jobs": len(scheduler.get_jobs())
    }


# --- Dynamic Scheduler Endpoint ---
@app.post("/reminders/schedule", status_code=status.HTTP_201_CREATED)
async def schedule_reminder(data: ReminderRequest):
    """
    Dynamically register a daily reminder job.
    Can be triggered via Telegram bot commands or webhook handlers.
    """
    # Create a unique job ID based on user and time
    job_id = f"reminder_{data.chat_id}_{data.hour:02d}_{data.minute:02d}"

    LOCAL_TZ = timezone('Asia/Phnom_Penh')
    
    # Add cron-based job to the scheduler
    scheduler.add_job(
        send_telegram_message,
        'cron',
        hour=data.hour,
        minute=data.minute,
        timezone=LOCAL_TZ,
        args=[data.chat_id, f"🔔 **Reminder:** {data.message}"],
        id=job_id,
        replace_existing=True
    )
    
    logger.info(f"Scheduled daily reminder for chat {data.chat_id} at {data.hour:02d}:{data.minute:02d}")
    return {
        "status": "success",
        "job_id": job_id,
        "detail": f"Reminder set for daily at {data.hour:02d}:{data.minute:02d}"
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
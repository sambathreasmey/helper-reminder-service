import os
import logging
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from pytz import timezone
import httpx
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Helper Reminder Bot", version="1.0.0")

# Telegram Bot Token from Environment
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")

# Define local timezone (Phnom Penh / Indochina Time)
LOCAL_TZ = timezone('Asia/Phnom_Penh')

# Initialize APScheduler with in-memory job store
jobstores = {'default': MemoryJobStore()}
scheduler = AsyncIOScheduler(jobstores=jobstores, timezone=LOCAL_TZ)


# --- Helper to Send Telegram Notifications ---
async def send_telegram_message(chat_id: int, text: str):
    """Sends a notification directly via the Telegram Bot API."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info(f"Successfully sent reminder to chat_id {chat_id}")
            else:
                logger.error(f"Telegram API Error: {response.text}")
        except Exception as e:
            logger.error(f"Exception while sending telegram message: {e}")


# --- Pydantic Schemas ---
class ReminderRequest(BaseModel):
    chat_id: int
    message: str
    hour: int
    minute: int

class IntervalReminderRequest(BaseModel):
    chat_id: int
    message: str
    minutes: int = 15  # Default to every 15 minutes


# --- FastAPI Lifecycle Events ---
@app.on_event("startup")
async def startup_event():
    scheduler.start()
    logger.info("APScheduler started successfully and running in background.")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    logger.info("APScheduler shut down safely.")


# --- Health Check / Keep-Alive Endpoint (For cron-job.org) ---
@app.get("/", status_code=status.HTTP_200_OK)
async def root():
    logger.info("Keep-alive ping received.")
    return {
        "status": "online",
        "service": "helper-reminder-bot",
        "active_jobs": len(scheduler.get_jobs())
    }

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "healthy"}


# --- 1. Daily Cron Reminder Endpoint ---
@app.post("/reminders/schedule", status_code=status.HTTP_201_CREATED)
async def schedule_reminder(data: ReminderRequest):
    """
    Register a daily cron-based reminder job at a specific time.
    """
    job_id = f"reminder_{data.chat_id}_{data.hour:02d}_{data.minute:02d}"
    
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
    
    logger.info(f"Scheduled daily reminder for chat {data.chat_id} at {data.hour:02d}:{data.minute:02d} local time")
    return {
        "status": "success",
        "job_id": job_id,
        "detail": f"Reminder set for daily at {data.hour:02d}:{data.minute:02d}"
    }


# --- 2. Recurring Interval Reminder Endpoint (e.g. Every 15 mins) ---
@app.post("/reminders/schedule-interval", status_code=status.HTTP_201_CREATED)
async def schedule_interval_reminder(data: IntervalReminderRequest):
    """
    Register a recurring interval job (e.g., every 15 minutes for drinking water).
    """
    job_id = f"interval_reminder_{data.chat_id}_{data.minutes}m"
    
    scheduler.add_job(
        send_telegram_message,
        'interval',
        minutes=data.minutes,
        timezone=LOCAL_TZ,
        args=[data.chat_id, f"💧 **Hydration Alert:** {data.message}"],
        id=job_id,
        replace_existing=True
    )
    
    logger.info(f"Scheduled recurring reminder for chat {data.chat_id} every {data.minutes} minutes.")
    return {
        "status": "success",
        "job_id": job_id,
        "detail": f"Reminder set to repeat every {data.minutes} minutes."
    }


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
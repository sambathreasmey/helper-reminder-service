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

app = FastAPI(title="Helper Reminder Bot - Full CRUD", version="2.0.0")

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


# --- Health Check / Keep-Alive Endpoint ---
@app.get("/", status_code=status.HTTP_200_OK)
async def root():
    logger.info("Keep-alive ping received.")
    return {
        "status": "online",
        "service": "helper-reminder-bot",
        "active_jobs": len(scheduler.get_jobs())
    }


# ==========================================
# --- CRUD OPERATIONS FOR REMINDERS ---
# ==========================================

# --- 1. CREATE (Daily Cron Reminder) ---
@app.post("/reminders/schedule", status_code=status.HTTP_201_CREATED)
async def create_daily_reminder(data: ReminderRequest):
    """Create or update a daily cron-based reminder."""
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
    
    logger.info(f"Created/Updated daily reminder job {job_id}")
    return {
        "status": "success",
        "action": "CREATE",
        "job_id": job_id,
        "detail": f"Daily reminder set for {data.hour:02d}:{data.minute:02d} local time"
    }


# --- 1b. CREATE (Interval Recurring Reminder) ---
@app.post("/reminders/schedule-interval", status_code=status.HTTP_201_CREATED)
async def create_interval_reminder(data: IntervalReminderRequest):
    """Create or update a recurring interval reminder (e.g., every 15 minutes)."""
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
    
    logger.info(f"Created/Updated interval reminder job {job_id}")
    return {
        "status": "success",
        "action": "CREATE",
        "job_id": job_id,
        "detail": f"Reminder set to repeat every {data.minutes} minutes."
    }


# --- 2. READ (List All Active Reminders) ---
@app.get("/reminders", status_code=status.HTTP_200_OK)
async def list_reminders():
    """List all currently active reminder jobs in the scheduler."""
    jobs = scheduler.get_jobs()
    job_list = []
    for job in jobs:
        job_list.append({
            "job_id": job.id,
            "next_run_time": str(job.next_run_time),
            "trigger": str(job.trigger)
        })
    return {
        "status": "success",
        "action": "READ",
        "total_active_jobs": len(job_list),
        "jobs": job_list
    }


# --- 3. UPDATE (Handled via POST create/replace or specific ID update) ---
# Note: Because the POST endpoints use `replace_existing=True`, 
# calling POST on an existing job_id acts as an Update operation.


# --- 4. DELETE (Cancel a Specific Reminder by Job ID) ---
@app.delete("/reminders/{job_id}", status_code=status.HTTP_200_OK)
async def delete_reminder(job_id: str):
    """Cancel and delete an active reminder job by its job_id."""
    try:
        scheduler.remove_job(job_id)
        logger.info(f"Successfully deleted job {job_id}")
        return {
            "status": "success",
            "action": "DELETE",
            "detail": f"Job '{job_id}' has been successfully deleted."
        }
    except Exception as e:
        logger.error(f"Failed to delete job {job_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found."
        )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
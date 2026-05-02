"""
APScheduler задачи:
  1. На всеки 5 минути — проверява неактивни разговори,
     записва съобщенията в pending_outbound (n8n ги взима и изпраща).
  2. Всеки ден в DAILY_REPORT_TIME — генерира PDF и го праща на имейл.
"""
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from config import settings

_scheduler = AsyncIOScheduler(timezone=pytz.timezone("Europe/Sofia"))


# ─── Проверка за неактивни разговори ─────────────────────────────────────────

async def _check_inactivity():
    from database import get_inactive_conversations, add_pending_outbound
    from order_manager import handle_inactivity
    from models import ConversationState

    inactive = get_inactive_conversations(settings.inactivity_timeout_minutes)
    for conv in inactive:
        if conv["state"] == ConversationState.ABANDONED_CHECK:
            continue

        conv_id_db = conv["id"]
        platform = conv["platform"]
        platform_conv_id = conv["platform_conversation_id"]
        user_id = conv["platform_user_id"]

        msg = handle_inactivity(conv_id_db, platform, platform_conv_id)

        # Запис в pending_outbound — n8n го взима и изпраща
        add_pending_outbound(
            platform=platform,
            user_id=user_id,
            conversation_id=platform_conv_id,
            message=msg,
            reply_to_comment_id=conv.get("reply_to_comment_id"),
        )


# ─── Дневен репорт ────────────────────────────────────────────────────────────

async def _send_daily_report():
    from report_generator import generate_report_pdf
    from database import get_todays_orders, get_todays_declined
    from datetime import datetime

    orders = get_todays_orders()
    declined = get_todays_declined()
    today_str = datetime.now().strftime("%d.%m.%Y")

    pdf_bytes = generate_report_pdf(orders, declined, today_str)
    print(f"[Scheduler] Репорт генериран за {today_str} — поръчки: {len(orders)}, отказани: {len(declined)}")

    if not settings.email_address or not settings.report_recipient_email:
        print("[Scheduler] Имейл не е настроен — репортът не е изпратен.")
        return

    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication

    mail = MIMEMultipart()
    mail["From"] = settings.email_address
    mail["To"] = settings.report_recipient_email
    mail["Subject"] = f"Дневен репорт — {today_str}"
    mail.attach(MIMEText(
        f"Потвърдени поръчки: {len(orders)}\nОтказани поръчки: {len(declined)}",
        "plain", "utf-8"
    ))
    attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment",
                          filename=f"report_{today_str.replace('.', '-')}.pdf")
    mail.attach(attachment)

    try:
        await aiosmtplib.send(
            mail,
            hostname=settings.email_smtp_server,
            port=settings.email_smtp_port,
            username=settings.email_address,
            password=settings.email_password,
            start_tls=True,
        )
        print(f"[Scheduler] Репорт изпратен на {settings.report_recipient_email}")
    except Exception as e:
        print(f"[Scheduler] Грешка при изпращане: {e}")


# ─── Стартиране ───────────────────────────────────────────────────────────────

def start_scheduler():
    hour, minute = settings.daily_report_time.split(":")

    _scheduler.add_job(
        _check_inactivity,
        trigger=IntervalTrigger(minutes=5),
        id="inactivity_check",
        replace_existing=True,
    )

    _scheduler.add_job(
        _send_daily_report,
        trigger=CronTrigger(hour=int(hour), minute=int(minute), timezone=settings.timezone),
        id="daily_report",
        replace_existing=True,
    )

    _scheduler.start()
    print(f"[Scheduler] Стартиран. Репорт в {settings.daily_report_time} ({settings.timezone})")

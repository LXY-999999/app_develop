from config.settings import Settings
from core.scheduler import start_scheduler


def test_scheduler_uses_configured_timezone() -> None:
    settings = Settings(
        schedule_cron="0 9 * * *",
        schedule_timezone="Asia/Shanghai",
        schedule_sources=["v2ex"],
    )

    scheduler = start_scheduler(settings)
    try:
        job = scheduler.get_job("ideahunter_v2ex")
        assert job is not None
        assert str(job.trigger.timezone) == "Asia/Shanghai"
        assert job.next_run_time.hour == 9
    finally:
        scheduler.shutdown(wait=False)

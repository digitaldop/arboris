from celery import shared_task


@shared_task(bind=True, ignore_result=True)
def execute_database_restore_task(self, job_id: int):
    from sistema.restore_job_runner import run_restore_job

    tid = getattr(self.request, "id", None)
    run_restore_job(job_id, celery_task_id=str(tid) if tid else "")

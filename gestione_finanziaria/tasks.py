from celery import shared_task


@shared_task(ignore_result=True)
def analyse_reconciliation_task():
    from django.db import connections
    from .reconciliation_worker import process_pending_analysis

    try:
        return process_pending_analysis()
    finally:
        connections.close_all()

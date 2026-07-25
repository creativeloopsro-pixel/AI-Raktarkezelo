from app.tasks import recover_pending_document_jobs, run_vrp_scheduler


def main() -> None:
    recover_pending_document_jobs.send()
    run_vrp_scheduler.send()


if __name__ == "__main__":
    main()

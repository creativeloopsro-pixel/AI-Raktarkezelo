from app.tasks import recover_pending_document_jobs


def main() -> None:
    recover_pending_document_jobs.send()


if __name__ == "__main__":
    main()

from app.config import get_settings
from app.tasks import (
    poll_inbound_email,
    recover_pending_document_jobs,
    run_plugin_dispatcher,
    run_vrp_scheduler,
)


def main() -> None:
    recover_pending_document_jobs.send()
    run_vrp_scheduler.send()
    run_plugin_dispatcher.send()
    if get_settings().email_imap_enabled:
        poll_inbound_email.send()


if __name__ == "__main__":
    main()

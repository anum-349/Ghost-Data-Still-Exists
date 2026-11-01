"""Compatibility entry point for the packaged evaluation script."""

import utils.clients
import utils.http_session
import utils.transport
import utils.session
from run_eval import main


if __name__ == "__main__":
    raise SystemExit(main())

import os
import threading
import time
from pathlib import Path

import uvicorn

from app.main import create_default_app


def main() -> None:
    stop_file_value = os.getenv("SEMIREVIEW_STOP_FILE", "")
    stop_file = Path(stop_file_value).resolve() if stop_file_value else None
    server = uvicorn.Server(
        uvicorn.Config(
            create_default_app(),
            host=os.getenv("SEMIREVIEW_HOST", "127.0.0.1"),
            port=int(os.getenv("SEMIREVIEW_PORT", "8000")),
        )
    )

    if stop_file is not None:
        def watch_for_stop() -> None:
            while not server.should_exit and not stop_file.exists():
                time.sleep(0.2)
            if stop_file.exists():
                server.should_exit = True

        threading.Thread(target=watch_for_stop, daemon=True).start()

    try:
        server.run()
    finally:
        if stop_file is not None:
            stop_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

"""Entry point for the portable Windows application and its child processes."""
import multiprocessing
import os
import sys


if __name__ == "__main__":
    # Set before importing the scientific stack, including in spawned workers.
    os.environ["PYTENSOR_FLAGS"] = ",".join(filter(None, [
        os.environ.get("PYTENSOR_FLAGS", ""), "cxx=",
    ]))
    os.environ.setdefault("MPLBACKEND", "Agg")
    multiprocessing.freeze_support()

    if "--chrono-file-dialog" in sys.argv:
        from chronologer_app.native_dialog import main
        main()
    else:
        import socket
        import threading
        import time
        import webbrowser
        import uvicorn
        from chronologer_app.main import app

        # Reserve a free loopback port so a development server cannot mask launch.
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port))

        def open_browser():
            while not server.started and not server.should_exit:
                time.sleep(0.1)
            if server.started:
                webbrowser.open(f"http://127.0.0.1:{port}")

        threading.Thread(target=open_browser, daemon=True).start()
        server.run(sockets=[listener])

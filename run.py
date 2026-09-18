import subprocess
import sys
import threading
import time

def start_api():
    subprocess.run(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        check=False,
    )

def start_ui():
    time.sleep(2)
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "ui/streamlit_app.py",
         "--server.port", "8501", "--server.address", "0.0.0.0"],
        check=False,
    )

if __name__ == "__main__":
    print("Starting DOTMappers AI Support Ticket Analytics...")
    print("FastAPI:  http://localhost:8000")
    print("Swagger:  http://localhost:8000/docs")
    print("Streamlit: http://localhost:8501")
    threading.Thread(target=start_api, daemon=True).start()
    start_ui()

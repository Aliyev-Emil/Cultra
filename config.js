// Where the backend (main.py) runs: the same computer that serves these pages, port 8000.
//   - opened on the laptop (localhost / 127.0.0.1 / a file)  -> http://127.0.0.1:8000
//   - opened from a phone on the same Wi-Fi (http://<laptop-ip>:5500/...)  -> http://<laptop-ip>:8000
// so a phone can join the demo without changing any page. (For phones, start the backend with
// "uvicorn main:app --host 0.0.0.0" so it accepts connections from other devices.)
const API = "http://" +
    (location.hostname && location.hostname !== "localhost" ? location.hostname : "127.0.0.1") +
    ":8000";

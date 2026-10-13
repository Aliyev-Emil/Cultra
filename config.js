// Shared by every page (loaded in <head>): where the backend is, who is logged in, and the
// few things the phone app needs.

// ---------- Where the backend (main.py) is ----------

// The online server on Render. After creating it, put its address here (no "/" at the end).
const SERVER_URL = "https://cultra-api.onrender.com";

// The phone app (Capacitor) shows these same pages from https://localhost and always uses the
// online server.
const IN_APP = Boolean(window.Capacitor && window.Capacitor.isNativePlatform && window.Capacitor.isNativePlatform()) ||
    (location.protocol === "https:" && location.hostname === "localhost");

// A normal browser uses the backend on this computer, like before:
//   - opened on the laptop (localhost / 127.0.0.1 / a file)  -> http://127.0.0.1:8000
//   - opened from a phone on the same Wi-Fi (http://<laptop-ip>:5500/...)  -> http://<laptop-ip>:8000
//     (start the backend with "uvicorn main:app --host 0.0.0.0" so other devices can reach it)
// To use the online server from the browser too (say the laptop is the shop's till and the
// phones have the app), open any page once with ?server=online at the end of the address.
// ?server=local switches back. The choice is remembered by this browser.
function chosenServer() {
    const asked = new URLSearchParams(location.search).get("server");
    try {
        if (asked === "online" || asked === "local") localStorage.setItem("cultra_server", asked);
        return localStorage.getItem("cultra_server");
    } catch (error) {
        return asked;            // storage blocked: only for this page
    }
}

const USE_ONLINE_SERVER = IN_APP || chosenServer() === "online";

const API = USE_ONLINE_SERVER ? SERVER_URL : "http://" +
    (location.hostname && location.hostname !== "localhost" ? location.hostname : "127.0.0.1") +
    ":8000";

// What pages say when the server can't be reached
const SERVER_ERROR = IN_APP
    ? "Serverə qoşulmaq olmur. İnternet bağlantınızı yoxlayıb yenidən cəhd edin."
    : "Serverə qoşulmaq olmur. Backend-in işlədiyini yoxlayın.";


// ---------- Who is logged in ----------
// sessionStorage = this tab only, so two tabs can be two different people while testing.
// localStorage = remembered when the app is closed, so the phone app stays logged in.

function getUserId() {
    try {
        let id = sessionStorage.getItem("user_id");
        if (!id) {
            id = localStorage.getItem("user_id");
            if (id) sessionStorage.setItem("user_id", id);   // this tab stays this person from now on
        }
        return id;
    } catch (error) {
        return null;
    }
}

function saveUserId(id) {
    try {
        sessionStorage.setItem("user_id", id);
        localStorage.setItem("user_id", id);
    } catch (error) {
        // storage blocked: logged in until the page is closed
    }
}

function forgetUserId() {
    try {
        sessionStorage.removeItem("user_id");
        localStorage.removeItem("user_id");
    } catch (error) {
        // nothing saved
    }
}


// ---------- Android back button (phone app) ----------
// Without this, the back button would close the app on every page. Now: an open camera or
// popup closes first (pages register a function with onBackButton that returns true when it
// closed something), the home screen leaves the app, every other page goes back.

const backButtonHandlers = [];

function onBackButton(handler) {
    backButtonHandlers.push(handler);
}

if (IN_APP && window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.App) {
    window.Capacitor.Plugins.App.addListener("backButton", function (event) {
        for (let i = backButtonHandlers.length - 1; i >= 0; i--) {
            if (backButtonHandlers[i]()) return;
        }

        const page = location.pathname.split("/").pop() || "index.html";
        if (page === "main_menu.html" || page === "index.html") {
            window.Capacitor.Plugins.App.minimizeApp();      // like any app's home screen
        } else if (event && event.canGoBack) {
            history.back();
        } else {
            location.href = "main_menu.html";
        }
    });
}


// ---------- Waking up the online server ----------
// Render's free server falls asleep after 15 minutes without visitors, and the first request
// then takes up to a minute. A note at the top says so, so the app doesn't look frozen.

if (USE_ONLINE_SERVER) {
    let answered = false;
    let note = null;

    fetch(API + "/health", { cache: "no-store" })
        .catch(function () { /* the page shows its own "can't reach the server" message */ })
        .finally(function () {
            answered = true;
            if (note) note.remove();
        });

    setTimeout(function () {
        if (answered) return;
        note = document.createElement("div");
        note.setAttribute("role", "status");
        note.textContent = "Server oyanır… ilk açılış 1 dəqiqəyə qədər çəkə bilər.";
        note.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:10000;padding:10px 16px;" +
            "background:#f79432;color:#0d111d;font:bold 14px Arial,sans-serif;text-align:center;";
        (document.body || document.documentElement).appendChild(note);
    }, 2500);
}

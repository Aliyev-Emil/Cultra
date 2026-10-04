// Included on every page that requires login. Polls for payment requests waiting
// on this user (someone scanned their payment QR) and shows an approve/decline
// sheet no matter which page they're on.
(function () {
    const user_id = sessionStorage.getItem("user_id");
    if (!user_id) return; // this page's own script handles the logged-out redirect

    const style = document.createElement("style");
    style.innerText = `
        #cultra-request-bg {
            display: none;
            position: fixed;
            inset: 0;
            background-color: rgba(0, 0, 0, 0.55);
            align-items: flex-end;
            justify-content: center;
            z-index: 9999;
        }
        #cultra-request-sheet {
            width: 100%;
            max-width: 420px;
            background-color: #131a2b;
            border: 1px solid #30394c;
            border-radius: 26px 26px 0 0;
            padding: 26px 24px 30px;
            box-sizing: border-box;
            font-family: Arial, sans-serif;
            color: white;
        }
        #cultra-request-amount {
            font-size: 36px;
            font-weight: bold;
            margin: 0 0 4px;
        }
        #cultra-request-sub {
            color: #71809f;
            font-size: 14px;
            margin: 0 0 6px;
        }
        #cultra-request-from {
            color: #71809f;
            font-size: 14px;
            margin: 0 0 22px;
        }
        #cultra-request-from.error {
            color: #ff7a6b;
        }
        .cultra-request-btn {
            width: 100%;
            height: 56px;
            border-radius: 18px;
            font-size: 16px;
            font-weight: bold;
            font-family: inherit;
            cursor: pointer;
        }
        .cultra-request-btn:disabled {
            opacity: 0.6;
            cursor: default;
        }
        #cultra-request-accept {
            border: none;
            background-color: #f79432;
            color: #0d111d;
            margin-bottom: 12px;
        }
        #cultra-request-decline {
            border: 1px solid #30394c;
            background-color: #182033;
            color: white;
        }
    `;
    document.head.appendChild(style);

    const bg = document.createElement("div");
    bg.id = "cultra-request-bg";
    bg.innerHTML =
        '<div id="cultra-request-sheet">' +
        '<p id="cultra-request-amount">₼0.00</p>' +
        '<p id="cultra-request-sub">wants to receive this from you</p>' +
        '<p id="cultra-request-from"></p>' +
        '<button class="cultra-request-btn" id="cultra-request-accept">Approve</button>' +
        '<button class="cultra-request-btn" id="cultra-request-decline">Decline</button>' +
        "</div>";
    document.body.appendChild(bg);

    const amountEl = document.getElementById("cultra-request-amount");
    const subEl = document.getElementById("cultra-request-sub");
    const fromEl = document.getElementById("cultra-request-from");
    const acceptBtn = document.getElementById("cultra-request-accept");
    const declineBtn = document.getElementById("cultra-request-decline");

    let queue = [];
    let shownId = null;
    let busy = false;

    function showNext() {
        if (busy || bg.style.display === "flex" || queue.length === 0) return;
        const req = queue[0];
        shownId = req.payment_id;
        amountEl.innerText = "₼" + req.amount.toFixed(2);
        subEl.innerText = (req.receiver_username || "Someone") + " wants to receive this from you";
        fromEl.className = "";
        fromEl.innerText = "Will be charged to " +
            (req.payer_card === "APP_BALANCE" ? "your Cultra balance" : "•••• " + String(req.payer_card).slice(-4));
        bg.style.display = "flex";
    }

    function closeAndAdvance() {
        bg.style.display = "none";
        queue = queue.filter(function (r) { return r.payment_id !== shownId; });
        shownId = null;
        setTimeout(showNext, 400);
    }

    async function respond(path) {
        if (!shownId || busy) return;
        busy = true;
        acceptBtn.disabled = true;
        declineBtn.disabled = true;

        let failedReason = null;
        try {
            const response = await fetch("http://127.0.0.1:8000/" + path, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ payment_id: shownId, user_id: user_id })
            });
            const data = await response.json();
            if (data.status === "failed") failedReason = data.reason || "Something went wrong";
        } catch (error) {
            // if it didn't go through, it'll just show up again on the next poll
        }

        busy = false;
        acceptBtn.disabled = false;
        declineBtn.disabled = false;

        if (failedReason) {
            // Keep the sheet open so they can read why, and still Decline if they want
            fromEl.className = "error";
            fromEl.innerText = failedReason;
            return;
        }
        closeAndAdvance();
    }

    acceptBtn.addEventListener("click", function () { respond("confirm-payment"); });
    declineBtn.addEventListener("click", function () { respond("decline-payment"); });

    async function poll() {
        try {
            const response = await fetch("http://127.0.0.1:8000/pending-payments/" + user_id);
            const data = await response.json();
            if (data.status === "success") {
                queue = data.payments;

                const stillPending = queue.some(function (r) { return r.payment_id === shownId; });
                if (shownId && !busy && !stillPending) {
                    closeAndAdvance(); // resolved from somewhere else
                } else {
                    showNext();
                }
            }
        } catch (error) {
            // backend not reachable right now, try again next tick
        }
    }

    poll();
    setInterval(poll, 4000);
})();

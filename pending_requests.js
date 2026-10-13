// Included on every page that requires login. Polls for payment requests waiting
// on this user (someone scanned their payment QR) and shows an approve/decline
// sheet no matter which page they're on.
(function () {
    const user_id = getUserId();
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
        /* What's being paid for (only when the merchant charged a cart) */
        #cultra-request-items {
            list-style: none;
            margin: 0 0 18px;
            padding: 10px 14px;
            border-radius: 14px;
            background-color: #182033;
            max-height: 180px;
            overflow-y: auto;
            font-size: 14px;
        }
        #cultra-request-items:empty {
            display: none;
        }
        #cultra-request-items li {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 4px 0;
        }
        #cultra-request-items li span:last-child {
            white-space: nowrap;
            color: #a9b3c9;
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
        '<p id="cultra-request-sub">sizdən ödəniş tələb edir</p>' +
        '<p id="cultra-request-from"></p>' +
        '<ul id="cultra-request-items"></ul>' +
        '<button class="cultra-request-btn" id="cultra-request-accept">Təsdiq et</button>' +
        '<button class="cultra-request-btn" id="cultra-request-decline">İmtina et</button>' +
        "</div>";
    document.body.appendChild(bg);

    const amountEl = document.getElementById("cultra-request-amount");
    const subEl = document.getElementById("cultra-request-sub");
    const fromEl = document.getElementById("cultra-request-from");
    const itemsEl = document.getElementById("cultra-request-items");

    // Cart items, if the backend sends them with the request ([{ name, price, qty }, ...])
    function showItems(items) {
        itemsEl.innerHTML = "";
        if (!Array.isArray(items)) return;
        items.forEach(function (item) {
            const li = document.createElement("li");
            const name = document.createElement("span");
            name.textContent = (item.qty > 1 ? item.qty + " × " : "") + item.name;   // textContent: never HTML
            const price = document.createElement("span");
            price.textContent = "₼" + (Math.round(item.price * 100) * item.qty / 100).toFixed(2);
            li.append(name, price);
            itemsEl.appendChild(li);
        });
    }
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
        subEl.innerText = (req.receiver_username || "Biznes") + " sizdən ödəniş tələb edir";
        fromEl.className = "";
        fromEl.innerText = (req.payer_card === "APP_BALANCE"
            ? "Cultra balansınızdan"
            : "•••• " + String(req.payer_card).slice(-4) + " kartınızdan") + " ödəniləcək";
        showItems(req.items);
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
        const shownReq = queue.find(function (r) { return r.payment_id === shownId; });
        let paid = null;
        acceptBtn.disabled = true;
        declineBtn.disabled = true;

        let failedReason = null;
        try {
            const response = await fetch(API + "/" + path, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ payment_id: shownId, user_id: user_id })
            });
            const data = await response.json();
            if (data.status === "failed") failedReason = data.reason || "Xəta baş verdi";
            else if (path === "confirm-payment" && data.status === "success") paid = data;
        } catch (error) {
            // if it didn't go through, it'll just show up again on the next poll
        }

        busy = false;
        acceptBtn.disabled = false;
        declineBtn.disabled = false;

        // Let the page refresh its balance / history (e.g. to show the cashback just earned)
        if (!failedReason) window.dispatchEvent(new CustomEvent("cultra:payment-resolved"));

        if (failedReason) {
            // Keep the sheet open so they can read why, and still Decline if they want
            fromEl.className = "error";
            fromEl.innerText = failedReason;
            return;
        }

        // Paid: back to the main menu, with a short confirmation there
        if (paid) {
            const text = "₼" + Number(paid.amount).toFixed(2) + " ödənildi" +
                (shownReq && shownReq.receiver_username ? ": " + shownReq.receiver_username : "") +
                (paid.cashback > 0 ? " · +₼" + Number(paid.cashback).toFixed(2) + " keşbek" : "") +
                (paid.xp > 0 ? " · +" + paid.xp + " XP" : "") +
                (paid.level_up ? " · " + paid.level_up.icon + " " + paid.level_up.name + " səviyyəsi!" : "");

            if (window.cultraShowFlash) {          // already on the main menu: just show it
                closeAndAdvance();
                window.cultraShowFlash(text);
                return;
            }
            try {
                sessionStorage.setItem("cultra_flash", text);
            } catch (error) {
                // no banner, still go home
            }
            window.location.href = "main_menu.html";
            return;
        }

        closeAndAdvance();
    }

    acceptBtn.addEventListener("click", function () { respond("confirm-payment"); });
    declineBtn.addEventListener("click", function () { respond("decline-payment"); });

    async function poll() {
        try {
            const response = await fetch(API + "/pending-payments/" + user_id);
            const data = await response.json();
            if (data.status === "success") {
                queue = data.payments;

                const stillPending = queue.some(function (r) { return r.payment_id === shownId; });
                if (shownId && !busy && !stillPending) {
                    // Resolved somewhere else, e.g. the merchant cancelled it. Let the page refresh
                    // (the payment QR page shows a fresh barcode, since the old one was used).
                    closeAndAdvance();
                    window.dispatchEvent(new CustomEvent("cultra:payment-resolved"));
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

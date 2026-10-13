// Phone app only: scanning with the phone's own scanner (Google ML Kit, through the Capacitor
// plugin @capacitor-mlkit/barcode-scanning). It reads QR codes and barcodes much better than the
// browser scanner, and works without Google Play services.
//
// The camera picture is drawn by the phone *behind* the web page. While scanning, the page turns
// see-through and shows only a frame, a hint and the buttons below.
// In a normal browser NativeScanner.available is false and the pages use html5-qrcode, as before.
//
//   NativeScanner.open({
//       formats: ["QR_CODE"],            // what to look for: QR_CODE, EAN_13, CODE_128, ...
//       hint: "QR kodu çərçivəyə tutun",
//       wide: false,                      // a wider frame, for barcodes
//       doneLabel: "Bağla",               // the button at the bottom
//       accent: "#d9a441",                // frame + button colour (default: Cultra orange)
//       onCode: function (text) {},       // each code read. The same code again only after it was out of view.
//       onClose: function () {}           // closed: by the user, the back button or NativeScanner.close()
//   })   -> a Promise. Rejects with an Error (Azerbaijani message) if the camera can't start.
//   NativeScanner.close()
//   NativeScanner.message(text, kind)     // a line above the button. kind: "ok", "error" or ""
//   NativeScanner.isOpen()
//   NativeScanner.openSettings()          // the app's page in the phone settings (camera permission)

const NativeScanner = (function () {
    const plugin = window.Capacitor && window.Capacitor.Plugins && window.Capacitor.Plugins.BarcodeScanner;
    const available = Boolean(IN_APP && plugin);
    const QUIET_MS = 1000;     // a code must be out of view this long before it counts again

    let isOpen = false;
    let options = null;
    let lastSeen = {};         // code -> when the camera last saw it
    let ui = null;

    function build() {
        if (ui) return ui;

        const style = document.createElement("style");
        style.textContent = `
            html.ns-on, html.ns-on body { background: transparent !important; }
            html.ns-on body > *:not(#native-scan) { visibility: hidden !important; }
            #native-scan { display: none; position: fixed; inset: 0; z-index: 2147483000;
                color: white; font-family: Arial, sans-serif; }
            html.ns-on #native-scan { display: block; }
            #native-scan .ns-frame { position: absolute; left: 50%; top: 44%; width: 250px; height: 250px;
                transform: translate(-50%, -50%); border: 3px solid #f79432; border-radius: 26px;
                box-shadow: 0 0 0 200vmax rgba(5, 8, 15, 0.62); }
            #native-scan .ns-frame.wide { width: min(320px, 86vw); height: 190px; }
            #native-scan .ns-top { position: absolute; top: 0; left: 0; right: 0; display: flex;
                align-items: center; justify-content: space-between; padding: 18px 18px 0; }
            #native-scan .ns-round { width: 46px; height: 46px; border-radius: 50%; border: none;
                background: rgba(24, 32, 51, 0.92); color: white; font-size: 20px; font-family: inherit; }
            #native-scan .ns-round.on { background: #f79432; color: #0d111d; }
            #native-scan .ns-hint { position: absolute; left: 24px; right: 24px; top: calc(44% - 175px);
                margin: 0; text-align: center; font-size: 17px; font-weight: bold; }
            #native-scan .ns-bottom { position: absolute; left: 0; right: 0; bottom: 0; padding: 0 24px 28px;
                display: flex; flex-direction: column; align-items: center; gap: 14px; }
            #native-scan .ns-message { margin: 0; min-height: 20px; max-width: 360px; text-align: center;
                font-size: 15px; line-height: 1.4; padding: 0 6px; white-space: pre-line; }
            #native-scan .ns-message.ok { color: #3fc08d; }
            #native-scan .ns-message.error { color: #ff8f80; }
            #native-scan .ns-done { width: 100%; max-width: 360px; height: 54px; border: none; border-radius: 18px;
                background: #f79432; color: #0d111d; font-size: 16px; font-weight: bold; font-family: inherit; }
        `;
        document.head.appendChild(style);

        const root = document.createElement("div");
        root.id = "native-scan";
        root.setAttribute("role", "dialog");
        root.setAttribute("aria-label", "Skaner");
        root.innerHTML =
            '<div class="ns-frame"></div>' +
            '<div class="ns-top">' +
            '  <button class="ns-round ns-close" type="button" aria-label="Bağla">✕</button>' +
            '  <button class="ns-round ns-torch" type="button" aria-label="Fənər" hidden>🔦</button>' +
            "</div>" +
            '<p class="ns-hint"></p>' +
            '<div class="ns-bottom">' +
            '  <p class="ns-message" role="status"></p>' +
            '  <button class="ns-done" type="button"></button>' +
            "</div>";
        document.body.appendChild(root);

        ui = {
            frame: root.querySelector(".ns-frame"),
            hint: root.querySelector(".ns-hint"),
            message: root.querySelector(".ns-message"),
            done: root.querySelector(".ns-done"),
            torch: root.querySelector(".ns-torch")
        };
        root.querySelector(".ns-close").addEventListener("click", function () { close(); });
        ui.done.addEventListener("click", function () { close(); });
        ui.torch.addEventListener("click", function () {
            plugin.toggleTorch().then(function () {
                ui.torch.classList.toggle("on");
            }, function () { /* no torch after all */ });
        });
        return ui;
    }

    function onBarcodes(event) {
        if (!isOpen || !event || !event.barcodes) return;
        const now = Date.now();
        event.barcodes.forEach(function (barcode) {
            const text = barcode.rawValue;
            if (!text || !isOpen) return;
            const before = lastSeen[text];
            lastSeen[text] = now;
            if (before && now - before < QUIET_MS) return;     // still the same code in front of the camera
            if (options && options.onCode) options.onCode(text);
        });
    }

    function explain(error) {
        const text = String((error && error.message) || error || "");
        const result = new Error();
        if (/denied/i.test(text)) {
            result.message = "Kameraya icazə verilməyib. Telefonun parametrlərində Cultra üçün kameranı açın.";
            result.permissionDenied = true;
        } else {
            result.message = "Kameranı açmaq olmadı" + (text ? ": " + text : ".");
        }
        return result;
    }

    async function open(newOptions) {
        if (!available) throw new Error("Bu cihazda tətbiqin skaneri yoxdur.");
        if (isOpen) await close();

        options = newOptions || {};
        lastSeen = {};
        build();
        ui.hint.textContent = options.hint || "";
        ui.frame.classList.toggle("wide", Boolean(options.wide));
        ui.done.textContent = options.doneLabel || "Bağla";
        ui.frame.style.borderColor = options.accent || "";
        ui.done.style.backgroundColor = options.accent || "";
        ui.torch.hidden = true;
        ui.torch.classList.remove("on");
        message("");

        isOpen = true;
        document.documentElement.classList.add("ns-on");
        try {
            await plugin.removeAllListeners();
            await plugin.addListener("barcodesScanned", onBarcodes);
            await plugin.startScan({ formats: options.formats || [] });   // asks for camera permission the first time
        } catch (error) {
            isOpen = false;
            document.documentElement.classList.remove("ns-on");
            options = null;
            plugin.stopScan().catch(function () { /* wasn't running */ });
            throw explain(error);
        }

        plugin.isTorchAvailable().then(function (result) {
            if (isOpen && result && result.available) ui.torch.hidden = false;
        }, function () { /* no torch button */ });
    }

    async function close() {
        if (!isOpen) return;
        isOpen = false;
        document.documentElement.classList.remove("ns-on");
        const closed = options && options.onClose;
        options = null;
        try {
            await plugin.stopScan();
            await plugin.removeAllListeners();
        } catch (error) {
            // already stopped
        }
        if (closed) closed();
    }

    function message(text, kind) {
        if (!ui) return;
        ui.message.textContent = text || "";
        ui.message.className = "ns-message" + (kind ? " " + kind : "");
    }

    if (available) {
        // A camera left running by the previous page (shouldn't happen, but it would stay on)
        plugin.stopScan().catch(function () { /* nothing was running */ });
        // Leaving the page turns the camera off; it isn't part of the page and wouldn't stop by itself
        window.addEventListener("pagehide", function () {
            if (isOpen) plugin.stopScan();
        });
        // Android back button: close the camera first
        onBackButton(function () {
            if (!isOpen) return false;
            close();
            return true;
        });
    }

    return {
        available: available,
        open: open,
        close: close,
        message: message,
        isOpen: function () { return isOpen; },
        openSettings: function () {
            if (available) plugin.openSettings().catch(function () { /* settings unavailable */ });
        }
    };
})();

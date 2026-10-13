// The camera scanner (html5-qrcode) has no language setting: its buttons and messages are
// always English. This swaps them for Azerbaijani the moment they appear on the page.
// Only exact library texts are replaced, so nothing else on the page is touched.
(function () {
    const AZ = {
        "Request Camera Permissions": "Kameraya icazə ver",
        "Requesting camera permissions...": "Kamera icazəsi soruşulur...",
        "No camera found": "Kamera tapılmadı",
        "No Cameras": "Kamera yoxdur",
        "Stop Scanning": "Skanı dayandır",
        "Start Scanning": "Skana başla",
        "Launching Camera...": "Kamera açılır...",
        "Switch On Torch": "Fənəri yandır",
        "Switch Off Torch": "Fənəri söndür",
        "Failed to turn on torch": "Fənəri yandırmaq alınmadı",
        "Failed to turn off torch": "Fənəri söndürmək alınmadı",
        "Scan an Image File": "Şəkildən skan et",
        "Scan using camera directly": "Kamera ilə skan et",
        "Select Camera": "Kamera seçin",
        "Choose Image": "Şəkil seçin",
        "Choose Another": "Başqa şəkil seçin",
        "No image choosen": "Şəkil seçilməyib",
        "Or drop an image to scan": "Və ya şəkli bura atın",
        "Or drop an image to scan (other files not supported)": "Və ya şəkli bura atın (yalnız şəkil faylları)",
        "Loading image...": "Şəkil yüklənir...",
        "Camera based scan": "Kamera ilə skan",
        "File based scan": "Fayl ilə skan",
        "Fule based scan": "Fayl ilə skan",          // (sic) - the library's own typo
        "Info icon": "Məlumat",
        "Scanner paused": "Skan dayandırılıb",
        "Code Scanner": "Kod skaneri",
        "Idle": "Gözləmədə",
        "Error": "Xəta",
        "Permission": "İcazə",
        "Scanning": "Skan edilir",
        "zoom": "yaxınlaşdırma",
        "Report issues": "Problem bildir",
        "Powered by ": "Texnologiya: ",
        "Camera access is only supported in secure context like https or localhost.":
            "Kameradan yalnız https və ya localhost ünvanında istifadə etmək olar.",
        "NotAllowedError: Permission denied": "Kameraya icazə verilmədi",
        "NotFoundError: Requested device not found": "Kamera tapılmadı",
        "NotReadableError: Could not start video source": "Kamera başqa proqram tərəfindən istifadə olunur"
    };

    // Texts with something after them: "Select Camera (2)", "Anonymous Camera 1", "Last Match: ..."
    const STARTS = [
        ["Select Camera", "Kamera seçin"],
        ["Anonymous Camera", "Kamera"],
        ["Last Match: ", "Son oxunan: "]
    ];

    // Phrases the library glues together, e.g. "Choose Image - No image choosen"
    const PARTS = [
        ["Choose Image", "Şəkil seçin"],
        ["Choose Another", "Başqa şəkil seçin"],
        ["No image choosen", "şəkil seçilməyib"]
    ];

    function translate(text) {
        const trimmed = text.trim();
        if (!trimmed) return null;
        if (Object.prototype.hasOwnProperty.call(AZ, trimmed)) {
            return text.replace(trimmed, AZ[trimmed]);
        }
        for (const [en, az] of STARTS) {
            if (trimmed.startsWith(en)) return text.replace(en, az);
        }
        let changed = text;
        for (const [en, az] of PARTS) changed = changed.split(en).join(az);
        return changed !== text ? changed : null;
    }

    function fixNode(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            const done = translate(node.nodeValue);
            if (done !== null && done !== node.nodeValue) node.nodeValue = done;
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        ["alt", "title", "placeholder", "aria-label"].forEach(function (name) {
            const value = node.getAttribute(name);
            const done = value && translate(value);
            if (done && done !== value) node.setAttribute(name, done);
        });
        node.childNodes.forEach(fixNode);
    }

    function start() {
        fixNode(document.body);
        new MutationObserver(function (changes) {
            changes.forEach(function (change) {
                if (change.type === "characterData") fixNode(change.target);
                else if (change.type === "attributes") fixNode(change.target);
                else change.addedNodes.forEach(fixNode);
            });
        }).observe(document.body, {
            subtree: true,
            childList: true,
            characterData: true,
            attributes: true,
            attributeFilter: ["alt", "title", "placeholder", "aria-label"]
        });
    }

    if (document.body) start();
    else document.addEventListener("DOMContentLoaded", start);
})();

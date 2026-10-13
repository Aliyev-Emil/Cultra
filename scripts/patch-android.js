// Gets the Android project (android/, made by "npx cap add android") ready for Cultra:
//   - camera permission, for the barcode scanner
//   - the app's dark colour behind the status bar, while pages load, and on the splash screen
//   - the Cultra icon (from resources/android/res)
//   - the app version from package.json ("version": "1.0.0")
// Safe to run again: "npm run sync" runs it every time.
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const main = path.join(root, "android", "app", "src", "main");
const res = path.join(main, "res");

if (!fs.existsSync(main)) {
    console.error('There is no Android project yet: run "npm run android:setup" first.');
    process.exit(1);
}

function edit(file, change) {
    const before = fs.readFileSync(file, "utf8");
    const after = change(before);
    if (after !== before) fs.writeFileSync(file, after);
}

function write(file, text) {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, text);
}

// Puts a line in front of the last closing tag, unless something with `marker` is already there
function addLine(xml, marker, line, closingTag, indent) {
    if (xml.includes(marker)) return xml;
    const at = xml.lastIndexOf(closingTag);
    if (at < 0) throw new Error("no " + closingTag + " found");
    const lineStart = xml.lastIndexOf("\n", at) + 1;
    return xml.slice(0, lineStart) + indent + line + "\n" + xml.slice(lineStart);
}

// Sets <item name="...">value</item> inside one <style> of styles.xml
function setStyleItems(xml, styleName, items) {
    const pattern = new RegExp('(<style name="' + styleName.replace(/\./g, "\\.") + '"[^>]*>)([\\s\\S]*?)(\\n[ \\t]*</style>)');
    const found = xml.match(pattern);
    if (!found) {
        console.warn("  styles.xml has no " + styleName + " style, skipped");
        return xml;
    }
    let body = found[2];
    Object.keys(items).forEach(function (name) {
        const item = '<item name="' + name + '">' + items[name] + "</item>";
        const existing = new RegExp('<item name="' + name + '">[^<]*</item>');
        body = existing.test(body) ? body.replace(existing, function () { return item; }) : body + "\n        " + item;
    });
    return xml.replace(pattern, function () { return found[1] + body + found[3]; });
}

// 1. Permissions: the camera (the scanner asks the user the first time)
edit(path.join(main, "AndroidManifest.xml"), function (xml) {
    xml = addLine(xml, "android.permission.CAMERA",
        '<uses-permission android:name="android.permission.CAMERA" />', "</manifest>", "    ");
    xml = addLine(xml, "android.hardware.camera",
        '<uses-feature android:name="android.hardware.camera" android:required="false" />', "</manifest>", "    ");
    // ML Kit's setup step (only used by its Google scanner screen, which Cultra doesn't open)
    xml = addLine(xml, "com.google.mlkit.vision.DEPENDENCIES",
        '<meta-data android:name="com.google.mlkit.vision.DEPENDENCIES" android:value="barcode_ui" />', "</application>", "        ");
    return xml;
});

// 2. Colours, splash screen, icon background
write(path.join(res, "values", "cultra_colors.xml"),
    '<?xml version="1.0" encoding="utf-8"?>\n' +
    "<resources>\n" +
    '    <color name="cultra_background">#0D111D</color>\n' +
    "</resources>\n");

write(path.join(res, "values", "ic_launcher_background.xml"),
    '<?xml version="1.0" encoding="utf-8"?>\n' +
    "<resources>\n" +
    '    <color name="ic_launcher_background">#F79432</color>\n' +
    "</resources>\n");

// Older phones (Android 11 and below) show this while the app starts: the icon in the middle of
// the dark background, not stretched
write(path.join(res, "drawable", "cultra_splash.xml"),
    '<?xml version="1.0" encoding="utf-8"?>\n' +
    '<layer-list xmlns:android="http://schemas.android.com/apk/res/android">\n' +
    '    <item android:drawable="@color/cultra_background" />\n' +
    '    <item android:drawable="@mipmap/ic_launcher_round" android:gravity="center" android:width="112dp" android:height="112dp" />\n' +
    "</layer-list>\n");

edit(path.join(res, "values", "styles.xml"), function (xml) {
    // The app itself: dark behind the status/navigation bars and between pages
    xml = setStyleItems(xml, "AppTheme.NoActionBar", {
        "android:windowBackground": "@color/cultra_background",
        "android:statusBarColor": "@color/cultra_background",
        "android:navigationBarColor": "@color/cultra_background"
    });
    // Starting up: Android 12+ shows the icon on windowSplashScreenBackground, older ones the drawable
    xml = setStyleItems(xml, "AppTheme.NoActionBarLaunch", {
        "android:background": "@drawable/cultra_splash",
        "windowSplashScreenBackground": "@color/cultra_background"
    });
    return xml;
});

// 3. Icons
const icons = path.join(root, "resources", "android", "res");
fs.cpSync(icons, res, { recursive: true });

// 4. Version: change "version" in package.json before building an update.
//    Android only installs an update over the old app if versionCode went up.
const version = require(path.join(root, "package.json")).version;
const parts = version.split(".").map(Number);
if (parts.length !== 3 || parts.some(function (n) { return !Number.isInteger(n) || n < 0 || n > 99; })) {
    console.error('package.json "version" must look like 1.0.0 (each number 0-99), not "' + version + '"');
    process.exit(1);
}
const versionCode = parts[0] * 10000 + parts[1] * 100 + parts[2];
edit(path.join(root, "android", "app", "build.gradle"), function (gradle) {
    return gradle
        .replace(/versionCode\s+\d+/, "versionCode " + versionCode)
        .replace(/versionName\s+"[^"]*"/, 'versionName "' + version + '"');
});

console.log("Android project ready: camera permission, dark theme, Cultra icon, version " + version + " (" + versionCode + ")");

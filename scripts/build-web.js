// Copies the pages into www/, the folder Capacitor puts inside the app.
// "npm run sync" and "npm run android:setup" run this for you.
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const www = path.join(root, "www");

// What the pages need, and nothing else (no main.py, docs, practice files, ...)
const files = fs.readdirSync(root).filter(function (name) {
    return name.endsWith(".html") || name.endsWith(".js");
});
const folders = ["images", "vendor"];

if (!files.includes("index.html")) {
    console.error("index.html is missing: the app opens it first.");
    process.exit(1);
}

fs.rmSync(www, { recursive: true, force: true });
fs.mkdirSync(www);
files.forEach(function (name) {
    fs.copyFileSync(path.join(root, name), path.join(www, name));
});
folders.forEach(function (name) {
    fs.cpSync(path.join(root, name), path.join(www, name), { recursive: true });
});

console.log("www/ ready: " + files.length + " files + " + folders.join(", ") + "/");

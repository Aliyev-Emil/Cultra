from fastapi import FastAPI
from pydantic import BaseModel
from typing import Literal
import math
import secrets
import uuid
from datetime import datetime, timedelta

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for local dev, never do this in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# All registered users, keyed by a unique user_id
users = {
    "123": {
        "username": "Emil",
        "password": "12345678",
        "accounts": {},
        "app_balance": 0.0,
        "merchant": None
    },
    "456": {
        "username": "Alik",
        "password": "12345678",
        "accounts": {},
        "app_balance": 0.0,
        "merchant": None
    }
}

bankcards = {
    "1234123412341234": {
        "cvv": "123",
        "month": "05",
        "year": "30",
        "balance": 1000.00
    },
    "5678567856785678": {
        "cvv": "456",
        "month": "11",
        "year": "27",
        "balance": 500.00
    }
}

pending_payments = {}

# All completed transfers, newest last. Each one is visible to both sides.
transactions = []

# Selecting this instead of a real card number means "use the app balance."
APP_BALANCE = "APP_BALANCE"

MERCHANT_BALANCE = "MERCHANT_BALANCE"

# Barcodes on the user's payment QR page. The barcode only holds a 16-digit number;
# the full "PAY_QR:<user>:<account>" text is kept here under that number.
# A user has one barcode at a time: opening the payment page makes a new one and the old one
# stops working. No timer: it stays valid while the page is open, like the QR code.
short_codes = {}          # "6261520768600759" -> {"qr_data": ..., "user_id": ...}
BARCODE_PREFIX = "62"     # 62 = payment code (PAY_QR)


BUSINESS_CATEGORIES = {
    "restaurants":  {"name": "Restoran və kafelər", "icon": "🍔", "cashback": 1.8, "monthly_cap": 10.0},
    "supermarkets": {"name": "Supermarketlər",      "icon": "🛒", "cashback": 0.5, "monthly_cap": 5.0},
    "gas_stations": {"name": "Yanacaq məntəqələri", "icon": "⛽", "cashback": 0.5, "monthly_cap": 5.0},
    "pharmacies":   {"name": "Apteklər",            "icon": "💊", "cashback": 1.0, "monthly_cap": 5.0},
    "transport":    {"name": "Nəqliyyat",           "icon": "🚕", "cashback": 1.0, "monthly_cap": 3.0},
}


# ---------- Levels (XP) - the full idea is in docs/levels.md ----------
# Customers earn XP by paying merchants. Each XP entry counts for 90 days, so the level follows
# recent use: going up is instant, going down is checked on the 1st of each month.
# A higher level multiplies the monthly cashback caps above.
XP_WINDOW_DAYS = 90
XP_PER_PAYMENT = 10          # each merchant payment of at least XP_MIN_PAYMENT...
XP_PAYMENTS_PER_DAY = 5      # ...but only the first 5 payments a day
XP_NEW_MERCHANT = 25         # first payment ever at a merchant
XP_REFERRAL = 100            # someone you sent money to (by username) makes their first merchant payment
XP_MIN_PAYMENT = 1.0         # smaller payments earn nothing, so nobody farms XP with ₼0.01 payments

LEVELS = [
    # reach = 90-day XP needed to rank up, keep = needed on the 1st of a month to stay (70% of reach)
    {"id": "bronze",   "name": "Bürünc", "icon": "🥉", "reach": 0,    "keep": 0,    "multiplier": 1.0},
    {"id": "silver",   "name": "Gümüş",  "icon": "🥈", "reach": 300,  "keep": 210,  "multiplier": 1.25},
    {"id": "gold",     "name": "Qızıl",  "icon": "🥇", "reach": 1000, "keep": 700,  "multiplier": 1.5},
    {"id": "platinum", "name": "Platin", "icon": "💎", "reach": 2500, "keep": 1750, "multiplier": 2.0},
]


# Demo products for the merchant checkout. barcode (EAN-13) -> name + price in AZN.
# 476 = Azerbaijan's barcode country prefix; the last digit is a real EAN-13 check digit.
# The server is the only place prices live: the app sends barcodes + quantities, and /payqr
# checks the total against these prices, so a price edited in the browser can't be charged.
PRODUCTS = {
    "4760180200374": {"name": "Çörək (ağ)",       "price": 0.60},
    "4760180200749": {"name": "Süd 1 L",          "price": 1.85},
    "4760180201111": {"name": "Ayran 0.5 L",      "price": 0.95},
    "4760180201487": {"name": "Ağ pendir 400 q",  "price": 4.20},
    "4760180201852": {"name": "Yumurta, 10 ədəd", "price": 2.40},
    "4760180202224": {"name": "Qazlı su 1.5 L",   "price": 0.80},
    "4760180202590": {"name": "Qara çay 250 q",   "price": 3.50},
    "4760180202965": {"name": "Şəkər 1 kq",       "price": 1.65},
    "4760180203337": {"name": "Makaron 500 q",    "price": 1.30},
    "4760180203702": {"name": "Kərə yağı 200 q",  "price": 3.10},
    "4760180204075": {"name": "Pomidor 1 kq",     "price": 2.20},
    "4760180204440": {"name": "Alma 1 kq",        "price": 1.90},
    "4760180204815": {"name": "Şokolad 90 q",     "price": 1.75},
    "4760180205188": {"name": "Düyü 1 kq",        "price": 2.60},
}


def get_merchant(user_id):
    """The user's merchant profile, or None if they never registered as a merchant."""
    return users[user_id]["merchant"]


def find_user_id(username):
    """user_id for an exact username, or None. Usernames are unique (see /register)."""
    for user_id, user in users.items():
        if user["username"] == username:
            return user_id
    return None


# Azerbaijani letters people often type with an English keyboard instead
SEARCH_FOLD = str.maketrans({"ə": "e", "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u"})


def search_key(text):
    """Lowercase plain-Latin version of a name, so "ilkin" finds "İlkin" and "sebuhi" finds "Səbuhi".
    ("İ".lower() is "i" + a combining dot, which is removed here.)"""
    return text.lower().replace("̇", "").translate(SEARCH_FOLD)


def can_pay_from(user_id, account_id):
    """Accounts a user can SPEND from: the app balance or one of their personal bank cards.
    The merchant balance is deliberately not here - merchants only receive money."""
    if account_id == APP_BALANCE:
        return True  # every user has an app balance, even if it's 0
    return account_id in users[user_id]["accounts"]


def can_receive_into(user_id, account_id):
    """Accounts a user can RECEIVE into: everything they can spend from, plus their merchant balance."""
    if account_id == MERCHANT_BALANCE:
        return get_merchant(user_id) is not None
    return can_pay_from(user_id, account_id)


def get_account_balance(user_id, account_id):
    if account_id == APP_BALANCE:
        return users[user_id]["app_balance"]
    if account_id == MERCHANT_BALANCE:
        return users[user_id]["merchant"]["merchant_balance"]
    # Bank cards: the bank's balance lives in `bankcards`, so a card added in two places
    # (personal + merchant, or two users) is still ONE balance instead of money being copied
    return bankcards[account_id]["balance"]


def adjust_account_balance(user_id, account_id, delta):
    if account_id == APP_BALANCE:
        users[user_id]["app_balance"] += delta
    elif account_id == MERCHANT_BALANCE:
        users[user_id]["merchant"]["merchant_balance"] += delta
    else:
        bankcards[account_id]["balance"] += delta


def with_balances(accounts):
    """Adds the live bank balance to each linked card, for sending to the app."""
    return {number: {**info, "balance": bankcards[number]["balance"]} for number, info in accounts.items()}


def party_name(user_id, account_id=None):
    """The name people see in history/popups. Money going to a merchant balance shows the
    business name, everything else shows the username."""
    if account_id == MERCHANT_BALANCE:
        return users[user_id]["merchant"]["business_name"]
    return users[user_id]["username"]


def record_transaction(payer_id, receiver_id, amount, receiver_account=None, cashback=0.0, items=None, xp=0):
    transactions.append({
        "id": str(uuid.uuid4()),
        "kind": "transfer",
        "payer_id": payer_id,
        "payer_username": users[payer_id]["username"],
        "receiver_id": receiver_id,
        "receiver_username": party_name(receiver_id, receiver_account),
        "receiver_account": receiver_account,  # MERCHANT_BALANCE sends it to the merchant history
        "amount": amount,
        "cashback": cashback,
        "xp": xp,               # level XP the payer got for it (merchant payments only)
        "items": items or [],   # what was bought, when a merchant charged a checkout cart
        "at": datetime.now().isoformat()
    })


def apply_cashback(payer_id, merchant_id, amount):
    """Pays cashback into the payer's Cultra balance for a payment to a merchant.
    Capped per customer, per category, per calendar month. Returns the amount given."""

    category_id = users[merchant_id]["merchant"]["merchant_category"]
    category = BUSINESS_CATEGORIES[category_id]

    # How much this customer already got in this category this month, e.g. key "2026-10:restaurants"
    earned = users[payer_id].setdefault("cashback_earned", {})
    key = datetime.now().strftime("%Y-%m") + ":" + category_id

    # Higher level = bigger caps (Gümüş ×1.25, Qızıl ×1.5, Platin ×2)
    cap = category["monthly_cap"] * LEVELS[current_level(payer_id)]["multiplier"]
    left_this_month = cap - earned.get(key, 0.0)

    cashback = round(min(amount * category["cashback"] / 100, left_this_month), 2)

    if cashback <= 0:
        return 0.0

    earned[key] = earned.get(key, 0.0) + cashback
    adjust_account_balance(payer_id, APP_BALANCE, cashback)   # always the Cultra balance, never a bank card
    return cashback


def record_topup(user_id, card_number, amount):
    transactions.append({
        "id": str(uuid.uuid4()),
        "kind": "topup",
        "user_id": user_id,
        "card_number": card_number,
        "amount": amount,
        "at": datetime.now().isoformat()
    })


def record_withdrawal(user_id, card_number, amount):
    transactions.append({
        "id": str(uuid.uuid4()),
        "kind": "withdrawal",
        "user_id": user_id,
        "card_number": card_number,
        "amount": amount,
        "at": datetime.now().isoformat()
    })


def record_card_transfer(user_id, from_account, to_card, amount):
    """Money sent from the app to a bank card number (send_card.html)."""
    transactions.append({
        "id": str(uuid.uuid4()),
        "kind": "card_transfer",
        "user_id": user_id,
        "username": users[user_id]["username"],
        "from_account": from_account,     # APP_BALANCE or one of the sender's cards
        "to_card": to_card,
        "amount": amount,
        "at": datetime.now().isoformat()
    })


def owns_card(user_id, card_number):
    """True if the card is linked to this user, as a personal card or a merchant bank account."""
    merchant = get_merchant(user_id)
    return card_number in users[user_id]["accounts"] or (
        merchant is not None and card_number in merchant["merchant_accounts"])


# ---------- Levels (XP) ----------

def rewards_of(user_id):
    """The user's XP data, created the first time it's needed (like "cashback_earned")."""
    return users[user_id].setdefault("rewards", {
        "xp_events": [],                              # {"at", "xp", "reason"}, oldest first
        "level": 0,                                   # index into LEVELS
        "checked": datetime.now().strftime("%Y-%m"),  # month of the last "1st of the month" check
        "paid_merchants": [],                         # merchants paid at least once (₼1 or more)
        "referred_by": None                           # who first sent them money by username
    })


def xp_in_window(user_id, at):
    """XP earned in the 90 days up to the moment `at`."""
    start = at - timedelta(days=XP_WINDOW_DAYS)
    return sum(event["xp"] for event in rewards_of(user_id)["xp_events"]
               if start < datetime.fromisoformat(event["at"]) <= at)


def first_of_next_month(month):
    """"2026-10" -> datetime(2026, 11, 1). December rolls over into January."""
    year, mon = int(month[:4]), int(month[5:7])
    return datetime(year + mon // 12, mon % 12 + 1, 1)


def current_level(user_id):
    """The user's level (index into LEVELS) after any "1st of the month" checks that are due.

    There's no timer: the first time a user is looked at in a new month, every 1st since the
    last check is replayed. On each one, if their XP from the 90 days before it is below their
    level's "keep" number, they drop one level."""
    rewards = rewards_of(user_id)
    this_month = datetime.now().strftime("%Y-%m")

    while rewards["checked"] < this_month:                  # "2026-10" < "2026-11" works as text
        first = first_of_next_month(rewards["checked"])
        level = rewards["level"]
        if level > 0 and xp_in_window(user_id, first) < LEVELS[level]["keep"]:
            rewards["level"] = level - 1
        rewards["checked"] = first.strftime("%Y-%m")

    return rewards["level"]


def award_xp(user_id, xp, reason):
    """Adds XP and ranks the user up straight away if they reached the next level.
    Returns the new level index if they ranked up, otherwise None."""
    level_before = current_level(user_id)       # any monthly drop that's due happens first
    rewards = rewards_of(user_id)

    now = datetime.now()
    rewards["xp_events"].append({"at": now.isoformat(), "xp": xp, "reason": reason})

    xp_now = xp_in_window(user_id, now)
    while rewards["level"] + 1 < len(LEVELS) and xp_now >= LEVELS[rewards["level"] + 1]["reach"]:
        rewards["level"] += 1

    return rewards["level"] if rewards["level"] > level_before else None


def xp_for_merchant_payment(payer_id, merchant_id, amount):
    """XP for paying a merchant (scanning their QR, or approving their checkout).
    Returns (XP the payer got, index of the level they just reached or None)."""
    if amount < XP_MIN_PAYMENT:
        return 0, None

    rewards = rewards_of(payer_id)
    gained, level_up = 0, None

    today = datetime.now().date().isoformat()
    payments_today = sum(1 for event in rewards["xp_events"]
                         if event["reason"] == "payment" and event["at"].startswith(today))
    if payments_today < XP_PAYMENTS_PER_DAY:
        gained += XP_PER_PAYMENT
        level_up = award_xp(payer_id, XP_PER_PAYMENT, "payment") or level_up

    if merchant_id not in rewards["paid_merchants"]:
        first_merchant_ever = not rewards["paid_merchants"]
        rewards["paid_merchants"].append(merchant_id)
        gained += XP_NEW_MERCHANT
        level_up = award_xp(payer_id, XP_NEW_MERCHANT, "new_merchant") or level_up

        # Their first merchant payment ever: the person who sent them money first gets XP
        referrer = rewards["referred_by"]
        if first_merchant_ever and referrer in users:
            award_xp(referrer, XP_REFERRAL, "referral")

    return gained, level_up


def level_info(index):
    """What the app gets about a level (None stays None)."""
    return None if index is None else dict(LEVELS[index])


def price_cart(items):
    """Cart lines from the app -> (lines with the server's names and prices, total in AZN, error).
    Only the barcode and quantity from the app are used; the price always comes from PRODUCTS."""

    if len(items) > 200:
        return None, None, "Səbətdə çox məhsul var"

    quantities = {}            # barcode -> qty (the same product sent twice is added up)
    for item in items:
        if item.barcode not in PRODUCTS:
            return None, None, "Məhsul tapılmadı: " + item.barcode
        if item.qty < 1 or item.qty > 999:
            return None, None, "Məhsulun sayı düzgün deyil"
        quantities[item.barcode] = quantities.get(item.barcode, 0) + item.qty

    lines = []
    total_qepik = 0            # whole qəpik, so 0.1 + 0.2 never becomes 0.30000000000000004
    for barcode, qty in quantities.items():
        product = PRODUCTS[barcode]
        total_qepik += round(product["price"] * 100) * qty
        lines.append({"barcode": barcode, "name": product["name"], "price": product["price"], "qty": qty})

    return lines, total_qepik / 100, None


def luhn_digit(digits):
    """Check digit, same method as bank card numbers. Catches a misread digit or two swapped digits."""
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return str((10 - total % 10) % 10)


def create_short_code(user_id, qr_data):
    """Saves qr_data under a new random 16-digit number and returns the number."""

    # Only the newest barcode works: throw away this user's older one(s)
    for code in list(short_codes):
        if short_codes[code]["user_id"] == user_id:
            del short_codes[code]

    while True:
        body = BARCODE_PREFIX + "".join(secrets.choice("0123456789") for _ in range(13))
        code = body + luhn_digit(body)            # 2 + 13 + 1 = 16 digits
        if code not in short_codes:
            break

    short_codes[code] = {"qr_data": qr_data, "user_id": user_id}
    return code


def resolve_short_code(code):
    """16-digit number from a scanner -> (original text, None) or (None, error reason)."""
    if len(code) != 16 or not (code.isascii() and code.isdigit()) or luhn_digit(code[:-1]) != code[-1]:
        return None, "Barkod düzgün oxunmadı"
    entry = short_codes.get(code)
    if entry is None:
        # Never existed, or the customer has opened their payment page again since (new barcode)
        return None, "Barkod tapılmadı və ya köhnədir"
    return entry["qr_data"], None




# ---------- Demo merchants (test data) ----------
# Each one is a normal user who has already registered as a merchant.
# Log in with the username + password 12345678, then press Merchant.

def demo_merchant(user_id, username, business_name, category, balance=0.0):
    users[user_id] = {
        "username": username,
        "password": "12345678",
        "accounts": {},
        "app_balance": 0.0,
        "merchant": {
            "merchant_id": "m-" + user_id,
            "merchant_category": category,     # must be a key of BUSINESS_CATEGORIES
            "business_name": business_name,
            "merchant_balance": balance,
            "merchant_accounts": {}
        }
    }

# Restaurants / cafes
demo_merchant("2001", "entree",       "Entrée",           "restaurants", 245.80)
demo_merchant("2002", "coffeemoffie", "Coffee Moffie",    "restaurants", 132.40)
demo_merchant("2003", "sumakh",       "Sumakh",           "restaurants", 310.00)

# Supermarkets
demo_merchant("2101", "bravo",        "Bravo",            "supermarkets", 1840.25)
demo_merchant("2102", "araz",         "Araz Supermarket", "supermarkets", 920.60)
demo_merchant("2103", "bazarstore",   "Bazarstore",       "supermarkets", 1275.10)
demo_merchant("2104", "oba",          "OBA Market",       "supermarkets", 488.35)

# Gas stations
demo_merchant("2201", "socar",        "SOCAR Petroleum",  "gas_stations", 2310.00)
demo_merchant("2202", "azpetrol",     "Azpetrol",         "gas_stations", 1560.45)

# Pharmacies
demo_merchant("2301", "zeytun",       "Zeytun Aptek",     "pharmacies", 402.90)

# Transport
demo_merchant("2401", "bakubus",      "BakuBus",          "transport", 655.00)
demo_merchant("2402", "metro",        "Bakı Metropoliteni", "transport", 980.20)
demo_merchant("2403", "ady",          "Azərbaycan Dəmir Yolları", "transport", 1120.75)


class RegisterRequest(BaseModel):
    username: str
    password: str


class AddBankCard(BaseModel):
    user_id: str
    number: str
    cvv: str
    month: str
    year: str
    # Literal = anything else gets rejected automatically. Default keeps old callers working.
    type: Literal["personal", "merchant"] = "personal"


class QRPayment(BaseModel):
    qr_data: str
    card_number: str
    user_id: str


class CartItem(BaseModel):
    barcode: str
    qty: int           # the name/price the app also sends are ignored: the server has its own prices


class PayQr(BaseModel):
    # No card_number: a merchant always receives into the merchant balance.
    qr_data: str
    user_id: str
    amount: float
    items: list[CartItem] = []    # the checkout cart; empty when the merchant typed an amount


class ConfirmPayment(BaseModel):
    payment_id: str
    user_id: str


class CancelPayment(BaseModel):
    payment_id: str
    user_id: str      # the merchant who made the request


class DeclinePayment(BaseModel):
    payment_id: str
    user_id: str


class AppBalance(BaseModel):
    user_id: str
    card_number: str
    amount: float
    currency: str


class RegisterMerchant(BaseModel):
    user_id: str
    category: str
    business_name: str


class BarcodeRequest(BaseModel):
    user_id: str
    account: str      # APP_BALANCE or one of the user's personal card numbers


class SendMoney(BaseModel):
    user_id: str          # who is sending
    to_username: str      # who gets it - always into their Cultra balance
    card_number: str      # pay from: APP_BALANCE or one of the sender's personal cards
    amount: float         # AZN


class SendToCard(BaseModel):
    user_id: str          # who is sending
    to_card: str          # 16-digit card number at any bank (here: any card in `bankcards`)
    card_number: str      # pay from: APP_BALANCE or one of the sender's personal cards
    amount: float         # AZN


class MerchantWithdraw(BaseModel):
    user_id: str
    card_number: str
    amount: float


#--------------auth------------


@app.post("/login")
def login(request: RegisterRequest):

    for user_id, user in users.items():

        if user["username"] == request.username.strip() and user["password"] == request.password:
            return {
                "status": "success",
                "user_id": user_id
            }

    return {
        "status": "failed",
        "reason": "İstifadəçi adı və ya parol yanlışdır"
    }
    


@app.post("/register")
def register(request: RegisterRequest):

    username = request.username.strip()

    # Others find you by this name (search, send money), so no empty or endless names
    if len(username) < 3 or len(username) > 20:
        return {"status": "failed", "reason": "İstifadəçi adı 3-20 simvol olmalıdır"}

    if len(request.password) < 8:
        return {
        "status": "failed",
        "reason": "Parol minimum 8 simvol olmalıdır"
    }

    # "emil" and "Emil" would look like the same person when sending money, so they count as taken
    for user in users.values():
        if user["username"].lower() == username.lower():
            return {
                "status": "failed",
                "reason": "Bu istifadəçi adı artıq götürülüb"
            }

    user_id = str(uuid.uuid4())

    users[user_id] = {
        "username": username,
        "password": request.password,
        "accounts": {},
        "app_balance": 0.0,
        "merchant": None
    }   

    return {
        "status": "success",
        "user_id": user_id,
        "username": username
    }


# Must stay ABOVE /users/{user_id}: FastAPI checks routes top to bottom, and
# /users/{user_id} would otherwise treat "search" as a user id
@app.get("/users/search")
def search_users(user_id: str, q: str = ""):
    """People to send money to, found by username: /users/search?q=al&user_id=123"""

    if user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    query = search_key(q.strip())

    # Nothing until 2 letters: keeps the list short and makes it harder to list every user
    if len(query) < 2:
        return {"status": "success", "users": []}

    matches = []
    for other_id, user in users.items():
        if other_id != user_id and query in search_key(user["username"]):   # never yourself
            matches.append(user["username"])

    # Exact name first, then names that start with the text, then the rest - A to Z inside each group
    matches.sort(key=lambda name: (search_key(name) != query, not search_key(name).startswith(query), name.lower()))

    # Usernames only. The user id works like a login in this prototype, so it's never listed.
    return {"status": "success", "users": [{"username": name} for name in matches[:10]]}


@app.get("/users/{user_id}")
def get_user(user_id: str):
    if user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    user = users[user_id]

    # Only what the app needs - never send the whole record (it contains the password)
    return {
        "status": "success",
        "username": user["username"],
        "is_merchant": user["merchant"] is not None
    }





#--------------bank cards--------------

# GET requests can't carry a body, so the type is a query parameter: /bankcards/123?type=merchant
@app.get("/bankcards/{user_id}")
def get_bank_cards(user_id: str, type: str = "personal"):

    if user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    if type == "personal":
        accounts = users[user_id]["accounts"]
    elif type == "merchant":
        if get_merchant(user_id) is None:
            return {"status": "failed", "reason": "Biznes hesabınız yoxdur"}
        accounts = get_merchant(user_id)["merchant_accounts"]
    else:
        return {"status": "failed", "reason": "Naməlum hesab növü"}

    return {
        "status": "success",
        "accounts": with_balances(accounts)
    }


@app.post("/addbank")
def addbank(request: AddBankCard):

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    if len(request.number) != 16 or len(request.cvv) != 3 or len(request.month) != 2 or len(request.year) != 2:
        return {"status": "failed", "reason": "Kart nömrəsi, CVV və ya tarix tam deyil"}

    card = bankcards.get(request.number)

    if (card is None or card["cvv"] != request.cvv or
            card["month"] != request.month or card["year"] != request.year):
        return {"status": "failed", "reason": "Kart tapıla bilmədi"}

    # Pick which list this card goes into
    if request.type == "merchant":
        if get_merchant(request.user_id) is None:
            return {"status": "failed", "reason": "Biznes hesabınız yoxdur"}
        target = get_merchant(request.user_id)["merchant_accounts"]
    else:
        target = users[request.user_id]["accounts"]

    if request.number in target:
        return {"status": "failed", "reason": "Bu bank hesabı artıq əlavə olunub"}

    # No balance copy here: the balance stays in `bankcards`
    target[request.number] = {
        "month": request.month,
        "year": request.year
    }

    return {"status": "success"}















@app.post("/pay")
def pay(request: QRPayment):

    print("QR received:", request.qr_data)
    parts = request.qr_data.split(":")

    if len(parts) != 5 or parts[0] != "PAY":
        return {"status": "failed", "reason": "QR kodu düzgün formatda deyil"}

    receiver_id, receiver_card, amount_str, currency = parts[1], parts[2], parts[3], parts[4]

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    # You can only spend from the app balance or a personal card - never a merchant balance
    if not can_pay_from(request.user_id, request.card_number):
        return {"status": "failed", "reason": "Ödəyicinin kartı tapılmadı"}

    # This also stops "app balance -> my own merchant balance -> withdraw to bank",
    # which would get around the one-way top-up rule
    if receiver_id == request.user_id:
        return {"status": "failed", "reason": "Özünüzə ödəniş edə bilməzsiniz"}

    if receiver_id not in users or not can_receive_into(receiver_id, receiver_card):
        return {"status": "failed", "reason": "Alıcı tapılmadı"}

    if currency == "AZN":
        try:
            amount = float(amount_str)
        except ValueError:
            return {"status": "failed", "reason": "Məbləğ düzgün deyil"}
    elif currency == "USD":
        try:
            amount = float(amount_str) * 1.7
        except ValueError:
            return {"status": "failed", "reason": "Məbləğ düzgün deyil"}
    else:
        return {"status": "failed", "reason": "Naməlum valyuta"}

    if not math.isfinite(amount) or amount <= 0:
        return {"status": "failed", "reason": "Məbləğ sıfırdan böyük olmalıdır"}

    if get_account_balance(request.user_id, request.card_number) < amount:
        return {"status": "failed", "reason": "Balans kifayət etmir"}

    adjust_account_balance(request.user_id, request.card_number, -amount)
    adjust_account_balance(receiver_id, receiver_card, amount)

    # Paying a merchant = the money goes into a MERCHANT_BALANCE. can_receive_into() above already
    # checked the receiver really is a registered merchant, so this can't be faked from the QR.
    cashback = 0.0
    xp, level_up = 0, None
    if receiver_card == MERCHANT_BALANCE:
        cashback = apply_cashback(request.user_id, receiver_id, amount)
        xp, level_up = xp_for_merchant_payment(request.user_id, receiver_id, amount)

    record_transaction(request.user_id, receiver_id, amount, receiver_card, cashback, xp=xp)

    return {
        "status": "success",
        "qr_data": request.qr_data,
        "cashback": cashback,
        "xp": xp,
        "level_up": level_info(level_up)     # the level they just reached, or None
    }


@app.post("/send")
def send_money(request: SendMoney):
    """Send money to someone found by username (send.html). It always goes into their Cultra balance."""

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    # Same sources as /pay: the app balance or a personal card, never a merchant balance
    if not can_pay_from(request.user_id, request.card_number):
        return {"status": "failed", "reason": "Ödəyicinin kartı tapılmadı"}

    receiver_id = find_user_id(request.to_username)
    if receiver_id is None:
        return {"status": "failed", "reason": "Alıcı tapılmadı"}

    if receiver_id == request.user_id:
        return {"status": "failed", "reason": "Özünüzə pul göndərə bilməzsiniz"}

    amount = round(request.amount, 2)       # whole qəpik
    if not math.isfinite(amount) or amount <= 0:
        return {"status": "failed", "reason": "Məbləğ sıfırdan böyük olmalıdır"}

    if get_account_balance(request.user_id, request.card_number) < amount:
        return {"status": "failed", "reason": "Balans kifayət etmir"}

    adjust_account_balance(request.user_id, request.card_number, -amount)
    adjust_account_balance(receiver_id, APP_BALANCE, amount)     # the receiver's Cultra balance

    # Shows as "Göndərildi: <them>" in your history and "Qəbul edildi: <you>" in theirs.
    # No cashback and no XP: those are only for paying merchants.
    record_transaction(request.user_id, receiver_id, amount, APP_BALANCE)

    # The first person to send money to someone who has never paid a merchant "brought them in":
    # when they make their first merchant payment, the sender gets XP_REFERRAL
    receiver_rewards = rewards_of(receiver_id)
    if receiver_rewards["referred_by"] is None and not receiver_rewards["paid_merchants"]:
        receiver_rewards["referred_by"] = request.user_id

    return {
        "status": "success",
        "to_username": users[receiver_id]["username"],
        "amount": amount
    }


@app.post("/send-to-card")
def send_to_card(request: SendToCard):
    """Send money to any bank card by its 16-digit number (send_card.html)."""

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    if not can_pay_from(request.user_id, request.card_number):
        return {"status": "failed", "reason": "Ödəyicinin kartı tapılmadı"}

    to_card = request.to_card.replace(" ", "")
    if len(to_card) != 16 or not (to_card.isascii() and to_card.isdigit()):
        return {"status": "failed", "reason": "Kart nömrəsi 16 rəqəm olmalıdır"}

    if to_card not in bankcards:
        return {"status": "failed", "reason": "Kart tapılmadı"}

    # Not to your own linked cards: Cultra balance -> own card would be a way to take
    # top-ups back out, and top-ups are one-way
    if owns_card(request.user_id, to_card):
        return {"status": "failed", "reason": "Öz kartınıza göndərə bilməzsiniz"}

    amount = round(request.amount, 2)       # whole qəpik
    if not math.isfinite(amount) or amount <= 0:
        return {"status": "failed", "reason": "Məbləğ sıfırdan böyük olmalıdır"}

    if get_account_balance(request.user_id, request.card_number) < amount:
        return {"status": "failed", "reason": "Balans kifayət etmir"}

    adjust_account_balance(request.user_id, request.card_number, -amount)
    bankcards[to_card]["balance"] += amount          # the bank's balance for that card

    record_card_transfer(request.user_id, request.card_number, to_card, amount)

    return {
        "status": "success",
        "to_card": "•••• " + to_card[-4:],
        "amount": amount
    }




















@app.post("/barcode")
def create_barcode(request: BarcodeRequest):

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    # The server builds the text itself, so nobody can make a barcode for someone else's account
    if not can_pay_from(request.user_id, request.account):
        return {"status": "failed", "reason": "Hesab tapılmadı"}

    qr_data = "PAY_QR:" + request.user_id + ":" + request.account
    code = create_short_code(request.user_id, qr_data)

    return {
        "status": "success",
        "code": code
    }


@app.post("/payqr")
def payqr(request: PayQr):

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    # Only registered merchants can scan a customer's payment QR. This is checked from the
    # user's profile on the server - a flag sent by the app can't be trusted.
    if get_merchant(request.user_id) is None:
        return {"status": "failed", "reason": "Biznes hesabınız yoxdur"}

    # A barcode (or its digits typed in by hand) is just a number: look up the text it stands for
    qr_data = request.qr_data.strip()
    from_barcode = qr_data.isascii() and qr_data.isdigit()

    if from_barcode:
        qr_data, error = resolve_short_code(qr_data)
        if error:
            return {"status": "failed", "reason": error}

    parts = qr_data.split(":")

    if len(parts) != 3 or parts[0] != "PAY_QR":
        return {"status": "failed", "reason": "QR kodu düzgün formatda deyil"}

    payer_id = parts[1]
    payer_card = parts[2]

    if payer_id not in users:
        return {"status": "failed", "reason": "Ödəniş edən istifadəçi tapılmadı"}

    if not can_pay_from(payer_id, payer_card):
        return {"status": "failed", "reason": "Ödəniş edən istifadəçinin hesabı tapılmadı"}

    if not math.isfinite(request.amount) or request.amount <= 0:
        return {"status": "failed", "reason": "Məbləğ sıfırdan böyük olmalıdır"}

    if payer_id == request.user_id:
        return {"status": "failed", "reason": "Özünüzə ödəniş edə bilməzsiniz"}

    # Checkout cart: the amount must be exactly what these products cost at the server's prices
    items = []
    if request.items:
        items, cart_total, error = price_cart(request.items)
        if error:
            return {"status": "failed", "reason": error}
        if abs(cart_total - request.amount) > 0.001:
            return {"status": "failed", "reason": f"Səbətin məbləği uyğun gəlmir: {cart_total:.2f} AZN olmalıdır"}

    payment_id = str(uuid.uuid4())

    pending_payments[payment_id] = {
        "payer_id": payer_id,
        "payer_card": payer_card,
        "receiver_id": request.user_id,
        "receiver_card": MERCHANT_BALANCE,
        "amount": request.amount,
        "items": items,
        "status": "pending"     # -> "accepted" | "declined" | "cancelled"
    }

    return {
        "status": "pending",
        "payment_id": payment_id,
        "amount": request.amount
    }












@app.get("/pending-payments/{user_id}")
def get_pending_payments(user_id: str):

    payments = []

    for payment_id, payment in pending_payments.items():

        if payment["payer_id"] == user_id and payment["status"] == "pending":

            payments.append({
                "payment_id": payment_id,
                "amount": payment["amount"],
                "receiver_id": payment["receiver_id"],
                "receiver_card": payment["receiver_card"],
                "payer_card": payment["payer_card"],
                "receiver_username": party_name(payment["receiver_id"], payment["receiver_card"]),
                "items": payment.get("items", [])
            })

    return {
        "status": "success",
        "payments": payments
    }











@app.get("/payment-status/{payment_id}")
def get_payment_status(payment_id: str):

    if payment_id not in pending_payments:
        return {
            "status": "failed",
            "reason": "Ödəniş tapılmadı"
        }

    payment = pending_payments[payment_id]

    return {
        "status": "success",
        "payment_status": payment["status"],  # "pending" | "accepted" | "declined" | "cancelled"
        "amount": payment["amount"]
    }










@app.post("/confirm-payment")
def confirm_payment(request: ConfirmPayment):

    if request.payment_id not in pending_payments:
        return {
            "status": "failed",
            "reason": "Ödəniş tapılmadı"
        }

    payment = pending_payments[request.payment_id]

    if request.user_id != payment["payer_id"]:
        return {
            "status": "failed",
            "reason": "Bu ödənişi təsdiqləmək icazəniz yoxdur"
        }

    if payment["status"] != "pending":
        return {
            "status": "failed",
            "reason": "Bu ödəniş artıq həll olunub"
        }

    payer_id = payment["payer_id"]
    receiver_id = payment["receiver_id"]
    payer_card = payment["payer_card"]
    receiver_card = payment["receiver_card"]

    amount = payment["amount"]

    if get_account_balance(payer_id, payer_card) < amount:
        return {
            "status": "failed",
            "reason": "Balans kifayət etmir"
        }

    adjust_account_balance(payer_id, payer_card, -amount)
    adjust_account_balance(receiver_id, receiver_card, amount)

    payment["status"] = "accepted"

    cashback = 0.0
    xp, level_up = 0, None
    if receiver_card == MERCHANT_BALANCE:
        cashback = apply_cashback(payer_id, receiver_id, amount)
        xp, level_up = xp_for_merchant_payment(payer_id, receiver_id, amount)

    record_transaction(payer_id, receiver_id, amount, receiver_card, cashback, payment.get("items", []), xp)

    return {
        "status": "success",
        "amount": amount,
        "cashback": cashback,
        "xp": xp,
        "level_up": level_info(level_up)     # the level they just reached, or None
    }











@app.post("/decline-payment")
def decline_payment(request: DeclinePayment):

    if request.payment_id not in pending_payments:
        return {
            "status": "failed",
            "reason": "Ödəniş tapılmadı"
        }

    payment = pending_payments[request.payment_id]

    if request.user_id != payment["payer_id"]:
        return {
            "status": "failed",
            "reason": "Bu ödənişi rədd etmək icazəniz yoxdur"
        }

    if payment["status"] != "pending":
        return {
            "status": "failed",
            "reason": "Bu ödəniş artıq həll olunub"
        }

    payment["status"] = "declined"

    return {
        "status": "success"
    }



@app.post("/cancel-payment")
def cancel_payment(request: CancelPayment):
    """The merchant withdraws a request the customer hasn't answered yet."""

    if request.payment_id not in pending_payments:
        return {"status": "failed", "reason": "Ödəniş tapılmadı"}

    payment = pending_payments[request.payment_id]

    # Only the merchant who asked for the money can withdraw the request
    if request.user_id != payment["receiver_id"]:
        return {"status": "failed", "reason": "Bu ödənişi ləğv etmək icazəniz yoxdur"}

    if payment["status"] != "pending":
        return {"status": "failed", "reason": "Bu ödəniş artıq həll olunub"}

    # No longer "pending": it disappears from the customer's popup, and confirming it now fails
    payment["status"] = "cancelled"

    return {"status": "success"}





@app.post("/app-balance")
def top_up_app_balance(request: AppBalance):

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    # The source must be a real bank card - you can't top up from the app balance itself
    if request.card_number not in users[request.user_id]["accounts"]:
        return {"status": "failed", "reason": "Ödəyicinin kartı tapılmadı"}

    if request.currency == "AZN":
        amount = request.amount
    elif request.currency == "USD":
        amount = request.amount * 1.7
    else:
        return {"status": "failed", "reason": "Naməlum valyuta"}

    if not math.isfinite(amount) or amount <= 0:
        return {"status": "failed", "reason": "Məbləğ sıfırdan böyük olmalıdır"}

    card = bankcards[request.card_number]

    if card["balance"] < amount:
        return {"status": "failed", "reason": "Balansda kifayət qədər məbləğ yoxdur"}

    card["balance"] -= amount
    users[request.user_id]["app_balance"] += amount

    record_topup(request.user_id, request.card_number, amount)

    return {
        "status": "success",
        "app_balance": users[request.user_id]["app_balance"],
        "card_balance": card["balance"]
    }





@app.get("/app-balance/{user_id}")
def get_app_balance(user_id: str):

    if user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    bank_total = sum(bankcards[number]["balance"] for number in users[user_id]["accounts"])

    return {
        "status": "success",
        "app_balance": users[user_id]["app_balance"],
        "bank_total": bank_total
    }




@app.get("/transactions/{user_id}")
def get_transactions(user_id: str, limit: int = 20):

    if user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    history = []

    for tx in transactions:
        kind = tx.get("kind")

        if kind == "topup":
            if tx["user_id"] == user_id:
                history.append({
                    "id": tx["id"],
                    "direction": "topup",
                    "other_username": None,
                    "card_number": tx["card_number"],
                    "amount": tx["amount"],
                    "at": tx["at"]
                })

        elif kind == "transfer":
            if tx["payer_id"] == user_id:
                history.append({
                    "id": tx["id"],
                    "direction": "sent",
                    "other_username": tx["receiver_username"],
                    "cashback": tx.get("cashback", 0.0),
                    "xp": tx.get("xp", 0),
                    "items": tx.get("items", []),
                    "amount": tx["amount"],
                    "at": tx["at"]
                })
            # Money that landed in a merchant balance belongs to the merchant history, not here
            elif tx["receiver_id"] == user_id and tx.get("receiver_account") != MERCHANT_BALANCE:
                history.append({
                    "id": tx["id"],
                    "direction": "received",
                    "other_username": tx["payer_username"],
                    "amount": tx["amount"],
                    "at": tx["at"]
                })

        elif kind == "card_transfer":
            if tx["user_id"] == user_id:
                history.append({
                    "id": tx["id"],
                    "direction": "sent",
                    "other_username": "Kart •••• " + tx["to_card"][-4:],
                    "amount": tx["amount"],
                    "at": tx["at"]
                })
            # The card belongs to another Cultra user: show it to them too
            elif tx["to_card"] in users[user_id]["accounts"]:
                history.append({
                    "id": tx["id"],
                    "direction": "received",
                    "other_username": tx["username"],
                    "amount": tx["amount"],
                    "at": tx["at"]
                })

        # "withdrawal" and anything new is skipped here on purpose

    history.reverse()  # newest first

    return {
        "status": "success",
        # limit=0 (or less) means "everything" - used by the full history page
        "transactions": history[:limit] if limit > 0 else history
    }











#---------cashback----------

@app.get("/cashback/{user_id}")
def get_cashback(user_id: str):
    """This month's cashback per category, next to each category's monthly cap (cashback.html)."""

    if user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    month = datetime.now().strftime("%Y-%m")            # same key format as apply_cashback()
    earned = users[user_id].get("cashback_earned", {})
    multiplier = LEVELS[current_level(user_id)]["multiplier"]

    categories = []
    for category_id, category in BUSINESS_CATEGORIES.items():
        categories.append({
            "id": category_id,
            "name": category["name"],
            "icon": category["icon"],
            "rate": category["cashback"],                # percent
            "earned": round(earned.get(month + ":" + category_id, 0.0), 2),
            "cap": round(category["monthly_cap"] * multiplier, 2),   # this user's cap, level included
            "base_cap": category["monthly_cap"]
        })

    return {
        "status": "success",
        "month": month,
        "multiplier": multiplier,
        "total": round(sum(c["earned"] for c in categories), 2),
        "categories": categories
    }


#---------levels (XP)----------

@app.get("/rewards/{user_id}")
def get_rewards(user_id: str):
    """Level, XP of the last 90 days, and what it takes to keep the level (cashback.html, main menu)."""

    if user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    level = current_level(user_id)
    now = datetime.now()
    next_check = first_of_next_month(now.strftime("%Y-%m"))

    return {
        "status": "success",
        "xp": xp_in_window(user_id, now),
        "level": level_info(level),
        "next_level": level_info(level + 1) if level + 1 < len(LEVELS) else None,
        # On the next 1st only the 90 days before it count, so "xp_then" is what they'll have
        # on that day if they don't pay anything until then. Bronze can't drop, so no check.
        "keep": None if level == 0 else {
            "date": next_check.date().isoformat(),
            "needed": LEVELS[level]["keep"],
            "xp_then": xp_in_window(user_id, next_check)
        },
        "levels": [level_info(i) for i in range(len(LEVELS))],
        "rules": {
            "per_payment": XP_PER_PAYMENT,
            "payments_per_day": XP_PAYMENTS_PER_DAY,
            "min_payment": XP_MIN_PAYMENT,
            "new_merchant": XP_NEW_MERCHANT,
            "referral": XP_REFERRAL,
            "window_days": XP_WINDOW_DAYS
        }
    }


#---------products----------

# The checkout loads the product list from here (barcode -> name + price)
@app.get("/products")
def get_products():
    return {"status": "success", "products": PRODUCTS}





#---------merchant----------

@app.post("/register_merchant")
def register_merchant(request: RegisterMerchant):

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    # Registering again would wipe the merchant balance and bank accounts
    if get_merchant(request.user_id) is not None:
        return {"status": "failed", "reason": "Biznes hesabınız artıq var"}

    if request.category not in BUSINESS_CATEGORIES:
        return {"status": "failed", "reason": "Naməlum kateqoriya"}

    business_name = request.business_name.strip()

    if len(business_name) < 2 or len(business_name) > 40:
        return {"status": "failed", "reason": "Biznesin adı 2-40 simvol olmalıdır"}

    for user in users.values():
        if user["merchant"] and user["merchant"]["business_name"].lower() == business_name.lower():
            return {"status": "failed", "reason": "Bu biznes adı artıq götürülüb"}

    merchant_id = str(uuid.uuid4())

    users[request.user_id]["merchant"] = {
        "merchant_id": merchant_id,
        "merchant_category": request.category,
        "business_name": business_name,
        "merchant_balance": 0.0,
        "merchant_accounts": {}
    }

    return {
        "status": "success",
        "merchant_id": merchant_id,
        "business_name": business_name
    }


@app.get("/merchant/categories")
def get_merchant_categories():
    return {"status": "success", "categories": BUSINESS_CATEGORIES}


# Customers see who they're paying before confirming (no balances or bank details in here)
@app.get("/merchant/public/{user_id}")
def get_merchant_public(user_id: str):

    if user_id not in users or get_merchant(user_id) is None:
        return {"status": "failed", "reason": "Biznes tapılmadı"}

    merchant = get_merchant(user_id)

    return {
        "status": "success",
        "business_name": merchant["business_name"],
        "category_info": BUSINESS_CATEGORIES.get(merchant["merchant_category"])
    }


@app.get("/merchant/transactions/{user_id}")
def get_merchant_transactions(user_id: str, limit: int = 20):

    if user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    if get_merchant(user_id) is None:
        return {"status": "failed", "reason": "Biznes hesabınız yoxdur"}

    history = []

    for tx in transactions:
        kind = tx.get("kind")

        if kind == "transfer" and tx["receiver_id"] == user_id and tx.get("receiver_account") == MERCHANT_BALANCE:
            history.append({
                "id": tx["id"],
                "direction": "received",
                "other_username": tx["payer_username"],
                "items": tx.get("items", []),
                "amount": tx["amount"],
                "at": tx["at"]
            })

        elif kind == "withdrawal" and tx["user_id"] == user_id:
            history.append({
                "id": tx["id"],
                "direction": "withdrawal",
                "other_username": None,
                "card_number": tx["card_number"],
                "amount": tx["amount"],
                "at": tx["at"]
            })

    history.reverse()  # newest first

    # limit=0 (or less) means "everything" - used by the "Check all" page
    if limit > 0:
        history = history[:limit]

    return {
        "status": "success",
        "transactions": history
    }


@app.post("/merchant/withdraw")
def merchant_withdraw(request: MerchantWithdraw):

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    merchant = get_merchant(request.user_id)

    if merchant is None:
        return {"status": "failed", "reason": "Biznes hesabınız yoxdur"}

    # Only to a MERCHANT bank account (never a personal card)
    if request.card_number not in merchant["merchant_accounts"]:
        return {"status": "failed", "reason": "Bank hesabı tapılmadı"}

    if not math.isfinite(request.amount) or request.amount <= 0:
        return {"status": "failed", "reason": "Məbləğ sıfırdan böyük olmalıdır"}

    if merchant["merchant_balance"] < request.amount:
        return {"status": "failed", "reason": "Biznes balansında kifayət qədər pul yoxdur"}

    merchant["merchant_balance"] -= request.amount
    bankcards[request.card_number]["balance"] += request.amount

    record_withdrawal(request.user_id, request.card_number, request.amount)

    return {
        "status": "success",
        "merchant_balance": merchant["merchant_balance"],
        "card_balance": bankcards[request.card_number]["balance"]
    }


# Keep this LAST: "/merchant/{user_id}" would also match "/merchant/categories" if it came first
@app.get("/merchant/{user_id}")
def get_merchant_info(user_id: str):

    if user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    merchant = get_merchant(user_id)

    if merchant is None:
        return {"status": "success", "registered": False, "merchant": None}

    # Sales today = customer payments that landed in the merchant balance today (withdrawals don't count)
    today = datetime.now().date()
    sales_today = [
        tx for tx in transactions
        if tx.get("kind") == "transfer"
        and tx["receiver_id"] == user_id
        and tx.get("receiver_account") == MERCHANT_BALANCE
        and datetime.fromisoformat(tx["at"]).date() == today
    ]

    # Total sitting on the merchant's linked bank accounts (separate from the merchant balance)
    bank_total = sum(bankcards[number]["balance"] for number in merchant["merchant_accounts"])

    return {
        "status": "success",
        "registered": True,
        "merchant": {
            "merchant_id": merchant["merchant_id"],
            "business_name": merchant["business_name"],
            "category": merchant["merchant_category"],
            "category_info": BUSINESS_CATEGORIES.get(merchant["merchant_category"]),
            "merchant_balance": merchant["merchant_balance"],
            "bank_total": bank_total,
            "sales_today": len(sales_today),
            "sales_today_amount": sum(tx["amount"] for tx in sales_today)
        }
    }

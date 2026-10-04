from fastapi import FastAPI
from pydantic import BaseModel
from typing import Literal
import math
import uuid
from datetime import datetime

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


BUSINESS_CATEGORIES = {
    "restaurants":  {"name": "Restaurants/cafes", "icon": "🍔", "cashback": 1.8, "monthly_cap": 10.0},
    "supermarkets": {"name": "Supermarkets",      "icon": "🛒", "cashback": 0.5, "monthly_cap": 5.0},
    "gas_stations": {"name": "Gas stations",      "icon": "⛽", "cashback": 0.5,  "monthly_cap": 5.0},
    "pharmacies":   {"name": "Pharmacies",        "icon": "💊", "cashback": 1.0, "monthly_cap": 5.0},
    "transport":    {"name": "Transport",         "icon": "🚕", "cashback": 1.0, "monthly_cap": 3.0},
}


def get_merchant(user_id):
    """The user's merchant profile, or None if they never registered as a merchant."""
    return users[user_id]["merchant"]


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


def record_transaction(payer_id, receiver_id, amount, receiver_account=None):
    transactions.append({
        "id": str(uuid.uuid4()),
        "kind": "transfer",
        "payer_id": payer_id,
        "payer_username": users[payer_id]["username"],
        "receiver_id": receiver_id,
        "receiver_username": party_name(receiver_id, receiver_account),
        "receiver_account": receiver_account,  # MERCHANT_BALANCE sends it to the merchant history
        "amount": amount,
        "at": datetime.now().isoformat()
    })


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


class PayQr(BaseModel):
    # No card_number: a merchant always receives into the merchant balance.
    qr_data: str
    user_id: str
    amount: float


class ConfirmPayment(BaseModel):
    payment_id: str
    user_id: str


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


class MerchantWithdraw(BaseModel):
    user_id: str
    card_number: str
    amount: float


#--------------auth------------


@app.post("/login")
def login(request: RegisterRequest):

    for user_id, user in users.items():

        if user["username"] == request.username and user["password"] == request.password:
            return {
                "status": "success",
                "user_id": user_id
            }

    return {
        "status": "failed",
        "reason": "İstifadəçi adı vəya parol yanlışdır"
    }
    


@app.post("/register")
def register(request: RegisterRequest):

    if len(request.password) < 8:
        return {
        "status": "failed",
        "reason": "Parol minimum 8 simvol olmalıdır"
    }

    for user in users.values():
        if user["username"] == request.username:
            return {
                "status": "failed",
                "reason": "Bu istifadəçi adı artıq götürülüb"
            }

    user_id = str(uuid.uuid4())

    users[user_id] = {
        "username": request.username,
        "password": request.password,
        "accounts": {},
        "app_balance": 0.0,
        "merchant": None
    }   

    return {
        "status": "success",
        "user_id": user_id,
        "username": request.username
    }


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
            return {"status": "failed", "reason": "You're not a merchant"}
        accounts = get_merchant(user_id)["merchant_accounts"]
    else:
        return {"status": "failed", "reason": "Unknown account type"}

    return {
        "status": "success",
        "accounts": with_balances(accounts)
    }


@app.post("/addbank")
def addbank(request: AddBankCard):

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    if len(request.number) != 16 or len(request.cvv) != 3 or len(request.month) != 2 or len(request.year) != 2:
        return {"status": "failed", "reason": "Kart nömrəsi, CVV, vəya tarix əksikdir"}

    card = bankcards.get(request.number)

    if (card is None or card["cvv"] != request.cvv or
            card["month"] != request.month or card["year"] != request.year):
        return {"status": "failed", "reason": "Kart tapıla bilmədi"}

    # Pick which list this card goes into
    if request.type == "merchant":
        if get_merchant(request.user_id) is None:
            return {"status": "failed", "reason": "You're not a merchant"}
        target = get_merchant(request.user_id)["merchant_accounts"]
    else:
        target = users[request.user_id]["accounts"]

    if request.number in target:
        return {"status": "failed", "reason": "This bank account is already added"}

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
    record_transaction(request.user_id, receiver_id, amount, receiver_card)

    return {
        "status": "success",
        "qr_data": request.qr_data
    }




















@app.post("/payqr")
def payqr(request: PayQr):

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    # Only registered merchants can scan a customer's payment QR. This is checked from the
    # user's profile on the server - a flag sent by the app can't be trusted.
    if get_merchant(request.user_id) is None:
        return {"status": "failed", "reason": "You're not a merchant"}

    parts = request.qr_data.split(":")

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

    payment_id = str(uuid.uuid4())

    pending_payments[payment_id] = {
        "payer_id": payer_id,
        "payer_card": payer_card,
        "receiver_id": request.user_id,
        "receiver_card": MERCHANT_BALANCE,
        "amount": request.amount,
        "status": "pending"
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
                "receiver_username": party_name(payment["receiver_id"], payment["receiver_card"])
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
        "payment_status": payment["status"],  # "pending" | "accepted" | "declined"
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

    record_transaction(payer_id, receiver_id, amount, receiver_card)

    return {
        "status": "success",
        "amount": amount
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
def get_transactions(user_id: str):

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

        # "withdrawal" and anything new is skipped here on purpose

    history.reverse()  # newest first

    return {
        "status": "success",
        "transactions": history[:20]
    }











#---------merchant----------

@app.post("/register_merchant")
def register_merchant(request: RegisterMerchant):

    if request.user_id not in users:
        return {"status": "failed", "reason": "İstifadəçi tapılmadı"}

    # Registering again would wipe the merchant balance and bank accounts
    if get_merchant(request.user_id) is not None:
        return {"status": "failed", "reason": "You're already registered as a merchant"}

    if request.category not in BUSINESS_CATEGORIES:
        return {"status": "failed", "reason": "Unknown category"}

    business_name = request.business_name.strip()

    if len(business_name) < 2 or len(business_name) > 40:
        return {"status": "failed", "reason": "Business name must be 2-40 characters"}

    for user in users.values():
        if user["merchant"] and user["merchant"]["business_name"].lower() == business_name.lower():
            return {"status": "failed", "reason": "This business name is already taken"}

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
        return {"status": "failed", "reason": "Merchant not found"}

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
        return {"status": "failed", "reason": "You're not a merchant"}

    history = []

    for tx in transactions:
        kind = tx.get("kind")

        if kind == "transfer" and tx["receiver_id"] == user_id and tx.get("receiver_account") == MERCHANT_BALANCE:
            history.append({
                "id": tx["id"],
                "direction": "received",
                "other_username": tx["payer_username"],
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
        return {"status": "failed", "reason": "You're not a merchant"}

    # Only to a MERCHANT bank account (never a personal card)
    if request.card_number not in merchant["merchant_accounts"]:
        return {"status": "failed", "reason": "Bank account not found"}

    if not math.isfinite(request.amount) or request.amount <= 0:
        return {"status": "failed", "reason": "Məbləğ sıfırdan böyük olmalıdır"}

    if merchant["merchant_balance"] < request.amount:
        return {"status": "failed", "reason": "Not enough merchant balance"}

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

import qrcode

data = "PAY:123:1234123412341234:50.00:AZN"

balance_data = "PAY_QR:123:APP_BALANCE"

pay_qr_data = "PAY_QR:123:1234123412341234"

qr = qrcode.make(data)

qr.save("qr.png")

balanceqr = qrcode.make (balance_data)
balanceqr.save("appbalance.png")

receive_qr = qrcode.make(pay_qr_data)

receive_qr.save("receive_qr.png")
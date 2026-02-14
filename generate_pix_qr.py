import qrcode

pix_link = "https://nubank.com.br/cobrar/1h7aul/698663c8-916a-42de-943b-c5a3b87b1b88"

img = qrcode.make(pix_link)

img.save("static/img/pix_nubank_qr.png")

print("QR Code gerado com sucesso!")
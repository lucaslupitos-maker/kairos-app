import qrcode

pix_payload = (
    "00020126360014BR.GOV.BCB.PIX"
    "011142506340866"
    "52040000"
    "5303986"
    "5802BR"
    "5924Lucas Castiglioni Toledo"
    "6009SAO PAULO"
    "6304"
)

img = qrcode.make(pix_payload)
img.save("pix_nubank_qr.png")
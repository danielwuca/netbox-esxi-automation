import smtplib
import mimetypes
from email.mime.multipart import MIMEMultipart
from email import encoders
from email.message import Message
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.text import MIMEText

class emailsend:
    def __init__(self, emailto):
        self.emailfrom = ""
        self.emailto = emailto
        self.email_server = ""
    '''
        This function will send report to the user email.
    '''

    def send_email_to(self,fileToSend, subject, body):
        msg = MIMEMultipart()
        msg["From"] = self.emailfrom
        msg["To"] = ",".join(self.emailto)
        #msg["To"] = self.emailto
        msg["Subject"] = subject
        msg.preamble = subject
        msg.attach(MIMEText(body, _subtype='plain', _charset='UTF-8'))

        ctype, encoding = mimetypes.guess_type(fileToSend)

        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"

        maintype, subtype = ctype.split("/", 1)

        if maintype == "text":
            fp = open(fileToSend)
            # Note: we should handle calculating the charset
            attachment = MIMEText(fp.read(), _subtype=subtype)
            fp.close()
        else:
            fp = open(fileToSend, "rb")
            attachment = MIMEBase(maintype, subtype)
            attachment.set_payload(fp.read())
            fp.close()
            encoders.encode_base64(attachment)

        attachment.add_header("Content-Disposition", "attachment", filename=fileToSend)
        msg.attach(attachment)
        server = smtplib.SMTP(self.email_server)
        server.set_debuglevel(0)
        server.sendmail(self.emailfrom, self.emailto, msg.as_string())
        server.quit()



  # version 2

import smtplib
gmail_user = 'moh.vmcreationnotify@outlook.com'
gmail_password = ''

sent_from = gmail_user
to = ['zhenyudaniel.wu@ontario.ca']
subject = 'Testing'
body = 'Testing python email sending function'

try:
    smtp_server = smtplib.SMTP_SSL('smtp-mail.outlook.com', 587)
    smtp_server.ehlo()
    smtp_server.login(gmail_user, gmail_password)
    smtp_server.sendmail(sent_from, to, email_text)
    smtp_server.close()
    print ("Email sent successfully!")
except Exception as ex:
    print ("Something went wrong….",ex)

from email.message import EmailMessage
import smtplib

sender = "moh.vmcreationnotify@outlook.com"
recipient = "zhenyudaniel.wu@ontario.ca"
message = "Testing python email sending function"

email = EmailMessage()
email["From"] = sender
email["To"] = recipient
email["Subject"] = "Test Email"
email.set_content(message)

smtp = smtplib.SMTP("smtp-mail.outlook.com", port=587)
smtp.starttls()
smtp.login(sender, "Password01!")
smtp.sendmail(sender, recipient, email.as_string())
smtp.quit()

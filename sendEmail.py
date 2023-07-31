import smtplib, ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import cred

# message = None

def get_credentials():
  credentials = {
    'sender_email': cred.sender_email,
    'receiver_email': cred.receiver_email,
    #password = input("Type your password and press enter:")
    'password': cred.sender_password
  }

  return credentials

def get_message_header(sender, receiver, subject):
  message = MIMEMultipart("alternative")
  message["Subject"] = subject
  message["From"] = sender
  message["To"] = receiver

  return message


# Create the plain-text and HTML version of your message
def create_message():
  text = """\
  Testing Sending an Email.
  """
  html = """\
  <html>
    <body>
      <p>If you get this, then it worked.</p>
    </body>
  </html>
  """
  return dict({
    'text': text,
    'html': html
  })

# Turn these into plain/html MIMEText objects
def get_MIME_text(text, html):
  mime_parts = {
    'part1': MIMEText(text, "plain"),
    'part2': MIMEText(html, "html")
  }

  return mime_parts

# Add HTML/plain-text parts to MIMEMultipart message
# The email client will try to render the last part first
def attach_MIME(message, part1, part2):
  message.attach(part1)
  message.attach(part2)

  return message

# filename = "image.png"

# Open PDF file in binary mode
# with open(filename, "rb") as attachment:
#     # Add file as application/octet-stream
#     # Email client can usually download this automatically as attachment
#     part = MIMEBase("application", "octet-stream")
#     part.set_payload(attachment.read())

# Encode file in ASCII characters to send by email    
# encoders.encode_base64(part)

# Add header as key/value pair to attachment part
# part.add_header(
#     "Content-Disposition",
#     f"attachment; filename= {filename}",
# )

# Add attachment to message and convert message to string
# message.attach(part)
# text = message.as_string()

# Create secure connection with server and send email
def send_message():
  credentials = get_credentials()
  message = get_message_header(credentials['sender_email'], credentials['receiver_email'], "Test Message")
  message_text = create_message()
  mime_text = get_MIME_text(message_text['text'], message_text['html'])
  message = attach_MIME(message, mime_text['part1'], mime_text['part2'] )

  context = ssl.create_default_context()
  with smtplib.SMTP_SSL(cred.mail_server, cred.mail_port, context=context) as server:
      server.login(credentials['sender_email'], credentials['password'])
      server.sendmail(
          credentials['sender_email'], credentials['receiver_email'], message.as_string()
      )

# send the otp to the user's email address
def send_otp_email(otp_message, email):
  credentials = {
    'sender_email': cred.sender_email,
    'receiver_email': email,
    'password': cred.sender_password
  }
  message = get_message_header(credentials['sender_email'], credentials['receiver_email'], "Login OTP")
  # the message text is a dictionary - plain text and html versions
  message_text = dict({
    'text': otp_message,
    'html': f"<html><body>{otp_message}</body></html>"
  })
  # convert this to MIME for sending
  mime_message = get_MIME_text(message_text['text'], message_text['html'])
  # attach the MIME to the message.
  message = attach_MIME(message, mime_message['part1'], mime_message['part2'])
  # connect to the server and send the message
  context = ssl.create_default_context()
  with smtplib.SMTP_SSL(cred.mail_server, cred.mail_port, context=context) as server:
      server.login(credentials['sender_email'], credentials['password'])
      server.sendmail(
          credentials['sender_email'], credentials['receiver_email'], message.as_string()
      )

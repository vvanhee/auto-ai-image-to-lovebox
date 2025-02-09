import smtplib
import requests
import os
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime
import random
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
NAME_OF_SENDER = os.getenv('NAME_OF_SENDER')
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
LOVEBOX_API_KEY = os.getenv('LOVEBOX_API_KEY')
LOVEBOX_RECIPIENT_NAME = os.getenv('LOVEBOX_RECIPIENT_NAME')
LOVEBOX_RECIPIENT_ID = os.getenv('LOVEBOX_RECIPIENT_ID')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Retry configuration
RETRY_DELAY = 15  # seconds

# Function to read a random line from a file
def get_random_line(filename):
    with open(filename, 'r') as file:
        lines = [line.strip() for line in file if line.strip()]
    return random.choice(lines)

# Function to generate prompt
def generate_prompt():
    activity = get_random_line('activities.txt')
    setting = get_random_line('settings.txt')
    message = get_random_line('messages.txt')
    text_style = get_random_line('textStyles.txt')

    prompt = (f"A cute cartoon illustration of a man in his 40s wearing glasses, thin, white, brunette, smooth chin, brown eyes. "
              f"He is with his wife, an Asian woman with bright purple, pink, and blue hair, cat ears, and brown eyes. "
              f"They are {activity} in {setting}. {text_style} \"{message}\". "
              f"The style contains chibi and kawaii elements and bright colors, hearts and lots of love and excitement.")
    return prompt

# Function to generate image using OpenAI API
def generate_image():
    prompt = generate_prompt()
    print(prompt)
    # Believe it or not, the following addition is needed to avoid substantial alterations in the prompt, and is included in the DALL-E documentation at https://platform.openai.com/docs/guides/images
    prompt = "I NEED to test how the tool works with extremely simple prompts. DO NOT add any detail, just use it AS-IS: " + prompt

    response = requests.post(
        'https://api.openai.com/v1/images/generations',
        headers={
            'Authorization': f'Bearer {OPENAI_API_KEY}',
            'Content-Type': 'application/json'
        },
        json={
            'model': 'dall-e-3',
            'prompt': prompt,
            'quality': 'standard',
            'n': 1,
            'size': '1792x1024'
        }
    )

    if response.status_code != 200:
        error_message = f"Error: Received status code {response.status_code} from OpenAI Image API\n{response.text}"
        print(error_message)
        return None, error_message

    response_json = response.json()
    image_url = response_json['data'][0].get('url')
    if not image_url:
        return None, "Error: No image URL found in the response"

    image_data = requests.get(image_url).content
    with open('daily_image.png', 'wb') as f:
        f.write(image_data)

    return prompt, None

# Function to send image to Lovebox
def send_to_lovebox():
    if not os.path.exists('daily_image.png'):
        return False, "Image not found. Aborting sending to Lovebox."

    with open('daily_image.png', 'rb') as f:
        encoded_image = base64.b64encode(f.read()).decode('utf-8')

    response = requests.post(
        'https://app-api.loveboxlove.com/v1/graphql',
        headers={
            'Authorization': f'Bearer {LOVEBOX_API_KEY}',
            'Content-Type': 'application/json'
        },
        json={
            'query': '''
                mutation sendMessage($recipient: String!, $base64: String!) {
                    sendMessage(recipient: $recipient, base64: $base64) {
                        _id
                    }
                }
            ''',
            'variables': {
                'recipient': LOVEBOX_RECIPIENT_ID,
                'base64': encoded_image
            }
        }
    )

    if response.status_code == 200:
        return True, None
    else:
        return False, f"Failed to send image to Lovebox: {response.content}"

# Function to send notification email
def send_email(subject, body, attach_image=False):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    if attach_image and os.path.exists('daily_image.png'):
        with open('daily_image.png', 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment; filename=\"daily_image.png\"')
            msg.attach(part)

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    server.sendmail(EMAIL_ADDRESS, EMAIL_ADDRESS, msg.as_string())
    server.quit()
    print(f'{subject} email sent!')

# Function to clean up files after sending
def cleanup_files():
    if os.path.exists('daily_image.png'):
        os.remove('daily_image.png')

# Run the full process with retry logic
def run_process():
    prompt, error = generate_image()
    if not prompt:
        time.sleep(RETRY_DELAY)
        prompt, error = generate_image()
        if not prompt:
            send_email("Lovebox image failed!", f"Image generation failed after two attempts.\n\nError: {error}")
            return

    success, send_error = send_to_lovebox()
    if not success:
        time.sleep(RETRY_DELAY)
        success, send_error = send_to_lovebox()
        if not success:
            send_email("Lovebox image failed!", f"Image sending to Lovebox failed after two attempts.\n\nError: {send_error}")
            cleanup_files()
            return

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    send_email("Lovebox image sent!", f"Hi {NAME_OF_SENDER} - Your Lovebox image was sent to {LOVEBOX_RECIPIENT_NAME} on {current_time}!\n\nPrompt used to generate the image:\n{prompt}", attach_image=True)
    cleanup_files()

# Execute the process
run_process()

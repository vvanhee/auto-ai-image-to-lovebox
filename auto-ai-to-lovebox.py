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
from google import genai
from google.genai import types
from PIL import Image

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
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

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
    image_style = get_random_line('imageStyles.txt')
    more_style = get_random_line('moreStyles.txt')
    date_str = datetime.now().strftime("%B")
    prompt = (f"A {image_style} of me and my wife. Her name is Ericka. "
              f"Make it include a loving message to her in English appropriate for {date_str}. ")
              # f"They are {activity} in {setting}. {text_style} \"{message}\". "
              # f"{more_style}")
    return prompt

# Function to generate image using Gemini API
def generate_image():
    prompt = generate_prompt()
    print(prompt)
    
    # Get random image from images directory
    image_dir = 'images'
    if not os.path.exists(image_dir):
        return None, f"Error: {image_dir} directory not found"
        
    images = [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
    if not images:
        return None, "Error: No images found in images directory"
        
    random_image_file = random.choice(images)
    image_path = os.path.join(image_dir, random_image_file)
    print(f"Using image: {image_path}")

    try:
        image = Image.open(image_path)
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=[prompt, image],
            config=types.GenerateContentConfig(
                image_config=types.ImageConfig(
                    aspect_ratio="4:3",
                )
            )
        )
        
        generated_image_saved = False
        if response.parts:
            for part in response.parts:
                if part.inline_data is not None:
                    img = part.as_image()
                    img.save("daily_image.png")
                    generated_image_saved = True
                    break
        
        if not generated_image_saved:
             return None, "Error: No image generated in response"

        return prompt, None

    except Exception as e:
        return None, f"Error generating image: {str(e)}"

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

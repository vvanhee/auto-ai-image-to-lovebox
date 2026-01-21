import smtplib
import requests
import os
import json
import hashlib
import base64
import argparse
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
LOVEBOX_RECIPIENT_ID2 = os.getenv('LOVEBOX_RECIPIENT_ID2')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Retry configuration
RETRY_DELAY = 15  # seconds

CYCLE_STATE_FILENAME = ".cycle_state.json"
CYCLE_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CYCLE_STATE_FILENAME)


def _read_non_empty_lines(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        return [line.strip() for line in file if line.strip()]


def _load_cycle_state():
    try:
        if not os.path.exists(CYCLE_STATE_PATH):
            return {}
        with open(CYCLE_STATE_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cycle_state(state):
    try:
        with open(CYCLE_STATE_PATH, 'w', encoding='utf-8') as file:
            json.dump(state, file, indent=2)
        return True
    except Exception:
        return False


def _items_signature(items):
    normalized = "\n".join(sorted(items))
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def shuffle_cycle_choice(key, items):
    unique_items = list(dict.fromkeys(items))
    if not unique_items:
        raise ValueError("No items available for shuffle cycle")

    signature = _items_signature(unique_items)
    state = _load_cycle_state()
    entry = state.get(key)

    if (
        not isinstance(entry, dict)
        or entry.get('signature') != signature
        or not isinstance(entry.get('order'), list)
        or len(entry.get('order')) != len(unique_items)
    ):
        order = unique_items[:]
        random.shuffle(order)
        entry = {'signature': signature, 'order': order, 'index': 0}
        state[key] = entry

    order = entry['order']
    index = entry.get('index', 0)
    if not isinstance(index, int) or index < 0:
        index = 0

    if index >= len(order):
        order = unique_items[:]
        random.shuffle(order)
        entry['order'] = order
        index = 0

    choice = order[index]
    entry['index'] = index + 1
    state[key] = entry

    if not _save_cycle_state(state):
        return random.choice(unique_items)

    return choice

# Function to read a random line from a file
def get_random_line(filename):
    lines = _read_non_empty_lines(filename)
    return random.choice(lines)


def get_shuffle_cycle_line(filename):
    lines = _read_non_empty_lines(filename)
    key = f"file:{os.path.basename(filename)}"
    return shuffle_cycle_choice(key, lines)

# Function to generate prompt
def generate_prompt():
    activity = get_random_line('activities.txt')
    setting = get_random_line('settings.txt')
    message = get_random_line('messages.txt')
    text_style = get_random_line('textStyles.txt')
    image_style = get_shuffle_cycle_line('imageStyles.txt')
    more_style = get_random_line('moreStyles.txt')

    prompt = (f"A cute single panel cartoon of me (a caucasian man named Victor) and my wife "
              f"(an Asian woman named Ericka). "
              f"Search for an interesting national or international holiday for today and "
              f"the weather in Minneapolis and current events and make the image relevant to "
              f"the holiday or the weather or current events, "
              f"with us performing relevant and interesting activities. Use the images to see what we look like. "
              f"Also include a funny and witty short caption in English appropriate for the theme. ")
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
        return None, None, f"Error: {image_dir} directory not found"
        
    images = [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
    if not images:
        return None, None, "Error: No images found in images directory"
        
    random_image_file = shuffle_cycle_choice('images_dir:images', images)
    image_path = os.path.join(image_dir, random_image_file)
    print(f"Using image: {image_path}")

    try:
        image = Image.open(image_path)
        
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=[prompt, image],
            config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE'],
                tools=[{"google_search": {}}],
                image_config=types.ImageConfig(
                    aspect_ratio="4:3",
                    image_size="2K"
                )
            )
        )
        
        generated_image_saved = False
        generated_text = ""
        if response.parts:
            for part in response.parts:
                if part.inline_data is not None:
                    img = part.as_image()
                    img.save("daily_image.png")
                    generated_image_saved = True
                if part.text:
                    generated_text += part.text + "\n"
        
        if not generated_image_saved:
             return None, None, "Error: No image generated in response"

        return prompt, generated_text, None

    except Exception as e:
        return None, None, f"Error generating image: {str(e)}"

# Function to send image to Lovebox
def send_to_lovebox(recipient_id):
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
                'recipient': recipient_id,
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
def run_process(recipient_id):
    prompt, generated_text, error = generate_image()
    if error:
        time.sleep(RETRY_DELAY)
        prompt, generated_text, error = generate_image()
        if error:
            send_email("Lovebox image failed!", f"Image generation failed after two attempts.\n\nError: {error}")
            return

    success, send_error = send_to_lovebox(recipient_id)
    if not success:
        time.sleep(RETRY_DELAY)
        success, send_error = send_to_lovebox(recipient_id)
        if not success:
            send_email("Lovebox image failed!", f"Image sending to Lovebox failed after two attempts.\n\nError: {send_error}")
            cleanup_files()
            return

    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    body = f"Hi {NAME_OF_SENDER} - Your Lovebox image was sent to {LOVEBOX_RECIPIENT_NAME} on {current_time}!\n\nPrompt used to generate the image:\n{prompt}"
    if generated_text:
        body += f"\n\nModel Output:\n{generated_text}"
        
    send_email("Lovebox image sent!", body, attach_image=True)
    cleanup_files()

# Execute the process
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Send AI generated image to Lovebox.')
    parser.add_argument('--id2', action='store_true', help='Use the second recipient ID')
    args = parser.parse_args()

    recipient_id = LOVEBOX_RECIPIENT_ID2 if args.id2 else LOVEBOX_RECIPIENT_ID
    
    if not recipient_id:
        print("Error: Recipient ID not found in environment variables.")
    else:
        run_process(recipient_id)

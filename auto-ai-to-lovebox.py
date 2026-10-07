import smtplib
import requests
import os
import re
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

# Always work relative to the script's folder (systemd, cron, etc.)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

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

# Models (override in .env). The "art director" is a text model that writes a coherent
# brief; the image models are tried in order until one works.
DIRECTOR_MODEL = os.getenv('DIRECTOR_MODEL', 'gemini-3.8-flash')
IMAGE_MODELS = [m.strip() for m in os.getenv(
    'IMAGE_MODELS', 'gemini-3-pro-image,gemini-3-pro-image-preview').split(',') if m.strip()]
HOME_LOCATION = os.getenv('HOME_LOCATION', '')        # e.g. "Minneapolis, Minnesota" — for seasons/weather jokes
MAX_REFERENCE_IMAGES = int(os.getenv('MAX_REFERENCE_IMAGES', '3'))
HISTORY_LENGTH = int(os.getenv('HISTORY_LENGTH', '30'))  # recent ideas the director must not repeat

# Retry configuration
RETRY_DELAY = 15  # seconds

CYCLE_STATE_PATH = os.path.join(SCRIPT_DIR, ".cycle_state.json")
HISTORY_PATH = os.path.join(SCRIPT_DIR, ".history.json")
OUTPUT_IMAGE = "daily_image.png"


# --------------------------------------------------------------------------- #
# Word-list helpers
# --------------------------------------------------------------------------- #

def _read_non_empty_lines(filename):
    """Non-empty lines, ignoring # comments. Missing file -> []."""
    if not os.path.exists(filename):
        return []
    with open(filename, 'r', encoding='utf-8') as file:
        return [line.strip() for line in file if line.strip() and not line.strip().startswith('#')]


def _load_json(path, default):
    try:
        if not os.path.exists(path):
            return default
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            return data if isinstance(data, type(default)) else default
    except Exception:
        return default


def _save_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _items_signature(items):
    normalized = "\n".join(sorted(items))
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def shuffle_cycle_choice(key, items, count=1):
    """Deal items from a shuffled deck so nothing repeats until every item has been used.
    The deck reshuffles whenever the list changes or runs out. Returns a list of `count` items."""
    unique_items = list(dict.fromkeys(items))
    if not unique_items:
        raise ValueError(f"No items available for shuffle cycle '{key}'")
    count = min(count, len(unique_items))

    signature = _items_signature(unique_items)
    state = _load_json(CYCLE_STATE_PATH, {})
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

    picks = []
    while len(picks) < count:
        index = entry.get('index', 0)
        if not isinstance(index, int) or index < 0 or index >= len(entry['order']):
            order = unique_items[:]
            random.shuffle(order)
            entry['order'] = order
            index = 0
        choice = entry['order'][index]
        entry['index'] = index + 1
        if choice not in picks:
            picks.append(choice)

    state[key] = entry
    if not _save_json(CYCLE_STATE_PATH, state):
        return random.sample(unique_items, count)
    return picks


def deal(filename, count=1):
    """Shuffle-cycle pick from a word-list file."""
    lines = _read_non_empty_lines(filename)
    if not lines:
        return []
    return shuffle_cycle_choice(f"file:{os.path.basename(filename)}", lines, count)


def read_couple_notes():
    lines = _read_non_empty_lines('couple.txt') + _read_non_empty_lines('couple.private.txt')
    return "\n".join(lines) if lines else "Victor (a man) and his wife Ericka (a woman)."


# --------------------------------------------------------------------------- #
# History (so the director doesn't repeat itself)
# --------------------------------------------------------------------------- #

def load_history():
    return _load_json(HISTORY_PATH, [])


def append_history(entry):
    history = load_history()
    history.append(entry)
    _save_json(HISTORY_PATH, history[-200:])


def format_history(history):
    if not history:
        return "(nothing yet — this is the first one)"
    rows = []
    for h in history[-HISTORY_LENGTH:]:
        texts = " / ".join(t.get('text', '') for t in h.get('text_elements', []) if isinstance(t, dict))
        rows.append(f"- {h.get('date', '?')}: \"{h.get('title', '')}\" — {h.get('concept', '')} "
                    f"[style: {h.get('style', '')}] [text: {texts}]")
    return "\n".join(rows)


# --------------------------------------------------------------------------- #
# Stage 1: the art director writes a coherent brief
# --------------------------------------------------------------------------- #

def draw_ingredients():
    return {
        'concept': (deal('concepts.txt') or ["Director's choice"])[0],
        'style': (deal('imageStyles.txt') or ["Gouache picture-book painting"])[0],
        'mood': random.choice(_read_non_empty_lines('moods.txt') or ["tender and playful"]),
        'sparks': deal('sparks.txt', 2),
        'sentiment': random.choice(_read_non_empty_lines('messages.txt') or ["I love you"]),
    }


def build_director_prompt(ingredients, now=None):
    now = now or datetime.now()
    today = now.strftime('%A, %B %-d, %Y')
    where = f" They live in {HOME_LOCATION}." if HOME_LOCATION else ""
    sparks = "; ".join(ingredients['sparks']) or "(none)"

    return f"""You are the art director and gag writer for a daily love note: a single illustrated image that Victor sends to his wife Ericka's Lovebox (a small screen she sees during her day). Today is {today}.{where}

WHO THEY ARE
{read_couple_notes()}

TODAY'S ASSIGNMENT
- Format ("you" here means Victor and Ericka): {ingredients['concept']}
- Art style (mandatory): {ingredients['style']}
- Mood: {ingredients['mood']}
- Optional sparks (use one, both, or neither — only if they make the idea better): {sparks}
- Sentiment to express (rephrase freely to fit the idea): "{ingredients['sentiment']}"

You may use Google Search to see what's special about today (odd holidays, notable anniversaries, astronomy, the season, local weather). Use it only if it produces a better idea — a date hook is a bonus, not a requirement.

HOW TO WORK
1. Brainstorm five genuinely different ideas that fit the format, style and mood.
2. Pick the one with the clearest payoff: Ericka should "get it" within three seconds and smile or laugh. Prefer specific, clever and warm over random and busy.
3. Develop it into one coherent scene.

RULES
- ONE central idea. Every element in the picture must serve it. No "object soup", no unrelated props, no mashing of themes that don't connect.
- The joke or sentiment must make literal sense when you look at the image.
- It must clearly contain a message of love for Ericka — via the text, the scene, or both.
- Text: at most 15 words total across all text, spelled exactly, in English, placed where it naturally belongs in the format (poster title, speech bubble, placard, caption…). It must be large and legible on a small screen.
- Victor and Ericka are the stars, both clearly visible with readable faces (not tiny, not turned away, not hidden behind masks or helmet visors) unless the format absolutely demands otherwise.
- Strictly illustrated/non-photographic, rendered in the assigned art style. Simple, bold composition that reads well small (landscape 4:3).
- Kind and tasteful; no real celebrities, trademarked characters, or brand logos.
- Do NOT repeat the ideas, jokes, settings, or text phrasing of these recent images:
{format_history(load_history())}

OUTPUT
Reply with ONLY a JSON object (no markdown fences) with these keys:
{{
  "title": "short internal title for this image",
  "concept": "one sentence: the idea and why it's funny or sweet",
  "date_hook": "what about today inspired it, or empty string",
  "scene": "a detailed visual description for an illustrator: composition and framing, what Victor and Ericka are each doing, their expressions and body language, outfits, key props, setting, color palette and lighting — written in the assigned art style",
  "text_elements": [{{"text": "exact words", "placement": "where and how it appears (lettering style, size)"}}]
}}"""


def _extract_json(text):
    if not text:
        raise ValueError("Empty response from director")
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE)
    start, end = cleaned.find('{'), cleaned.rfind('}')
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in director response: {text[:300]}")
    return json.loads(cleaned[start:end + 1])


def run_director(client, ingredients):
    """Ask the text model for a brief. Tries the richest config first, then simpler fallbacks."""
    prompt = build_director_prompt(ingredients)
    # Configs are built lazily (inside the try) so an older google-genai SDK that doesn't know
    # e.g. thinking_level just falls through to a simpler attempt instead of crashing the run.
    attempts = [
        lambda: dict(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=1.0,
                     thinking_config=types.ThinkingConfig(thinking_level="high")),
        lambda: dict(tools=[types.Tool(google_search=types.GoogleSearch())], temperature=1.0),
        lambda: dict(temperature=1.0),
    ]
    last_error = None
    for make_config in attempts:
        try:
            response = client.models.generate_content(
                model=DIRECTOR_MODEL, contents=prompt, config=types.GenerateContentConfig(**make_config()))
            brief = _extract_json(response.text)
            if not brief.get('scene'):
                raise ValueError("Director brief missing 'scene'")
            brief.setdefault('text_elements', [])
            return brief
        except Exception as e:
            last_error = e
            print(f"Director attempt failed ({e}); trying a simpler config...")
    raise RuntimeError(f"Art director failed: {last_error}")


def fallback_brief(ingredients):
    """Used only if the director model is unavailable, so the daily image still goes out."""
    return {
        'title': 'Fallback',
        'concept': ingredients['concept'],
        'date_hook': '',
        'scene': (f"{ingredients['concept']} The mood is {ingredients['mood']}. "
                  f"Keep it to one clear, simple idea with Victor and Ericka front and center."),
        'text_elements': [{'text': ingredients['sentiment'], 'placement': 'large, legible lettering that fits the format'}],
    }


# --------------------------------------------------------------------------- #
# Stage 2: render the brief with the reference photos
# --------------------------------------------------------------------------- #

def build_image_prompt(brief, style, ref_count):
    text_lines = "\n".join(
        f'- "{t.get("text", "")}" — {t.get("placement", "")}'
        for t in brief.get('text_elements', []) if isinstance(t, dict) and t.get('text'))

    return f"""Create an illustration in this art style: {style}.

THE PEOPLE — LIKENESS IS THE TOP PRIORITY
The {ref_count} attached photo(s) show Victor and Ericka. {read_couple_notes()}
Draw them so anyone who knows them would recognize them instantly: carry over their real face shapes, eyes, noses, smiles, hairstyles and hair colors, any glasses or facial hair, skin tones, builds and their height difference — translated into the art style the way a skilled caricaturist or portrait illustrator would. Do not swap in generic stock cartoon faces. Use the photos ONLY for their likeness: ignore the photos' clothing, poses, backgrounds, lighting and photographic look.

THE SCENE
{brief.get('scene', '')}

TEXT IN THE IMAGE (render exactly as written, spelled correctly, large and legible on a small screen; no other text)
{text_lines or '- (no text)'}

RENDERING RULES
- This is an illustration, NOT a photograph: no photorealism, no photographic skin or lighting, fully committed to the art style above.
- One clear focal point, bold readable composition in landscape 4:3, both faces clearly visible.
- No brand logos, trademarked characters, watermarks or signatures."""


def pick_reference_images(image_dir='images'):
    if not os.path.isdir(image_dir):
        raise FileNotFoundError(f"{image_dir} directory not found")
    files = sorted(f for f in os.listdir(image_dir)
                   if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')))
    if not files:
        raise FileNotFoundError("No images found in images directory")
    chosen = shuffle_cycle_choice('images_dir:images', files, MAX_REFERENCE_IMAGES)
    return [os.path.join(image_dir, f) for f in chosen]


def render_image(client, image_prompt, ref_paths, out_path):
    refs = [Image.open(p) for p in ref_paths]
    last_error = None
    for model in IMAGE_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[image_prompt, *refs],
                config=types.GenerateContentConfig(
                    response_modalities=['TEXT', 'IMAGE'],
                    image_config=types.ImageConfig(aspect_ratio="4:3", image_size="2K"),
                ),
            )
            text_out = ""
            saved = False
            for part in (response.parts or []):
                if part.inline_data is not None:
                    part.as_image().save(out_path)
                    saved = True
                elif part.text:
                    text_out += part.text + "\n"
            if saved:
                return model, text_out
            last_error = f"{model} returned no image. {text_out.strip()}"
        except Exception as e:
            last_error = f"{model}: {e}"
        print(f"Image attempt failed ({last_error})")
    raise RuntimeError(last_error)


def generate_image(out_path=OUTPUT_IMAGE, dry_run=False):
    """Returns (details_dict, error)."""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        ingredients = draw_ingredients()
        print("Ingredients:", json.dumps(ingredients, indent=2, ensure_ascii=False))

        try:
            brief = run_director(client, ingredients)
        except Exception as e:
            print(f"{e}\nUsing fallback brief.")
            brief = fallback_brief(ingredients)

        ref_paths = pick_reference_images()
        image_prompt = build_image_prompt(brief, ingredients['style'], len(ref_paths))
        print("\n--- BRIEF ---\n" + json.dumps(brief, indent=2, ensure_ascii=False))
        print("\n--- IMAGE PROMPT ---\n" + image_prompt)
        print(f"\nReference images: {ref_paths}")

        details = {'ingredients': ingredients, 'brief': brief, 'image_prompt': image_prompt,
                   'references': ref_paths, 'model': None, 'model_text': ''}
        if dry_run:
            return details, None

        model, model_text = render_image(client, image_prompt, ref_paths, out_path)
        details['model'], details['model_text'] = model, model_text
        return details, None
    except Exception as e:
        return None, f"Error generating image: {e}"


def record_history(details):
    brief = details['brief']
    append_history({
        'date': datetime.now().strftime('%Y-%m-%d'),
        'title': brief.get('title', ''),
        'concept': brief.get('concept', ''),
        'style': details['ingredients']['style'],
        'text_elements': brief.get('text_elements', []),
    })


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #

def send_to_lovebox(recipient_id):
    if not os.path.exists(OUTPUT_IMAGE):
        return False, "Image not found. Aborting sending to Lovebox."

    with open(OUTPUT_IMAGE, 'rb') as f:
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


def send_email(subject, body, attach_image=False):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    if attach_image and os.path.exists(OUTPUT_IMAGE):
        with open(OUTPUT_IMAGE, 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment; filename="daily_image.png"')
            msg.attach(part)

    server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
    server.starttls()
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    server.sendmail(EMAIL_ADDRESS, EMAIL_ADDRESS, msg.as_string())
    server.quit()
    print(f'{subject} email sent!')


def cleanup_files():
    if os.path.exists(OUTPUT_IMAGE):
        os.remove(OUTPUT_IMAGE)


def run_process(recipient_id):
    details, error = generate_image()
    if error:
        print(error)
        time.sleep(RETRY_DELAY)
        details, error = generate_image()
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

    record_history(details)
    brief = details['brief']
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    texts = "\n".join(f'  "{t.get("text", "")}"' for t in brief.get('text_elements', []) if isinstance(t, dict))
    body = (f"Hi {NAME_OF_SENDER} - Your Lovebox image was sent to {LOVEBOX_RECIPIENT_NAME} on {current_time}!\n\n"
            f"Idea: {brief.get('title', '')} — {brief.get('concept', '')}\n"
            f"Date hook: {brief.get('date_hook') or '(none)'}\n"
            f"Style: {details['ingredients']['style']}\n"
            f"Mood: {details['ingredients']['mood']}\n"
            f"Text:\n{texts}\n\n"
            f"Image model: {details['model']}\n\n"
            f"Full image prompt:\n{details['image_prompt']}")
    if details.get('model_text'):
        body += f"\n\nModel Output:\n{details['model_text']}"

    send_email("Lovebox image sent!", body, attach_image=True)
    cleanup_files()


def run_preview(count):
    """Generate images locally (previews/) without sending anything — for tuning the lists."""
    os.makedirs('previews', exist_ok=True)
    for i in range(count):
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        out = os.path.join('previews', f'{stamp}-{i + 1}.png')
        details, error = generate_image(out_path=out)
        if error:
            print(error)
            continue
        with open(out.replace('.png', '.json'), 'w', encoding='utf-8') as f:
            json.dump(details, f, indent=2, ensure_ascii=False)
        print(f"\nSaved {out}\n" + "=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Send AI generated image to Lovebox.')
    parser.add_argument('--id2', action='store_true', help='Use the second recipient ID')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only run the art director and print the brief + image prompt (no image, nothing sent)')
    parser.add_argument('--preview', type=int, metavar='N',
                        help='Generate N images into previews/ without sending or emailing')
    args = parser.parse_args()

    if args.dry_run:
        generate_image(dry_run=True)
    elif args.preview:
        run_preview(args.preview)
    else:
        recipient_id = LOVEBOX_RECIPIENT_ID2 if args.id2 else LOVEBOX_RECIPIENT_ID
        if not recipient_id:
            print("Error: Recipient ID not found in environment variables.")
        else:
            run_process(recipient_id)

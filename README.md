# Auto AI Image To Lovebox
Automatically send daily generated images from Google's Gemini to your loved one's Lovebox using APIs

Welcome to **Auto AI Image to Lovebox** — a semi-automated way to express love for your significant other without lifting a finger (well, almost). This script generates amazing AI-created images and sends them straight to your partner's Lovebox. Because nothing says "romance" like delegating affection to artificial intelligence.

## Features

- Generates tailored images for your loved one based on custom randomized prompts.
- Sends images directly to your Lovebox.
- Emails you a confirmation with the image and prompt details.
- Retries on failure and keeps you in the loop if something breaks (because love is about communication).

> **Important:** Check [Gemini API pricing](https://ai.google.dev/pricing) for current rates. Test your prompts thoroughly before letting the AI run wild with your wallet!

---

## Setup Guide

### 1. Prerequisites

- A **Linux** machine (because Windows doesn't deserve this kind of love).
- A **Lovebox** account with API access.
- A **Google Cloud** project with Gemini API enabled.
- A **Google** account (for sending confirmation emails).

### 2. Install Required Packages

On newer Linux distributions (like Ubuntu 24.04+), you should use a virtual environment to avoid conflicts with system packages.

1.  **Create a virtual environment:**
    ```bash
    python3 -m venv venv
    ```

2.  **Activate the virtual environment:**
    ```bash
    source venv/bin/activate
    ```

3.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

    *Note: If you ever need to run the script manually, remember to activate the environment first!*

### 3. Get Your API Keys

#### Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/).
2. Create an API key.

#### Google App Password

1. Enable [2FA on your Google account](https://support.google.com/accounts/answer/185839?hl=en&ref_topic=2954345&sjid=12054959942831181503-NC).
2. Go to [Google App Passwords](https://myaccount.google.com/apppasswords).
3. Generate a password for the app.

#### Lovebox API Key & Recipient ID

##### Create a Lovebox account.
The easiest way to do this is to [download the Lovebox app](https://en.lovebox.love/pages/app). Make sure to set up your Lovebox in the app and send at least one message.

##### Get your API key / token and the ID of the Lovebox or phone widget you want to send to.
First, get the token with the following command. Replace the e-mail and password with your e-mail and password associated with your Lovebox account.

```bash
curl --location --request POST 'https://app-api.loveboxlove.com/v1/auth/loginWithPassword' \
--header 'accept: application/json' \
--header 'content-type: application/json' \
--header 'host: app-api.loveboxlove.com' \
--data-raw '{
    "email": "my@email.com",
    "password": "mySecret"
}'
```

You will get a response that looks like this:
```json
{
  "_id": "42c61f261f3d9d0016350b7f",
  "firstName": "FirstName",
  "email": "my@email.com",
  "token": "REALLY_LONG_ALPHANUMERIC_THING"
}
```
The token is your API key for Lovebox.

##### Find your sweetheart's **Recipient ID** (probably your partner's box, but double-check unless you want to surprise a stranger).
Use the following command, replacing the part after Bearer with your token from the last step.
```bash
curl --location --request POST 'https://app-api.loveboxlove.com/v1/graphql' \
--header 'authorization: Bearer YOUR_REALLY_LONG_TOKEN' \
--header 'content-type: application/json' \
--data-raw '{
    "operationName": "me",
    "variables": {},
    "query": "query me {\n  me {\n    _id\n    firstName\n    email\n    boxes {\n      _id\n      nickname\n      isAdmin\n      __typename\n    }\n    __typename\n  }\n}\n"
}'
```

You should get a response that looks like this:
```json
{
{"data":{"me":{"_id":"hexnumber","firstName":"Victor","email":"email","boxes":[{"_id":"SomeHexNumber","nickname":"Ericka","isAdmin":false,"__typename":"BoxSettings"},{"_id":"SomeHexNumber","nickname":"Your Widget","isAdmin":true,"__typename":"BoxSettings"},{"_id":"SomeHexNumber","nickname":"Ericka","isAdmin":false,"__typename":"BoxSettings"}],"__typename":"User"}}}
```
Look for the hexadecimal numbers associated with the _id variables. One of those should be the box you're looking for!

### 4. Download the files here to their own directory and modify the `.env` File

Use the API keys / tokens and ID from the last steps to modify the .env file.

### 5. Customize the Prompts

Each day runs in two stages:

1. **Art director (text model).** The script deals a random *concept format* (`concepts.txt`), *art style* (`imageStyles.txt`), *mood* (`moods.txt`), two optional *sparks* (`sparks.txt`) and a *sentiment* (`messages.txt`). A Gemini text model (with Google Search, for date hooks) brainstorms several ideas from those ingredients, picks the clearest one, and writes a single coherent brief: scene, composition and the exact on-image text. It also sees the last 30 ideas (`.history.json`) so it doesn't repeat itself.
2. **Illustrator (image model).** The brief, the style, and up to 3 reference photos from `images/` go to the image model with strict likeness instructions (stylized but recognizable, never photorealistic).

Concepts, styles, sparks and reference photos are dealt like a shuffled deck: nothing repeats until the whole list has been used.

Files you'll want to edit (lines starting with `#` are ignored):

- `couple.txt` — **the most important file for likeness.** Describe each person concretely (hair, glasses, facial hair, build, height difference) and add inside jokes, pets, hobbies and places. Put private details in `couple.private.txt` (git-ignored); it's read the same way.
- `concepts.txt` — formats like "movie poster", "three-panel comic", "museum placard", "tiny people in a giant kitchen".
- `imageStyles.txt` — illustrated styles only; photographic styles tend to produce strangers.
- `moods.txt`, `sparks.txt`, `messages.txt`.
- `images/` — add several clear, well-lit photos where your faces are visible (solo shots work too). More variety in the references = better likeness.

Optional `.env` settings: `DIRECTOR_MODEL` (default `gemini-3.8-flash`), `IMAGE_MODELS` (comma-separated, tried in order; default `gemini-3-pro-image,gemini-3-pro-image-preview`), `HOME_LOCATION` (e.g. `Minneapolis, Minnesota`, for seasonal/weather jokes), `MAX_REFERENCE_IMAGES` (default 3), `HISTORY_LENGTH` (default 30).

Trying it out without sending anything:

```bash
python3 auto-ai-to-lovebox.py --dry-run      # just print today's brief and image prompt
python3 auto-ai-to-lovebox.py --preview 5    # render 5 images into previews/ (no Lovebox, no email)
```

### 6. Set Up as a Daily Service

Want to automate this to run daily? Here's how:

1. **Create a Service File:**

```bash
sudo nano /etc/systemd/system/lovebox.service
```

Add the following:

```
[Unit]
Description=Auto AI to Lovebox Service

[Service]
# Set the user to ensure correct permissions for your home directory and venv
User=yourusername
Group=yourusername
# Use a shell command to explicitly activate the virtual environment before running the script
ExecStart=/bin/bash -c "source /path/to/auto-ai-image-to-lovebox/venv/bin/activate && /path/to/auto-ai-image-to-lovebox/venv/bin/python3 /path/to/auto-ai-image-to-lovebox/auto-ai-to-lovebox.py"
WorkingDirectory=/path/to/auto-ai-image-to-lovebox/
StandardOutput=journal

[Install]
WantedBy=multi-user.target
```

2. **Create a Timer:**

```bash
sudo nano /etc/systemd/system/lovebox.timer
```

Add:

```
[Unit]
Description=Run Lovebox Script Daily

[Timer]
# Set the desired time (e.g., 10:00 AM)
OnCalendar=*-*-* 10:00:00
# Force the timer to respect the system's local time zone (e.g., America/Chicago)
Timezone=America/Chicago 
Persistent=true

[Install]
WantedBy=timers.target
```

3. **Enable and Start:**

```bash
sudo systemctl enable lovebox.timer
sudo systemctl start lovebox.timer
```

---

### Important Notes

- **Testing:** Make sure to thoroughly test your prompts. Weird things can happen when AI interprets your love.
- **Cost Awareness:** Check Gemini pricing. Plan (and love) responsibly.
- **Failures Happen:** The script retries once if something fails and emails you about it if it still doesn't work. Even AI can't always get things right on the first try—just like relationships.

---

### Contributing

Feel free to fork this repo and add more features, like sending randomized poetry or automating "I’m sorry" messages (kidding... mostly).

---

### License

This project is licensed under the MIT License. Use it, modify it, and remember: even though AI can automate affection, **it’s the thought that counts**. 

---




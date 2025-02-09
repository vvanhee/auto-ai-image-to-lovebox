# auto-ai-image-to-lovebox
Automatically send daily generated images from OpenAI's DALL-E to your loved one's Lovebox using APIs

Welcome to **Auto AI Image to Lovebox** — a semi-automated way to express love for your significant other without lifting a finger (well, almost). This script generates adorable AI-created images and sends them straight to your partner's Lovebox. Because nothing says "romance" like delegating affection to artificial intelligence.

## Features

- Generates cute cartoon images based on random prompts.
- Sends images directly to your Lovebox.
- Emails you a confirmation with the image and prompt details.
- Retries on failure and keeps you in the loop if something breaks (because love is about communication).

> **Important:** As of this script's publication, **each image costs about \$0.08** through OpenAI's API. This can add up faster than you think. Test your prompts thoroughly before letting the AI run wild with your wallet!

---

## Setup Guide

### 1. Prerequisites

- A **Linux** machine (because Windows doesn't deserve this kind of love).
- A **Lovebox** account with API access.
- An **OpenAI** account with credits.
- A **Google** account (for sending confirmation emails).

### 2. Install Required Packages

Make sure you have Python installed, then run:

```bash
pip install requests python-dotenv
```

### 3. Get Your API Keys

#### OpenAI API Key

1. Create an account at [OpenAI](https://openai.com/).
2. Add some credits [on OpenAI's billing page](https://platform.openai.com/settings/organization/billing/overview) (because love—and AI—isn't free).
3. Create an API key from the [OpenAI API Keys](https://platform.openai.com/settings/organization/api-keys) page.

#### Google App Password

1. Enable [2FA on your Google account](https://support.google.com/accounts/answer/185839?hl=en&ref_topic=2954345&sjid=12054959942831181503-NC).
2. Go to [Google App Passwords](https://myaccount.google.com/apppasswords).
3. Generate a password for the app.

#### Lovebox API Key & Recipient ID

1. Create a Lovebox account. The easiest way to do this is to [download the Lovebox app](https://en.lovebox.love/pages/app). Make sure to set up your Lovebox in the app and send at least one message.
2. Get your API key / token and the ID of the Lovebox or phone widget you want to send to.
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
3. Find your sweetheart's **Recipient ID** (probably your partner's box, but double-check unless you want to surprise a stranger).
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

### 4. Create Your `.env` File

In the project directory, create a `.env` file and add:

```
NAME_OF_SENDER = 'your_name_just_for_personalization'
EMAIL_ADDRESS='your_email@gmail.com'
EMAIL_PASSWORD='your_google_app_password'
LOVEBOX_API_KEY='your_lovebox_api_key'
LOVEBOX_RECIPIENT_NAME = 'recipient_name_just_for_personalization'
LOVEBOX_RECIPIENT_ID='your_lovebox_recipient_id'
OPENAI_API_KEY='your_openai_api_key'
```

**Important:** Add `.env` to your `.gitignore` file to avoid accidentally sharing your secrets with the world, if for some reason you're planning to post this to Github.

### 5. Customize Your Prompts

The current script generates images that are supposed to look like **me and my wife**. Unless you want daily pictures of two strangers (which, hey, no judgment), you'll want to tweak the prompt in the `generate_prompt()` function in `auto-ai-to-lovebox.py`.

You can also modify the following text files to create more personalized prompts. The script will take a random line from each to add to the prompt:

- `activities.txt`
- `settings.txt`
- `messages.txt`
- `textStyles.txt`

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
ExecStart=/usr/bin/python3 /path/to/auto-ai-to-lovebox.py
WorkingDirectory=/path/to/
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
OnCalendar=*-*-* 08:00:00
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

## Important Notes

- **Testing:** Make sure to thoroughly test your prompts. Weird things can happen when AI interprets your love.
- **Cost Awareness:** With the current OpenAI pricing, each image costs \$0.08. Daily love could cost you \~\$2.50/month. Plan (and love) responsibly.
- **Failures Happen:** The script retries once if something fails and emails you about it if it still doesn't work. Even AI can't always get things right on the first try—just like relationships.

---

## Contributing

Feel free to fork this repo and add more features, like sending randomized poetry or automating "I’m sorry" messages (kidding... mostly).

---

## License

This project is licensed under the MIT License. Use it, modify it, and remember: even though AI can automate affection, **it’s the thought that counts**. 

---




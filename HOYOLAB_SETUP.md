# HoYoLab Banner Data Integration

This bot can automatically fetch banner data from HoYoLab using your account v2 cookies, eliminating the need for manual `/bupdate` commands.

## Setup Instructions

### 1. Get Your HoYoLab v2 Cookies

You need to extract **v2 cookies** from your HoYoLab account. These are the newer authentication cookies.

#### Option A: Using Browser DevTools (Chrome/Firefox/Edge)

1. Go to https://hoyolab.com/ and log in to your account
2. Open Developer Tools (Press `F12` or `Ctrl+Shift+I`)
3. Go to the **Application** or **Storage** tab
4. Look for **Cookies** in the left sidebar
5. Click on the HoYoLab domain (hoyolab.com)
6. Look for these **v2 cookies** (these are required):
   - `cookie_token_v2` ⭐ (required)
   - `account_id_v2` ⭐ (required)

7. Optional v2 cookies that improve reliability:
   - `ltoken_v2`
   - `ltuid_v2`
   - `mi18nLanguage`

8. The simplest way to get the complete cookie string:
   - Open **Console** tab
   - Paste this command:
     ```javascript
     document.cookie
     ```
   - Copy the entire output - it contains all your cookies

#### Option B: Using Cookie Editor Extension

1. Install a cookie editor extension for your browser (like "Cookie Editor" or "EditThisCookie")
2. Go to https://hoyolab.com and log in
3. Use the extension to view and export cookies
4. Copy all cookies as a string
5. Make sure it includes `cookie_token_v2` and `account_id_v2`

### 2. Add Cookies to Environment

Add **only the v2 cookies** to your `.env` file:

```env
HOYOLAB_COOKIES="cookie_token_v2=YOUR_TOKEN_HERE; account_id_v2=YOUR_ACCOUNT_ID"
```

**Minimal setup (required cookies only)**:
```env
HOYOLAB_COOKIES="cookie_token_v2=abc123xyz; account_id_v2=987654321"
```

**Full setup (recommended for reliability)**:
```env
HOYOLAB_COOKIES="cookie_token_v2=abc123xyz; account_id_v2=987654321; ltoken_v2=xyz789abc; ltuid_v2=123456789"
```

### 3. Install Dependencies

Make sure `requests` library is installed:

```bash
pip install -r requirements.txt
```

The requirements.txt has been updated to include `requests`.

## Usage

### Automatic Sync Command

Once your v2 cookies are configured, use the `/bsync` command in the bot:

```
/bsync
```

The bot will:
- Fetch current and next banner data from HoYoLab
- Extract character names
- Extract banner timing information
- Automatically update the internal banner database
- Send you a confirmation with the synced characters

## Troubleshooting

### "Failed to sync banner data from HoYoLab"

1. **Missing v2 cookies**: Make sure you have these exact cookies:
   - `cookie_token_v2=...`
   - `account_id_v2=...`
   
   Check that you copied **v2 cookies**, not old v1 cookies (which look like `cookie_token=...` without the `_v2`)

2. **Cookie expiration**: HoYoLab cookies expire after some time. If sync fails:
   - Log in to HoYoLab again at https://hoyolab.com
   - Extract fresh v2 cookies using the steps above
   - Update your `.env` file with new cookies

3. **Cookie format**: Make sure v2 cookies follow the exact format:
   ```
   cookie_token_v2=value1; account_id_v2=value2; ltoken_v2=value3
   ```
   - Use semicolons `;` to separate cookies
   - Use equals `=` to separate names and values
   - Include spaces after semicolons (optional but recommended)
   - Only include cookies that exist (don't add empty values)

4. **Check logs**: Run the bot and look for detailed error messages about the HoYoLab fetch.

### "Missing required v2 cookies"

- You need to have both `cookie_token_v2` AND `account_id_v2` in your `HOYOLAB_COOKIES`
- If you only see `cookie_token` and `account_id` (without `_v2`), those are old v1 cookies
- Log in again and extract the v2 versions

### "No calendar data from HoYoLab"

- The HoYoLab calendar API might be temporarily unavailable
- Your v2 cookies might have expired - try re-extracting them
- Try logging into HoYoLab directly to verify it's working
- Wait a moment and try `/bsync` again

## Security Notes

⚠️ **Important**: Your HoYoLab v2 cookies contain authentication tokens. 

- **Never** share your `.env` file or cookies publicly
- **Never** commit `.env` to version control (it should be in `.gitignore`)
- v2 Cookies should be treated like passwords
- If you suspect your cookies have been compromised, change your HoYoLab password
- Tokens may expire periodically (usually after several months), requiring you to refresh them
- Only share your `.env` file with people you completely trust

## How It Works

The `/bsync` command:
1. Uses your v2 HoYoLab cookies to authenticate with the calendar API
2. Fetches the official Genshin Impact banner calendar from HoYoLab
3. Parses the response to find current and next character banners
4. Extracts timing information for all regions (Asia, EU, NA)
5. Updates the internal `banner_data.json` file
6. Character information is now available via `/next` command

## API Details

- **Endpoint**: `https://hoyolab.com/genshin/h5/traveler_contain/calendar`
- **Method**: GET with Cookie-based v2 authentication
- **Response**: JSON with calendar events
- **Required Cookies**: `cookie_token_v2`, `account_id_v2`

## FAQ

**Q: Why does my sync fail immediately after logging in?**
A: Sometimes it takes a few seconds for HoYoLab to fully update cookies. Try again after 10-30 seconds.

**Q: Can I use v1 cookies instead of v2?**
A: No, the bot requires v2 cookies. If you only see v1 cookies, log out and log back in to generate v2 cookies.

**Q: Do I need all the optional v2 cookies?**
A: No, only `cookie_token_v2` and `account_id_v2` are required. The others make it more reliable.

For more information about the HoYoLab API, visit https://hoyolab.com/

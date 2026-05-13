import requests
import re
import time

SESSION = requests.Session()
SESSION.proxies = {
    'http': 'socks5h://127.0.0.1:9050',
    'https': 'socks5h://127.0.0.1:9050'
}
SESSION.headers.update({
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

USERNAME = "Grouchy_Month2324"
PASSWORD = "anashalima123"

print("=== Step 1: Login ===")
# Get CSRF token from old.reddit.com
r = SESSION.get("https://old.reddit.com/")
print(f"GET old.reddit.com: {r.status_code}")

csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
if csrf_match:
    csrf = csrf_match.group(1)
    print(f"CSRF token found: {csrf[:20]}...")
else:
    csrf = ""
    print("No CSRF token found")

# Login
login_data = {
    "op": "login-main",
    "user": USERNAME,
    "passwd": PASSWORD,
    "csrf_token": csrf
}
r2 = SESSION.post("https://old.reddit.com/api/login", data=login_data)
print(f"Login response: {r2.status_code}")
if 'Grouchy_Month2324' in r2.text or 'logout' in r2.text.lower():
    print("LOGIN SUCCESSFUL!")
else:
    print("LOGIN MAY HAVE FAILED")
    # Check for error
    err_match = re.search(r'class="error">([^<]+)', r2.text)
    if err_match:
        print(f"Error: {err_match.group(1)}")

# Verify by visiting user page
r3 = SESSION.get("https://old.reddit.com/user/Grouchy_Month2324/")
print(f"User page: {r3.status_code}")
if 'logout' in r3.text.lower():
    print("VERIFIED: Logged in!")
else:
    print("NOT logged in based on user page")
    # Save debug
    with open('/tmp/reddit_login_debug.html', 'w') as f:
        f.write(r3.text[:5000])
    print("Saved debug HTML")

print("\n=== Step 2: Get CSRF for posting ===")
# Visit a subreddit to get fresh CSRF
r4 = SESSION.get("https://old.reddit.com/r/APIs/")
print(f"GET r/APIs: {r4.status_code}")

csrf_match2 = re.search(r'name="csrf_token"\s+value="([^"]+)"', r4.text)
if csrf_match2:
    csrf2 = csrf_match2.group(1)
    print(f"Post CSRF: {csrf2[:20]}...")
else:
    csrf2 = ""
    print("No post CSRF found - checking if logged in")
    # Check debug
    if 'login' in r4.text.lower()[:2000]:
        print("Redirected to login page")
    else:
        print("Might be logged in but CSRF hidden")


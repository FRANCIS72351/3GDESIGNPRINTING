import requests

# Test login via HTTP POST
url = 'http://localhost:5001/login'
data = {
    'username': 'admin',
    'password': 'Press2026!'
}

print("Testing login via HTTP POST...")
print(f"URL: {url}")
print(f"Data: {data}")

try:
    response = requests.post(url, data=data, allow_redirects=False)  # Don't follow redirects to see the response
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")

    if response.status_code == 302:  # Redirect (expected for successful login)
        location = response.headers.get('Location', '')
        print(f"✓ Login successful! Redirecting to: {location}")
        if 'setup-2fa' in location or 'verify-2fa' in location:
            print("✓ 2FA verification required (expected)")
        else:
            print("? Unexpected redirect location")
    elif response.status_code == 200:
        print("✗ Login failed - returned to login page")
        # Check if there's an error message in the response
        if 'Invalid username or password' in response.text:
            print("✗ Error message: Invalid username or password")
        else:
            print("? No error message found in response")
    else:
        print(f"✗ Unexpected status code: {response.status_code}")

except Exception as e:
    print(f"✗ Request failed: {e}")
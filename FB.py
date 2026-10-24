import requests
import random
import time
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from faker import Faker
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import box

console = Console()
fake = Faker('en_US')

class FBCreator:
    def __init__(self, proxy=None):
        self.session = requests.Session()
        
        # রিয়েল ব্রাউজারের মতো ইউজার-এজেন্ট সেট করা
        try:
            ua = UserAgent().random
        except:
            ua = "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
            
        self.session.headers.update({
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })

        if proxy:
            parts = proxy.split(":")
            if len(parts) == 4:
                proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
            elif len(parts) == 2:
                proxy_url = f"http://{parts[0]}:{parts[1]}"
            else:
                proxy_url = f"http://{proxy}"
            self.session.proxies = {"http": proxy_url, "https": proxy_url}

    def create_account(self, contact, identity):
        try:
            # ১. ফেসবুকের মোবাইল সাইট থেকে ফর্ম টোকেন আনা
            console.print("[dim]1. Fetching Facebook Mobile Page...[/]")
            r = self.session.get("https://mbasic.facebook.com/reg/", timeout=30)
            
            soup = BeautifulSoup(r.text, "html.parser")
            form = soup.find("form")
            if not form:
                return False, "Registration form not found (Facebook blocked the request)"

            # ফর্মের লুকানো (hidden) ইনপুটগুলো খোঁজা
            hidden_inputs = {}
            for inp in form.find_all("input"):
                if inp.get("type") == "hidden":
                    hidden_inputs[inp.get("name")] = inp.get("value", "")

            # ২. ডেটা প্রস্তুত করা
            data = {
                **hidden_inputs,
                "firstname": identity["first_name"],
                "lastname": identity["last_name"],
                "reg_email__": contact,
                "reg_passwd__": identity["password"],
                "birthday_day": str(identity["day"]),
                "birthday_month": str(identity["month"]),
                "birthday_year": str(identity["year"]),
                "sex": identity["gender"],
                "submit": "Sign Up"
            }
            
            if "@" in contact:
                data["reg_email_confirmation__"] = contact

            # ৩. ফর্ম সাবমিট করা
            console.print("[dim]2. Submitting Form...[/]")
            time.sleep(2) # মানুষ যেভাবে করে
            post_req = self.session.post("https://mbasic.facebook.com/reg/", data=data, timeout=30, allow_redirects=True)
            
            text = post_req.text.lower()
            url = post_req.url.lower()

            # ৪. রেসপন্স চেক করা
            if "checkpoint" in url or "confirm" in text or "enter the code" in text or "codel" in text:
                return True, "OTP_REQUIRED"
            elif "disabled" in text or "blocked" in text or "suspended" in text:
                return False, "Blocked by Facebook (Use VPN/Proxy)"
            elif "home" in url or "news feed" in text:
                return True, "SUCCESS"
            else:
                return False, "Unknown Response (Facebook might have shown a CAPTCHA)"

        except requests.exceptions.ProxyError:
            return False, "Proxy Connection Failed"
        except Exception as e:
            return False, f"Error: {str(e)[:50]}"

    def submit_otp(self, otp):
        try:
            # OTP সাবমিট করার চেষ্টা
            for endpoint in ["/confirmemail.php", "/checkpoint/", "/two_step_verification/"]:
                r = self.session.post(f"https://mbasic.facebook.com{endpoint}", data={"code": otp, "approvals_code": otp}, timeout=30, allow_redirects=True)
                if "home" in r.url or "welcome" in r.text.lower():
                    return True, "Account Verified!"
            return False, "OTP Failed"
        except:
            return False, "OTP Submission Error"

def generate_identity():
    return {
        "first_name": fake.first_name(),
        "last_name": fake.last_name(),
        "password": fake.password(length=12, special_chars=True, digits=True, upper_case=True, lower_case=True),
        "day": str(random.randint(1, 28)),
        "month": str(random.randint(1, 12)),
        "year": str(random.randint(1990, 2004)),
        "gender": random.choice(["1", "2"]) # 1=Female, 2=Male
    }

def main():
    console.clear()
    console.print(Panel.fit("[bold cyan]FACEBOOK API AUTO CREATOR[/]\n[dim]Requests + BeautifulSoup Version[/]", border_style="cyan"))

    contact = Prompt.ask("\n[bold yellow]Enter Email or Phone Number[/]")
    if "@" not in contact:
        contact = contact.replace(" ", "").replace("-", "")
        if contact.startswith("+88"): contact = contact[3:]
        if contact.startswith("0"): contact = "88" + contact
            
    proxy = Prompt.ask("[bold yellow]Enter Proxy (host:port:user:pass) or blank[/]", default="")

    identity = generate_identity()
    
    t = Table(box=box.ROUNDED)
    t.add_column("Field", style="cyan")
    t.add_column("Value", style="green")
    t.add_row("Name", f"{identity['first_name']} {identity['last_name']}")
    t.add_row("Password", identity['password'])
    console.print(t)

    creator = FBCreator(proxy=proxy)
    success, msg = creator.create_account(contact, identity)

    if success and msg == "OTP_REQUIRED":
        console.print("\n[bold cyan]⚠ Facebook OTP চাচ্ছে![/]")
        otp = Prompt.ask("[bold yellow]আপনার Email/SMS থেকে OTP দিন[/]")
        if otp:
            ok, otp_msg = creator.submit_otp(otp)
            if ok:
                console.print(f"[bold green]✅ Account Created & Verified![/]")
                console.print(f"Email: {contact} | Pass: {identity['password']}")
            else:
                console.print(f"[bold red]❌ {otp_msg}[/]")
                
    elif success and msg == "SUCCESS":
        console.print("[bold green]✅ Account Created Successfully without OTP![/]")
        console.print(f"Email: {contact} | Pass: {identity['password']}")
        
    else:
        console.print(f"\n[bold red]❌ Failed: {msg}[/]")
        console.print("[dim]Tip: Try using a VPN (1.1.1.1) or a Residential Proxy for better results.[/]")

    Prompt.ask("\n[dim]Press Enter to exit...[/]", default="")

if __name__ == "__main__":
    main()

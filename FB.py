import os
import time
import random
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich import box
from faker import Faker
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

console = Console()
# ফেসবুকের জন্য ইংরেজি নাম জরুরি, তাই en_US লোকাল ব্যবহার করা হলো
fake = Faker('en_US') 
ACCOUNTS_FILE = Path("accounts.txt")

def get_chromium_path():
    # Termux-এর জন্য সিস্টেম ক্রোমিয়ামের পাথ
    paths = [
        "/data/data/com.termux/files/usr/bin/chromium",
        "/data/data/com.termux/files/usr/bin/chromium-browser"
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def generate_identity():
    first = fake.first_name()
    last = fake.last_name()
    pwd = fake.password(length=12, special_chars=True, digits=True, upper_case=True, lower_case=True)
    return {
        "first_name": first,
        "last_name": last,
        "password": pwd,
        "day": str(random.randint(1, 28)),
        "month": str(random.randint(1, 12)),
        "year": str(random.randint(1990, 2004)),
        "gender": random.choice(["1", "2"]) # 1=Female, 2=Male
    }

def save_account(data):
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"Contact: {data['contact']} | Pass: {data['password']} | Name: {data['first_name']} {data['last_name']} | Status: {data['status']}\n")

def main():
    console.clear()
    console.print(Panel.fit("[bold cyan]FACEBOOK AUTO REGISTRATION[/]\n[dim]Playwright + Termux Version[/]", border_style="cyan"))

    contact = Prompt.ask("\n[bold yellow]Enter Email or Phone Number[/]")
    
    # নাম্বার দিলে ডাবল 0 বা + চিহ্ন ঠিক করার লজিক
    if "@" not in contact:
        contact = contact.replace(" ", "").replace("-", "")
        if contact.startswith("+88"):
            contact = contact[3:]
        if contact.startswith("0"):
            contact = "88" + contact # ফেসবুকের জন্য 88 যোগ করা
            
    proxy = Prompt.ask("[bold yellow]Enter Proxy (host:port:user:pass) or leave blank[/]", default="")

    console.print("\n[dim]Generating English Identity...[/]")
    identity = generate_identity()
    
    t = Table(box=box.ROUNDED)
    t.add_column("Field", style="cyan")
    t.add_column("Value", style="green")
    t.add_row("Name", f"{identity['first_name']} {identity['last_name']}")
    t.add_row("Password", identity['password'])
    console.print(t)

    console.print("\n[bold yellow]▶ Launching Browser...[/]")
    
    with sync_playwright() as p:
        launch_args = {
            "headless": True,
            "args": [
                "--no-sandbox", 
                "--disable-dev-shm-usage", 
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu"
            ]
        }
        
        chromium_path = get_chromium_path()
        if chromium_path:
            launch_args["executable_path"] = chromium_path
            console.print(f"[dim]Using Termux Chromium: {chromium_path}[/]")

        if proxy:
            parts = proxy.split(":")
            if len(parts) == 4:
                launch_args["proxy"] = {
                    "server": f"http://{parts[0]}:{parts[1]}",
                    "username": parts[2],
                    "password": parts[3]
                }
            elif len(parts) == 2:
                launch_args["proxy"] = {"server": f"http://{parts[0]}:{parts[1]}"}

        try:
            browser = p.chromium.launch(**launch_args)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()

            # ফেসবুকের অটোমেশন ডিটেকশন বাইপাস
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            console.print("[dim]Loading Facebook Registration Page...[/]")
            page.goto("https://www.facebook.com/reg/", timeout=90000, wait_until="domcontentloaded")
            
            # ফর্ম লোড হওয়া পর্যন্ত অপেক্ষা করা
            console.print("[dim]Waiting for form to load...[/]")
            page.wait_for_selector('input[name="firstname"]', timeout=30000)

            console.print("[dim]Filling form...[/]")
            page.fill('input[name="firstname"]', identity["first_name"], timeout=10000)
            page.fill('input[name="lastname"]', identity["last_name"], timeout=10000)
            
            # ইমেইল বা ফোন নাম্বার
            page.fill('input[name="reg_email__"]', contact, timeout=10000)
            if "@" in contact:
                # ইমেইল দিলে কনফার্ম ইমেইল ফিল্ড আসে
                try:
                    page.wait_for_selector('input[name="reg_email_confirmation__"]', timeout=3000)
                    page.fill('input[name="reg_email_confirmation__"]', contact)
                except:
                    pass

            page.fill('input[name="reg_passwd__"]', identity["password"], timeout=10000)
            
            page.select_option("#day", identity["day"])
            page.select_option("#month", identity["month"])
            page.select_option("#year", identity["year"])
            
            page.click(f'input[name="sex"][value="{identity["gender"]}"]')
            time.sleep(1)
            
            console.print("[dim]Submitting form...[/]")
            page.click('button[name="websubmit"]')
            
            # সাবমিট করার পর ফেসবুক রেসপন্স দেওয়া পর্যন্ত অপেক্ষা
            console.print("[dim]Waiting for Facebook response...[/]")
            time.sleep(8) 

            # রেসপন্স চেক করা
            page_url = page.url
            content = page.content().lower()
            
            # ১. OTP বা কোড চাইলে
            if "checkpoint" in page_url or 'name="code"' in content or "confirm your email" in content:
                console.print("\n[bold cyan]⚠ Facebook OTP / Email Verification চাচ্ছে![/]")
                otp = Prompt.ask("[bold yellow]আপনার Email/SMS থেকে OTP দিন[/]")
                
                if otp:
                    try:
                        console.print("[dim]Submitting OTP...[/]")
                        # যেকোনো কোড ইনপুট ফিল্ড খুঁজে বের করা
                        code_input = page.locator('input[name="code"], input[autocomplete="one-time-code"], input[inputmode="numeric"]').first
                        code_input.fill(otp, timeout=10000)
                        
                        # সাবমিট বাটনে ক্লিক
                        page.locator('button[type="submit"], button:has-text("Continue"), button:has-text("Next")').first.click()
                        time.sleep(6)
                        
                        # OTP সফল হয়েছে কিনা চেক
                        if "checkpoint" not in page.url:
                            console.print("[bold green]✅ Account Created Successfully![/]")
                            identity["contact"] = contact
                            identity["status"] = "Success"
                            save_account(identity)
                        else:
                            console.print("[bold red]❌ OTP ভুল অথবা ফেসবুক ব্লক করেছে।[/]")
                    except Exception as e:
                        console.print(f"[red]OTP ফিল্ডে সমস্যা: {e}[/]")
            
            # ২. সরাসরি অ্যাকাউন্ট খুলে গেলে
            elif "home" in page_url or "welcome" in content:
                console.print("[bold green]✅ Account Created Successfully without OTP![/]")
                identity["contact"] = contact
                identity["status"] = "Success (No OTP)"
                save_account(identity)
            
            # ৩. ব্লক বা ক্যাপচা
            elif "disabled" in content or "blocked" in content or "captcha" in content:
                console.print("[bold red]❌ Facebook এই IP বা ডিভাইস ব্লক করেছে / CAPTCHA দিয়েছে। নতুন Proxy ব্যবহার করুন।[/]")
            else:
                console.print("[bold yellow]⚠ অজানা রেসপন্স। ফেসবুক হয়তো ফর্ম সাবমিট নেয়নি।[/]")

        except PlaywrightTimeoutError:
            console.print("[bold red]❌ Timeout: ফেসবুক পেজ লোড হতে অনেক সময় নিচ্ছে বা ইন্টারনেট স্লো।[/]")
        except Exception as e:
            console.print(f"\n[bold red]Error: {e}[/]")
        finally:
            if 'browser' in locals():
                browser.close()

    Prompt.ask("\n[dim]Press Enter to exit...[/]", default="")

if __name__ == "__main__":
    main()

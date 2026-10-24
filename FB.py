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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

console = Console()
fake = Faker('en_US')
ACCOUNTS_FILE = Path("accounts.txt")

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
        "gender": random.choice(["1", "2"]) 
    }

def save_account(data):
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"Contact: {data['contact']} | Pass: {data['password']} | Name: {data['first_name']} {data['last_name']} | Status: {data['status']}\n")

def main():
    console.clear()
    console.print(Panel.fit("[bold cyan]FACEBOOK AUTO REGISTRATION[/]\n[dim]Firefox + Termux Version[/]", border_style="cyan"))

    contact = Prompt.ask("\n[bold yellow]Enter Email or Phone Number[/]")
    
    if "@" not in contact:
        contact = contact.replace(" ", "").replace("-", "")
        if contact.startswith("+88"):
            contact = contact[3:]
        if contact.startswith("0"):
            contact = "88" + contact
            
    proxy = Prompt.ask("[bold yellow]Enter Proxy (host:port:user:pass) or leave blank[/]", default="")

    console.print("\n[dim]Generating English Identity...[/]")
    identity = generate_identity()
    
    t = Table(box=box.ROUNDED)
    t.add_column("Field", style="cyan")
    t.add_column("Value", style="green")
    t.add_row("Name", f"{identity['first_name']} {identity['last_name']}")
    t.add_row("Password", identity['password'])
    console.print(t)

    console.print("\n[bold yellow]▶ Launching Firefox Browser...[/]")
    
    # ─── Firefox Options ───
    options = Options()
    options.add_argument("-headless") # হেডলেস মোড
    options.set_preference("dom.webdriver.enabled", False)
    options.set_preference("useAutomationExtension", False)
    options.set_preference("general.useragent.override", "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0")
    
    if proxy:
        parts = proxy.split(":")
        if len(parts) == 4:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.http", parts[0])
            options.set_preference("network.proxy.http_port", int(parts[1]))
            options.set_preference("network.proxy.ssl", parts[0])
            options.set_preference("network.proxy.ssl_port", int(parts[1]))
            # Firefox-এ প্রোক্সি অথেনটিকেশন হ্যান্ডল করা একটু কঠিন, তবে সাধারণ ক্ষেত্রে কাজ করে
        elif len(parts) == 2:
            options.set_preference("network.proxy.type", 1)
            options.set_preference("network.proxy.http", parts[0])
            options.set_preference("network.proxy.http_port", int(parts[1]))

    driver = None
    try:
        # Geckodriver সার্ভিস
        service = Service(executable_path="/data/data/com.termux/files/usr/bin/geckodriver")
        print("→ Starting GeckoDriver...")
        driver = webdriver.Firefox(service=service, options=options)
        
        print("→ Firefox opened. Loading Facebook...")
        driver.get("https://www.facebook.com/reg/")
        
        wait = WebDriverWait(driver, 30)
        print("→ Waiting for form to load...")
        wait.until(EC.presence_of_element_located((By.NAME, "firstname")))
        print("→ Form loaded! Filling...")

        driver.find_element(By.NAME, "firstname").send_keys(identity["first_name"])
        driver.find_element(By.NAME, "lastname").send_keys(identity["last_name"])
        driver.find_element(By.NAME, "reg_email__").send_keys(contact)
        
        if "@" in contact:
            try:
                driver.find_element(By.NAME, "reg_email_confirmation__").send_keys(contact)
            except:
                pass

        driver.find_element(By.NAME, "reg_passwd__").send_keys(identity["password"])
        
        Select(driver.find_element(By.ID, "day")).select_by_value(identity["day"])
        Select(driver.find_element(By.ID, "month")).select_by_value(identity["month"])
        Select(driver.find_element(By.ID, "year")).select_by_value(identity["year"])
        
        driver.find_element(By.XPATH, f'//input[@name="sex" and @value="{identity["gender"]}"]').click()
        time.sleep(1)
        
        print("→ Submitting form...")
        driver.find_element(By.NAME, "websubmit").click()
        
        print("→ Waiting for Facebook response (8s)...")
        time.sleep(8) 

        page_url = driver.current_url
        content = driver.page_source.lower()
        
        if "checkpoint" in page_url or 'name="code"' in content or "confirm your email" in content:
            console.print("\n[bold cyan]⚠ Facebook OTP / Email Verification চাচ্ছে![/]")
            otp = Prompt.ask("[bold yellow]আপনার Email/SMS থেকে OTP দিন[/]")
            
            if otp:
                try:
                    console.print("[dim]Submitting OTP...[/]")
                    code_input = wait.until(EC.presence_of_element_located((By.XPATH, '//input[@name="code" or @autocomplete="one-time-code" or @inputmode="numeric"]')))
                    code_input.send_keys(otp)
                    
                    submit_btn = driver.find_element(By.XPATH, '//button[@type="submit" or contains(text(), "Continue") or contains(text(), "Next")]')
                    submit_btn.click()
                    time.sleep(6)
                    
                    if "checkpoint" not in driver.current_url:
                        console.print("[bold green]✅ Account Created Successfully![/]")
                        identity["contact"] = contact
                        identity["status"] = "Success"
                        save_account(identity)
                    else:
                        console.print("[bold red]❌ OTP ভুল অথবা ফেসবুক ব্লক করেছে।[/]")
                except Exception as e:
                    console.print(f"[red]OTP ফিল্ডে সমস্যা: {e}[/]")
        
        elif "home" in driver.current_url or "welcome" in content:
            console.print("[bold green]✅ Account Created Successfully without OTP![/]")
            identity["contact"] = contact
            identity["status"] = "Success (No OTP)"
            save_account(identity)
        
        elif "disabled" in content or "blocked" in content or "captcha" in content:
            console.print("[bold red]❌ Facebook এই IP বা ডিভাইস ব্লক করেছে / CAPTCHA দিয়েছে। নতুন Proxy ব্যবহার করুন।[/]")
        else:
            console.print("[bold yellow]⚠ অজানা রেসপন্স। ফেসবুক হয়তো ফর্ম সাবমিট নেয়নি।[/]")
            print(f"URL: {driver.current_url}")

    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/]")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

    Prompt.ask("\n[dim]Press Enter to exit...[/]", default="")

if __name__ == "__main__":
    main()

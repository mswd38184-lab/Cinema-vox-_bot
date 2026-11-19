import hashlib
import json
import os
import re
import sys
import time
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

# الروابط الرسمية لفروع VOX Cinemas في القاهرة فقط
VOX_BRANCHES = {
    "VOX مول مصر (Mall of Egypt)": "https://elcinema.com/theater/3101271/",
    "VOX سيتي سنتر ألماظة (Almaza)": "https://elcinema.com/theater/3101353/",
}

TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
FILE = "seen.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
}


def send_telegram_message(text):
    if not TOKEN or not CHAT_ID:
        print("تنبيه: TOKEN أو CHAT_ID غير موجودين.")
        return
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        res = requests.post(url, data=payload, timeout=15)
        res.raise_for_status()
    except Exception as e:
        print(f"فشل إرسال رسالة تليجرام: {e}")


def main():
    print("جاري فحص مواعيد VOX Cinemas Cairo...")
    current_items = {}

    for branch_name, branch_url in VOX_BRANCHES.items():
        try:
            res = requests.get(branch_url, headers=HEADERS, timeout=20)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")

            seen_movies_in_branch = set()
            for a in soup.find_all("a", href=re.compile(r"^/work/\d+")):
                movie_name = a.get_text(strip=True)
                href = a.get("href", "")
                if not movie_name or len(movie_name) < 2 or href in seen_movies_in_branch:
                    continue

                seen_movies_in_branch.add(href)
                movie_link = urljoin("https://elcinema.com", href)

                container = a.find_parent("div", class_="jumbo") or a.find_parent("div")
                times = []
                if container:
                    text_block = container.get_text(" ", strip=True)
                    times = re.findall(r"\b\d{1,2}:\d{2}\s*(?:ص|م|AM|PM|am|pm)\b", text_block)

                if not times:
                    sig = f"{branch_name}|{href}"
                    item_id = f"VOX_M_{hashlib.md5(sig.encode()).hexdigest()[:12]}"
                    current_items[item_id] = (
                        f"🎬 <b>فيلم جديد في {branch_name}!</b>\n\n"
                        f"الفيلم: <b>{movie_name}</b>\n"
                        f"🔗 التفاصيل: {movie_link}\n"
                        f"🎟️ للحجز: https://egy.voxcinemas.com"
                    )
                else:
                    for showtime in set(times):
                        sig = f"{branch_name}|{href}|{showtime}"
                        item_id = f"VOX_S_{hashlib.md5(sig.encode()).hexdigest()[:12]}"
                        current_items[item_id] = (
                            f"🎟️ <b>معاد جديد نزل في {branch_name}!</b>\n\n"
                            f"🎬 الفيلم: <b>{movie_name}</b>\n"
                            f"🕒 المعاد: <b>{showtime}</b>\n\n"
                            f"🔗 احجز من موقع فوكس:\nhttps://egy.voxcinemas.com"
                        )

            print(f"تم فحص {branch_name} بنجاح (عدد الأفلام: {len(seen_movies_in_branch)}).")
            time.sleep(1)

        except Exception as e:
            print(f"خطأ في فحص {branch_name}: {e}")

    print(f"إجمالي المواعيد والأفلام المرصودة: {len(current_items)}")

    if not current_items:
        print("لم يتم العثور على مواعيد حالياً.")
        sys.exit(0)

    seen = set()
    is_first_run = not os.path.exists(FILE)

    if not is_first_run:
        try:
            with open(FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    seen = set(data)
        except Exception:
            seen = set()

    if is_first_run or len(seen) == 0:
        print("أول تشغيل: حفظ المواعيد الحالية في seen.json...")
        with open(FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(current_items.keys())), f, ensure_ascii=False, indent=2)
        print("تم الحفظ بنجاح!")
        return

    new_keys = set(current_items.keys()) - seen
    print(f"عدد المواعيد الجديدة: {len(new_keys)}")

    for key in new_keys:
        send_telegram_message(current_items[key])
        time.sleep(0.5)

    if new_keys:
        updated_seen = sorted(list(seen | set(current_items.keys())))
        with open(FILE, "w", encoding="utf-8") as f:
            json.dump(updated_seen, f, ensure_ascii=False, indent=2)
        print("تم تحديث seen.json بنجاح.")


if __name__ == "__main__":
    main()

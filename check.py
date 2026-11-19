import hashlib
import json
import os
import sys
import time
from urllib.parse import urljoin
import requests
from playwright.sync_api import sync_playwright

# رابط أفلام فوكس سينما مصر
BASE_URL = "https://egy.voxcinemas.com/movies/whatson"

# لو حابب تراقب فرع معين بس اكتب اسمه هنا (مثلاً: "Mall of Egypt") أو سيبه فاضي "" لكل الفروع
TARGET_CINEMA = ""

TOKEN = os.environ.get("TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
FILE = "seen.json"


def send_telegram_message(text):
    """إرسال رسالة عبر بوت تليجرام"""
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
    print("جاري تشغيل المتصفح لفحص موقع VOX Cinemas Egypt...")
    current_items = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US"
        )
        page = context.new_page()

        try:
            print(f"فتح صفحة الأفلام: {BASE_URL}")
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_selector("article.movie-summary, a[href*='/movies/']", timeout=20000)
            time.sleep(2)
        except Exception as e:
            print(f"تعذر تحميل الصفحة الرئيسية لفوكس سينما: {e}")
            browser.close()
            sys.exit(1)

        movies = {}
        movie_elements = page.query_selector_all("article.movie-summary")

        if movie_elements:
            for el in movie_elements:
                link_el = el.query_selector("h3 a, a[href*='/movies/']")
                if link_el:
                    href = link_el.get_attribute("href")
                    title = link_el.inner_text().strip()
                    if href and title and "/movies/whatson" not in href and "/movies/comingsoon" not in href:
                        movies[urljoin(BASE_URL, href)] = title
        else:
            for a in page.query_selector_all("a[href*='/movies/']"):
                href = a.get_attribute("href")
                title = a.inner_text().strip()
                if href and title and len(title) > 2 and "whatson" not in href and "comingsoon" not in href:
                    movies[urljoin(BASE_URL, href)] = title

        print(f"تم العثور على {len(movies)} فيلم في فوكس سينما.")
        if not movies:
            browser.close()
            sys.exit(0)

        for movie_url, movie_name in movies.items():
            movie_id = f"VOX_MOVIE_{hashlib.md5(movie_url.encode()).hexdigest()[:10]}"
            current_items[movie_id] = {
                "text": f"🎬 <b>فيلم جديد في VOX Cinemas!</b>\n\nالفيلم: <b>{movie_name}</b>\nالرابط: {movie_url}"
            }

            try:
                page.goto(movie_url, wait_until="domcontentloaded", timeout=35000)
                time.sleep(2)

                booking_links = page.query_selector_all("a[href*='/booking/'], a[data-slug], .showtimes a")

                for b_link in booking_links:
                    time_text = " ".join(b_link.inner_text().split())
                    b_href = b_link.get_attribute("href") or ""

                    if not time_text or len(time_text) > 30:
                        continue

                    context_info = page.evaluate("""(el) => {
                        let cinema = "";
                        let exp = "";
                        let date = "";
                        
                        let cinemaSection = el.closest('[data-cinema], .cinema-showtimes, section');
                        if (cinemaSection) {
                            let h2 = cinemaSection.querySelector('h2, h3');
                            if (h2) cinema = h2.innerText.trim();
                        }
                        
                        let expSection = el.closest('ol, ul, .experience-group');
                        if (expSection && expSection.previousElementSibling) {
                            exp = expSection.previousElementSibling.innerText.trim();
                        }
                        
                        let activeDate = document.querySelector('.dates .active, [aria-selected="true"]');
                        if (activeDate) date = activeDate.innerText.replace(/\\n/g, ' ').trim();
                        
                        return {cinema, exp, date};
                    }""", b_link)

                    cinema_name = context_info.get("cinema", "غير محدد")
                    exp_name = context_info.get("exp", "")
                    date_str = context_info.get("date", "")

                    if TARGET_CINEMA and TARGET_CINEMA.lower() not in cinema_name.lower():
                        continue

                    full_booking_url = urljoin(movie_url, b_href) if b_href else movie_url
                    slot_signature = f"{movie_url}|{cinema_name}|{date_str}|{exp_name}|{time_text}|{b_href}"
                    slot_id = f"VOX_SLOT_{hashlib.md5(slot_signature.encode()).hexdigest()[:12]}"

                    details_parts = []
                    if cinema_name:
                        details_parts.append(f"📍 الفرع: {cinema_name}")
                    if date_str:
                        details_parts.append(f"📅 اليوم: {date_str}")
                    if exp_name:
                        details_parts.append(f"🎥 القاعة: {exp_name}")
                    details_parts.append(f"🕒 الساعة: <b>{time_text}</b>")

                    details_msg = "\n".join(details_parts)

                    current_items[slot_id] = {
                        "text": (
                            f"🎟️ <b>معاد حجز جديد في VOX Cinemas!</b>\n\n"
                            f"🎬 الفيلم: <b>{movie_name}</b>\n"
                            f"{details_msg}\n\n"
                            f"🔗 احجز تذكرتك الآن:\n{full_booking_url}"
                        )
                    }
            except Exception as e:
                print(f"خطأ أثناء فحص مواعيد فيلم {movie_name}: {e}")
                continue

        browser.close()

    print(f"إجمالي العناصر المرصودة في VOX: {len(current_items)}")

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
        print("أول تشغيل: حفظ مواعيد فوكس سينما الحالية كمرجع...")
        with open(FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(list(current_items.keys())), f, ensure_ascii=False, indent=2)
        print("تم الحفظ بنجاح.")
        return

    new_keys = set(current_items.keys()) - seen
    print(f"عدد التحديثات الجديدة في VOX: {len(new_keys)}")

    for key in new_keys:
        send_telegram_message(current_items[key]["text"])
        time.sleep(0.5)

    if new_keys:
        updated_seen = sorted(list(seen | set(current_items.keys())))
        with open(FILE, "w", encoding="utf-8") as f:
            json.dump(updated_seen, f, ensure_ascii=False, indent=2)
        print("تم تحديث ملف seen.json بنجاح.")


if __name__ == "__main__":
    main()

# файл: parser_stealth_with_stealth.py
import time
import json
import uuid
import random
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth

# === НАСТРОЙКИ ===================================
BASE_URL = "https://www.mvideo.ru/smartfony-i-svyaz-10/smartfony-205/f/brand=honor/tolko-v-nalichii=da"
PAGINATION_PARAM = "page="   # шаблон для добавления номера страницы
MAX_PAGES_TO_PARSE = 10000 # Максимальный лимит страниц для безопасности
OUTPUT_FILE = "flats_stealthV2.json"
# ==================================================

def random_sleep(a=1.0, b=2.5):
    time.sleep(random.uniform(a, b))

def human_move_and_scroll(driver):
    # Лёгкое движение мышки (0.05 сек)
    try:
        ActionChains(driver).move_by_offset(5, 5).perform()
    except:
        pass

    # Быстрый human-like скролл
    driver.execute_script("window.scrollBy(0, 250);")
    random_sleep(0.1, 0.15)
    driver.execute_script("window.scrollBy(0, 250);")

def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    stealth(driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
            )
    return driver

def find_product_container(driver):
    """
    Автоматическое определение контейнера с товарами и списка карточек.
    Возвращает tuple: (container, list_of_cards)
    """
    name_selectors = ["a.title-wrapper", "a.block_name u", "a.dark_link span", "div.item-title span"]
    price_selectors = ["span.price", "div.price", "div.price_block .price span", "div.price_matrix_block .price span"]


    containers = driver.find_elements(By.CSS_SELECTOR, "ul, div")
    for c in containers:
        children = c.find_elements(By.XPATH, "./*")
        if len(children) < 2:
            continue
        # проверяем, есть ли у большинства детей ссылка и цена
        matches = 0
        for child in children:
            if any(child.find_elements(By.CSS_SELECTOR, sel) for sel in name_selectors) and any(child.find_elements(By.CSS_SELECTOR, sel) for sel in price_selectors):
                matches += 1
        if matches / len(children) > 0.5:
            return c, children
    return None, []


# --- ФАЗА 1: Сбор ссылок со страницы каталога ---
def parse_cards(driver):
    """Собирает URL и Название со страницы каталога."""
    container, cards = find_product_container(driver)
    if not container:
        return []

    result = []
    for card in cards:
        try:
            # Универсальный поиск названия
            name_el = None
            for sel in ["a.title-wrapper", "a.block_name u", "a.dark_link span", "div.item-title span", "a.product-card__title"]:
                els = card.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    name_el = els[0]
                    break
            
            if not name_el:
                continue

            # Универсальный поиск URL
            url = name_el.find_element(By.XPATH, "./ancestor::a[@href]").get_attribute("href") if name_el.tag_name != "a" else name_el.get_attribute("href")
            name = name_el.text.strip()
            
            if url:
                 # Возвращаем только URL и Название (для логгирования/проверки дубликатов)
                 result.append({"url": url, "name": name})

        except Exception as e:
            # print(f"Ошибка сбора ссылки с карточки: {e}")
            continue
    return result

# --- ФАЗА 2: Детальный парсинг страницы товара ---
def parse_product_details(driver, url):
    """Переходит по URL и парсит все детальные поля."""
    print(f"  > Детальный парсинг: {url}")
    
    try:
        driver.get(url)
        # ⬇ Ускоренные паузы
        random_sleep(0.2, 0.4)
        # ⬇ Быстрый скролл для загрузки блоков
        driver.execute_script("window.scrollBy(0, 400);")
        random_sleep(0.1, 0.15)
        driver.execute_script("window.scrollBy(0, 800);")

        item = {
            "id": str(uuid.uuid4()),
            "url": url,
            "name": None,
            "price": "0",
            "currencyId": "RUB",
            "picture": [],
            "description": None,
            "available": None,
            "characteristics": {} # <-- НОВОЕ ПОЛЕ
        }

        # --- 1. Поиск Названия (надежнее на детальной) ---
        for sel in ["h1.item-title", "h1.product-title", "div.main-info h1", "h1"]:
            try:
                name_el = driver.find_element(By.CSS_SELECTOR, sel)
                item["name"] = name_el.text.strip()
                break
            except Exception:
                continue

        # --- 2. Поиск Цены (обновлённая логика) ---
        item["price"] = "0"
        item["oldPrice"] = None
        
        try:
            # Пробуем сначала найти meta[itemprop="price"]
            meta_price = driver.find_elements(By.CSS_SELECTOR, "meta[itemprop='price']")
            if meta_price:
                price_val = meta_price[0].get_attribute("content")
                if price_val and price_val.isdigit():
                    item["price"] = price_val.strip()
        
            # Затем проверяем наличие элементов с новой и старой ценой
            new_price_el = None
            old_price_el = None
        
            try:
                new_price_el = driver.find_element(By.CSS_SELECTOR, ".newqpricest")
            except Exception:
                pass
            
            try:
                old_price_el = driver.find_element(By.CSS_SELECTOR, ".oldpricest")
            except Exception:
                pass
            
            if new_price_el:
                new_price_text = re.sub(r"[^\d]", "", new_price_el.text)
                if new_price_text:
                    item["price"] = new_price_text
        
            if old_price_el:
                old_price_text = re.sub(r"[^\d]", "", old_price_el.text)
                if old_price_text:
                    item["oldPrice"] = old_price_text
        
            # Если не нашли ничего специфичного — fallback на старую универсальную логику
            if item["price"] == "0":
                for sel in [
                    "span.price",
                    "div.product-main-info span.price",
                    "div.item_main_info .price",
                    "div.product-price"
                ]:
                    try:
                        price_el = driver.find_element(By.CSS_SELECTOR, sel)
                        price_text = price_el.text.strip()
                        price_only_digits = re.sub(r"[^\d]", "", price_text)
                        if price_only_digits:
                            item["price"] = price_only_digits
                            break
                    except Exception:
                        continue
                    
        except Exception as e:
            print(f"Ошибка при парсинге цены: {e}")


        # --- 3. Поиск Описания (Улучшенная логика) ---
        item["description"] = None
        description_selectors = [
            "div[itemprop='description']",
            "div.tabs-panel.tab-content-description",
            "div.detail-description p",
            "div.description-block",
            "div.tab-pane.active div.description",
            "div.description-section div.content"
        ]

        for sel in description_selectors:
            try:
                desc_el = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                print('desc_el', desc_el)
                full_text = desc_el.text.strip()

                # Убираем всё после "Смотрите также" или "Теги товара"
                full_text = re.split(r"Смотрите также:|Теги товара:", full_text)[0].strip()

                # Удаляем заголовок вида "Описание товара Смартфон Nothing ..."
                full_text = re.sub(r"^Описание товара\s+[^\n]+", "", full_text, flags=re.IGNORECASE).strip()

                # Финальная очистка от двойных переносов и пробелов
                full_text = re.sub(r'\s{2,}', ' ', full_text).replace("\n", " ").strip()

                if full_text:
                    item["description"] = full_text
                    break
                
            except Exception:
                continue

       # --- 4. Поиск Наличия (булево) ---
        item["available"] = False
        
        try:
            # Основной вариант: ищем в блоке .art-prod
            art_prod_el = driver.find_element(By.CSS_SELECTOR, "div.art-prod")
            text = art_prod_el.text.strip().lower()
            
            if text:
                # Любой непустой текст считаем как "в наличии"
                item["available"] = True
            else:
                # Иногда текст пуст, но есть иконка
                try:
                    icon_el = art_prod_el.find_element(By.CSS_SELECTOR, ".product-item__status-icon")
                    classes = icon_el.get_attribute("class")
                    if "green" in classes:
                        item["available"] = True
                    elif "red" in classes:
                        item["available"] = False
                except Exception:
                    pass
                
            # Фоллбек на старые варианты
            if not item["available"]:
                for sel in [
                    "span.available",
                    "div.status-block span.in-stock",
                    "div.buy_block .available",
                    "span.product-availability"
                ]:
                    try:
                        avail_el = driver.find_element(By.CSS_SELECTOR, sel)
                        text = avail_el.text.strip().lower()
                        if text and ("в наличии" in text or "есть" in text):
                            item["available"] = True
                            break
                    except Exception:
                        continue
                    
        except Exception:
            pass
        

                # --- 5. Поиск Картинки (УЛУЧШЕННАЯ ЛОГИКА ДЛЯ МНОЖЕСТВЕННЫХ ФОТО) ---
        unique_pictures = set()
        
        # 1. Специфичный поиск всех миниатюр в слайдере
        try:
            # Ищем все изображения с классом mirfoto внутри списка слайдера
            slider_images = driver.find_elements(By.CSS_SELECTOR, "ul.slick-slider img.mirfoto")
            for img_el in slider_images:
                # Предпочитаем data-src, так как это часто оригинальное изображение для ленивой загрузки
                src = img_el.get_attribute("data-src") or img_el.get_attribute("src")
                if src and "kotofoto.ru" in src and not src.endswith("not_found.png"):
                    # URL часто не полные, добавляем схему, если отсутствует (хотя в примере они полные)
                    if not src.startswith(('http', 'https')):
                        src = f"https:{src}" if src.startswith('//') else src
                    
                    unique_pictures.add(src)
        except Exception:
            pass # Игнорируем ошибку, если слайдер не найден
            
        # 2. Сохраняем результат
        if unique_pictures:
            item["picture"] = list(unique_pictures)
        else:
            # Если специфичный поиск не сработал, возвращаемся к старой логике основного изображения (для универсальности)
            for sel in ["div.img-container img", "div.product-gallery img.main-image", "div.main-image-block img"]:
                try:
                    img_el = driver.find_element(By.CSS_SELECTOR, sel)
                    img_src = img_el.get_attribute("src")
                    print(img_src)
                    if img_src:
                        item["picture"] = [img_src]
                        break
                except Exception:
                    continue
        
        # --- 6. Поиск Характеристик (НОВАЯ ЛОГИКА) ---
        spec_containers = driver.find_elements(By.CSS_SELECTOR, "div.product-characteristics__spec")

        for container in spec_containers:
            try:
                # Ищем заголовок характеристики
                title_el = container.find_element(By.CSS_SELECTOR, ".product-characteristics__spec-title-content")
                # Ищем значение характеристики
                value_el = container.find_element(By.CSS_SELECTOR, ".product-characteristics__spec-value")
                
                title = title_el.text.strip().replace("\n", " ")
                value = value_el.text.strip().replace("\n", " ")
                
                if title and value:
                    item["characteristics"][title] = value
            except Exception:
                continue
        # --- КОНЕЦ НОВОЙ ЛОГИКИ ХАРАКТЕРИСТИК ---

        return item

    except Exception as e:
        print(f"Критическая ошибка парсинга {url}: {e}")
        return None

def main():
    print("Запуск парсера...")
    driver = create_driver()
    all_items = []

    seen_product_urls = set()

    try:
        for page_num in range(1, MAX_PAGES_TO_PARSE + 1):
            if page_num == 1:
                page_url = BASE_URL
            else:
                # проверяем, есть ли уже "?" в BASE_URL
                separator = "&" if "?" in BASE_URL else "?"
                page_url = f"{BASE_URL}{separator}{PAGINATION_PARAM}{page_num}"

            print(f"Парсинг страницы {page_num}: {page_url}")
            driver.get(page_url)
            random_sleep(0.2, 0.4)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.25);")
            random_sleep(0.1, 0.15)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5);")
            time.sleep(10)
            items = parse_cards(driver)
            if not items:
                print(f"На странице {page_num} не найдено товаров. Остановка.")
                break
            
            new_items_on_this_page = []
            for item in items:
                product_url = item.get("url")
                if not product_url or product_url in seen_product_urls:
                    continue
                seen_product_urls.add(product_url)
                new_items_on_this_page.append(item)

            if not new_items_on_this_page:
                print("Дубликаты или пустая страница — выход.")
                break
            
            print(f"Найдено {len(new_items_on_this_page)} новых товаров, начинаю детальный парсинг...")

            for product in new_items_on_this_page:
                details = parse_product_details(driver, product["url"])
                if details:
                    all_items.append(details)
                else:
                    print(f"Ошибка при парсинге {product['url']}")


        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_items, f, ensure_ascii=False, indent=2)

        print(f"Всего собрано {len(all_items)} товаров. Сохранено в {OUTPUT_FILE}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()

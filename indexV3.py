# файл: parser_stealth_with_stealth.py
import time
import json
import uuid
import random
import re
import threading
from concurrent.futures import ThreadPoolExecutor # <-- НОВЫЙ ИМПОРТ ДЛЯ УСКОРЕНИЯ
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
from bs4 import BeautifulSoup # <-- ДОБАВЛЕН ДЛЯ ПОТЕНЦИАЛЬНОЙ БУДУЩЕЙ ОПТИМИЗАЦИИ (не используется в текущей версии, но полезен)
from urllib.parse import urlparse
from selenium.common.exceptions import StaleElementReferenceException # Импорт ошибки

# === НАСТРОЙКИ ===================================
BASE_URL_FULL = "https://www.citilink.ru/catalog/noutbuki/MSI--4k-uhd-msi/?ref=mainpage_popular"
PAGINATION_PARAM = "page=" 
MAX_PAGES_TO_PARSE = 10000 
OUTPUT_FILE = "flats_stealthV3.json"
MAX_WORKERS = 6 # <-- КОЛИЧЕСТВО ОДНОВРЕМЕННО ОБРАБАТЫВАЕМЫХ ТОВАРОВ
BASE_URL = f"{urlparse(BASE_URL_FULL).scheme}://{urlparse(BASE_URL_FULL).netloc}"
# ==================================================

# Удален random_sleep. Используйте time.sleep(0.05) только при необходимости.

def human_move_and_scroll(driver):
    # Лёгкое движение мышки
    try:
        ActionChains(driver).move_by_offset(5, 5).perform()
    except:
        pass

    # Быстрый human-like скролл (с минимальной паузой)
    driver.execute_script("window.scrollBy(0, 250);")
    time.sleep(0.25)
    driver.execute_script("window.scrollBy(0, 250);")
    time.sleep(0.25)

def smart_scroll(driver, step=400, pause=0.7, max_loops=40):
    """
    Постепенный скролл страницы небольшими шагами,
    чтобы успевала подгружаться ленивая загрузка.
    """
    last_height = 0

    for _ in range(max_loops):
        # текущая высота
        current_height = driver.execute_script("return window.pageYOffset;")
        full_height = driver.execute_script("return document.body.scrollHeight;")

        # если достигли конца — стоп
        if current_height + step >= full_height:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause)
            new_height = driver.execute_script("return document.body.scrollHeight;")
            if new_height == full_height:
                break
            else:
                full_height = new_height
                continue

        # скроллим небольшим шагом вниз
        driver.execute_script(f"window.scrollBy(0, {step});")
        time.sleep(pause)

        # проверяем, изменилась ли высота DOM
        new_height = driver.execute_script("return document.body.scrollHeight;")
        if new_height == last_height:
            # ничего нового не подгрузилось — возможно, это конец
            break

        last_height = new_height



def create_driver():
    """Создает и настраивает драйвер с Headless-режимом и отключением изображений."""
    options = webdriver.ChromeOptions()
    
    # ⚡️ Ускорение 1: Headless и отключение изображений
    options.add_argument("--headless") # Включение безголового режима
    options.add_argument("--disable-gpu")
    
    # Отключаем загрузку изображений
    options.add_experimental_option(
        "prefs", {"profile.managed_default_content_settings.images": 2}
    )
    
    # Остальные настройки
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

# ... find_product_container, parse_cards (без изменений, так как они работают с WebDriver) ...
def find_product_container(driver):
    """
    Автоматическое определение контейнера с товарами и списка карточек.
    Возвращает tuple: (container, list_of_cards)
    """
    
    name_selectors = [
        "a.title-wrapper",
        "a.block_name u",
        "a.dark_link span",
        "div.item-title span",
        "a.product-title__text",
        "a.product-title__text",
        "[class*='title']",
        "[class*='name']",
        "div.product-item-title a",
        'a[data-meta-name="Snippet__title"]'
    ]

    price_selectors = [
        "span.price",
        "div.price",
        "div.price_block .price span",
        "div.price_matrix_block .price span",
        "div.price span.price__sale-value",
        "span.price__main-value",
        "[class*='price']",
        "div.product-item-price",
        'span[data-meta-name="Snippet__price"]'
    ]

    # 1. Сначала находим все потенциальные контейнеры
    containers = driver.find_elements(By.CSS_SELECTOR, "ul, div, section, mvid-product-cards-list-container, div.row, div:has([data-meta-name='ProductHorizontalSnippet'])")
    
    for c in containers:
        try:
            # ⚡️ Изменение: Оборачиваем поиск дочерних элементов в try/except
            # Если элемент 'c' устарел, мы его просто пропускаем.
            children = c.find_elements(By.XPATH, "./*") 
            
            if len(children) < 2:
                continue
                
            # проверяем, есть ли у большинства детей ссылка
            matches = 0
            for child in children:
                # Внутренние find_elements также могут вызвать StaleElement, 
                # поэтому используем вложенный try/except.
                try:
                    has_name = any(child.find_elements(By.CSS_SELECTOR, sel) for sel in name_selectors)
                    has_price = any(child.find_elements(By.CSS_SELECTOR, sel) for sel in price_selectors)
                    
                    if has_name and has_price:
                        matches += 1
                except StaleElementReferenceException:
                    # Пропускаем только этот дочерний элемент
                    continue
                    
            # ⚡️ Изменение: Добавлена проверка на len(children) > 0 для избежания деления на ноль.
            # Если найдено достаточно совпадений, возвращаем результат.
            if len(children) > 0 and matches / len(children) > 0.5:
                return c, children
            

            # === 2. НОВЫЙ Fallback-для сайтов как М.Видео ===

            selector = (
                "div[class*='card'], "
                "div[class*='product'], "
                "article, "
                "li[class*='item'], "
                "div.product-card--list, "
                "div.product-cards-layout__item, "
                "div.product-card--list"
            )

            deep_cards = c.find_elements(By.CSS_SELECTOR, selector)


            # фильтруем только те, что содержат и имя и цену
            valid_cards = []
            for card in deep_cards:
                try:
                    has_name = any(card.find_elements(By.CSS_SELECTOR, sel) for sel in name_selectors)
                    has_price = any(card.find_elements(By.CSS_SELECTOR, sel) for sel in price_selectors)
                    if has_name and has_price:
                        valid_cards.append(card)
                except:
                    continue

            # Если таких карточек 3+ → это каталог
            if len(valid_cards) >= 3:
                return c, valid_cards

                
        except StaleElementReferenceException:
            # Если сам родительский контейнер 'c' устарел, пропускаем его и переходим к следующему
            continue
            
    # Если цикл завершился без нахождения подходящего контейнера:
    return None, []


# --- ФАЗА 1: Сбор ссылок со страницы каталога ---
def parse_cards(driver):
    """Собирает URL и Название со страницы каталога."""
    container, cards = find_product_container(driver)
    # print('cards', cards)
    if not container:
        return []

    result = []
    for card in cards:
        try:
            # Универсальный поиск названия
            name_el = None
            for sel in ["a.title-wrapper", "a.block_name u", "a.dark_link span", "div.item-title span", "a.product-card__title", "a.product-title__text", "div.product-item-title a", 'a[data-meta-name="Snippet__title"]']:
                els = card.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    name_el = els[0]
                    break
            
            # print(name_el)
            if not name_el:
                continue
            # print(1111111)    
            # Универсальный поиск URL
            url = name_el.find_element(By.XPATH, "./ancestor::a[@href]").get_attribute("href") if name_el.tag_name != "a" else name_el.get_attribute("href")
            name = name_el.text.strip()
            # print(url)
            if url:
                    # Возвращаем только URL и Название (для логгирования/проверки дубликатов)
                    result.append({"url": url, "name": name})

        except Exception as e:
            # print(f"Ошибка сбора ссылки с карточки: {e}")
            continue
    return result

# --- ФАЗА 2: Детальный парсинг страницы товара (ОПТИМИЗИРОВАНО) ---
def parse_product_details(driver, url):
    """Переходит по URL и парсит все детальные поля."""
    print(f" Детальный парсинг: {url}")
    
    try:
        driver.get(url)
        
        # ⬇ Удалены random_sleep
        # ⬇ Быстрый скролл для загрузки блоков (с минимальной паузой)
        driver.execute_script("window.scrollBy(0, 400);")
        time.sleep(0.25)
        driver.execute_script("window.scrollBy(0, 800);")
        time.sleep(0.25)

        item = {
            "id": str(uuid.uuid4()),
            "url": url,
            "name": None,
            "price": "0",
            "currencyId": "RUB",
            "picture": [],
            "description": None,
            "available": False,
            "characteristics": {}
        }

        # --- 1. Поиск Названия (ОПТИМИЗИРОВАНО) ---
        name_selectors = [
            "h1.item-title",
            "h1.product-title",
            "div.main-info h1",
            "h1"
        ]
        
        item["name"] = None
        
        for sel in name_selectors:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                text = el.text.strip()
                
                if not text:
                    text = driver.execute_script("return arguments[0].textContent;", el)
                    
                    if text:
                        text = text.strip()

                if text:
                    item["name"] = text
                    break
            except:
                continue

        # --- 2. Поиск Цены (ОПТИМИЗИРОВАНО: сфокусировано на find_elements) --- 
        price_selectors = [
            "span.price",
            "div.product-main-info span.price",
            "div.item_main_info .price",
            "div.product-price",
            "div.price",
            "span.new-price",

            'div[data-meta-name="PriceBlock__price"] span[data-meta-price] span'
        ]

        js_code = f"""
        let result = {{ price: "0", oldPrice: null }};

        try {{
            // 1) meta
            let metaPrice = document.querySelector("meta[itemprop='price']");
            if (metaPrice) {{
                let val = metaPrice.getAttribute("content");
                if (val && /^\\d+$/.test(val.trim())) result.price = val.trim();
            }}

            // 2) специфичные селекторы
            let newEl = document.querySelector(".newqpricest");
            let oldEl = document.querySelector(".oldpricest");

            if (newEl) {{
                let newText = newEl.innerText.replace(/\\D/g, "");
                if (newText) result.price = newText;
            }}

            if (oldEl) {{
                let oldText = oldEl.innerText.replace(/\\D/g, "");
                if (oldText) result.oldPrice = oldText;
            }}

            // 2.1) Добавляем поддержку:
            // <span class="price__main-value">25 999 ₽</span>
            // <span class="price__sale-value">49 999</span>

            let mainVal = document.querySelector(".price__main-value");
            if (mainVal) {{
                let t = mainVal.innerText.replace(/\\D/g, "");
                if (t) result.price = t;
            }}

            let saleVal = document.querySelector(".price__sale-value");
            if (saleVal) {{
                let t = saleVal.innerText.replace(/\\D/g, "");
                if (t) result.oldPrice = t;
            }}

            // === 2.2) Новый сайт: data-meta-price ===
            let metaPriceSpan = document.querySelector('div[data-meta-name="PriceBlock__price"] span[data-meta-price]');
            if (metaPriceSpan) {{
                let raw = metaPriceSpan.getAttribute("data-meta-price");
                if (raw) {{
                    let cleaned = raw.replace(/\\D/g, "");
                    if (cleaned) result.price = cleaned;
                }}
            }}

            // === 2.3) Клубная цена → oldPrice ===
            let clubPriceSpan = document.querySelector('div[data-meta-name="PriceBlock__club-price"] span');
            if (clubPriceSpan) {{
                let club = clubPriceSpan.innerText.replace(/\\D/g, "");
                if (club) result.oldPrice = club;
            }}

            // 3) универсальные селекторы fallback
            if (result.price === "0") {{
                let selectors = {price_selectors};
                for (let sel of selectors) {{
                    let container = document.querySelector(sel);
                    if (container) {{

                        // ищем старую цену (.old_price или sale-value)
                        let oldSpan = container.querySelector(".old_price span, .price__sale-value, span.old-price");
                        if (oldSpan) {{
                            let oldText = oldSpan.innerText.replace(/\\D/g, "");
                            if (oldText) result.oldPrice = oldText;
                        }}

                        // ищем новую цену (main-value или просто span)
                        let spanElems = container.querySelectorAll(".price__main-value, span");
                        for (let s of spanElems) {{
                            let newText = s.innerText.replace(/\\D/g, "");
                            if (newText) {{
                                result.price = newText;
                                break;
                            }}
                        }}

                        if (result.price !== "0") break;
                    }}
                }}
            }}
        }} catch(e) {{
            console.log("Ошибка при парсинге цены:", e);
        }}

        return result;
        """

        # выполнение JS через Selenium
        price_data = driver.execute_script(js_code)

        # записываем в item
        item["price"] = price_data.get("price", "0")
        item["oldPrice"] = price_data.get("oldPrice", None)


       # --- 3. Поиск Описания (добавлена таблица item_features) ---
        item["description"] = None

        description_selectors = [
            "div[itemprop='description']",
            "div.tabs-panel.tab-content-description",
            "div.detail-description p",
            "div.description-block",
            "div.tab-pane.active div.description",
            "div.description-section div.content",
            "div.seo-text",
            "div.body-product-item"

            "div.view-desktop"
        ]

        try:
            js_script = f"""
            let parts = [];

            // сначала ищем текст по стандартным селекторам
            let selectors = {description_selectors};
            selectors.forEach(sel => {{
                let el = document.querySelector(sel);
                if (el && el.innerText.trim()) {{
                    parts.push(el.innerText.trim());
                }}
            }});

            // затем ищем таблицу item_features
            let table = document.querySelector('table.item_features');
            if (table) {{
                let rows = table.querySelectorAll('tr');
                rows.forEach(row => {{
                    let tds = row.querySelectorAll('td');
                    if (tds.length >= 2) {{
                        parts.push(tds[1].innerText.trim());
                    }}
                    let nested = row.querySelector('.item_description');
                    if (nested) {{
                        parts.push(nested.innerText.trim());
                    }}
                }});
            }}

            return parts.join(' | ');
            """

            description = driver.execute_script(js_script)
            if description:
                # нормализация пробелов и переносов
                description = re.sub(r'\s+', ' ', description).strip()
                item["description"] = description

        except Exception:
            item["description"] = None

        # --- 4. Поиск Наличия (ОПТИМИЗИРОВАНО: сфокусировано на find_elements) ---
        availability_selectors = [
            "div.art-prod",
            "span.available",
            "div.status-block span.in-stock",
            "div.buy_block .available",
            "span.product-availability",
            ".in_stock",
            "span.in_stock .green",
            "span.in_stock span",
            "span.ml25.no-mods-amount",
            "div.bootstrap-reboot",

            "p.product-sold-out-text",
            "p.product-unavailable-text",
            "div.product-not-available",
            "mvid-product-details-card p",

            "div.block_btn-product button"
        ]
        
        js_code = f"""
        let available = false;
        let selectors = {availability_selectors};

        // ключевые слова отсутствия
        let negativeKeywords = [
            "нет в наличии",
            "отсутствует",
            "распродан",
            "закончился",
            "нет доступных предложений",
            "временно отсутствует",
            "временно недоступен",
            "нет товара",
            "Подобрать аналог"
        ];

        for (let sel of selectors) {{
            try {{
                let elements = document.querySelectorAll(sel);
                for (let el of elements) {{
                    let text = (el.innerText || el.textContent || "").trim().toLowerCase();

                    // 1) сначала ищем отсутствие
                    if (negativeKeywords.some(k => text.includes(k))) {{
                        return false; // сразу прекращаем — товара точно НЕТ
                    }}

                    // 2) ищем наличие
                    if (text.includes("в наличии") || text.includes("есть")) {{
                        available = true;
                        break;
                    }}

                    // 3) универсальная проверка на наличие количества
                    if (/[0-9]/.test(text) && !text.includes("0")) {{
                        available = true;
                        break;
                    }}
                }}
                if (available) break;
            }} catch(e) {{
                continue;
            }}
        }}

        return available;
        """
        
        # выполнение JS через Selenium
        item["available"] = driver.execute_script(js_code)

        # --- 5. Поиск Картинки (УЛУЧШЕННАЯ УНИВЕРСАЛЬНАЯ ЛОГИКА) ---
        image_selectors = [
            "div.slick-track img",
            "div.slick-list img",
            "div.slider-item img",
            "ul.slick-slider img",
            "div.page_product-image img",
            "ul.slick-slider img.mirfoto",
            "div.multiphoto a.photo-preview img",
            "div.main_img img",
            "div.img-container img",
            "div.product-gallery img.main-image",
            "div.main-image-block img",
            "div.img_wrapper #fixed_slider li img",
            "div.item_slider.color-controls ul.slides img",
            "div.slides li link[itemprop='image']",
            "div.slides li a.popup_link img",
            "div.item img",
            'div[data-meta-name="ImageGallery__thumbs"] div div div img'
        ]

        js_images = f"""
        let unique_pictures = new Set();

        try {{
            for (let sel of {image_selectors}) {{
                let imgs = document.querySelectorAll(sel);
                imgs.forEach(img => {{
                    let src = img.getAttribute("data-large") || img.getAttribute("data-src") || img.getAttribute("src");
                    if (src) {{
                        // добавляем протокол, если начинается с //
                        if (src.startsWith("//")) {{
                            src = "https:" + src;
                        }}
                        // добавляем BASE_URL, если ссылка относительная
                        else if (!src.startsWith("http")) {{
                            src = "{BASE_URL}" + src;
                        }}
                        // фильтруем пустые и заглушки
                        if (src.trim() && !src.includes("not_found")) {{
                            unique_pictures.add(src);
                        }}
                    }}
                }});
            }}
        }} catch(e) {{
            console.log("Ошибка при поиске картинок:", e);
        }}

        return Array.from(unique_pictures);
        """

        item["picture"] = driver.execute_script(js_images)
        
        # --- 6. Поиск Характеристик ---
        characteristics_selectors = [
            "table.props_list.nbg tr[itemprop='additionalProperty']",  # новая разметка
            "div.product-characteristics__spec",  # старая разметка
            "mvid-key-characteristics .characteristics-item",
            "div.product-item-char ul",
            "div[data-meta-name='ProductHeaderContentLayout__second-column'] div div ul li"
        ]

        js_characteristics = f"""
        let characteristics = {{}};
        let selectors = {characteristics_selectors};

        selectors.forEach(sel => {{
            try {{
                let rows = document.querySelectorAll(sel);
                rows.forEach(row => {{
                    try {{
                        let nameEl = null;
                        let valueEl = null;

                        // 1) табличная разметка
                        if (row.querySelector("td.char_name span[itemprop='name']")) {{
                            nameEl = row.querySelector("td.char_name span[itemprop='name']");
                            valueEl = row.querySelector("td.char_value span[itemprop='value']");
                        }}

                        // 2) старая разметка продукта
                        if (!nameEl || !valueEl) {{
                            let n = row.querySelector(".product-characteristics__spec-title-content");
                            let v = row.querySelector(".product-characteristics__spec-value");
                            if (n && v) {{
                                nameEl = n;
                                valueEl = v;
                            }}
                        }}

                        // 3) НОВАЯ разметка МВидео (<dt>/<dd>)
                        if (!nameEl || !valueEl) {{
                            let dt = row.querySelector("dt");
                            let dd = row.querySelector("dd");
                            if (dt && dd) {{
                                nameEl = dt;
                                valueEl = dd;
                            }}
                        }}

                         // 4) Новая разметка li/span
                        if (!nameEl || !valueEl) {{
                            let spans = row.querySelectorAll("span");
                            if (spans.length >= 2) {{
                                let nameCandidate = spans[0].innerText.trim().replace(/\\s+/g, " ");;
                                let valueCandidate = spans[1].innerText.trim().replace(/\\s+/g, " ");;

                                if (nameCandidate && valueCandidate) {{
                                    characteristics[nameCandidate] = valueCandidate;
                                    return;
                                }}
                            }}
                        }}

                        if (nameEl && valueEl) {{
                            let name = nameEl.innerText.trim().replace(/\\s+/g, " ");
                            let value = valueEl.innerText.trim().replace(/\\s+/g, " ");
                            if (name && value) {{
                                characteristics[name] = value;
                            }}
                        }}
                    }} catch(e) {{}}
                }});
            }} catch(e) {{}}
        }});

        return characteristics;
        """
        # print(driver.execute_script(js_characteristics))
  

        item["characteristics"] = driver.execute_script(js_characteristics)

        return item

    except Exception as e:
        print(f"Критическая ошибка парсинга {url}: {e}")
        return None

# --- ГЛАВНАЯ ФУНКЦИЯ (ДОБАВЛЕН ПАРАЛЛЕЛИЗМ) ---
def main():
    print(f"Запуск парсера с {MAX_WORKERS} потоками...")
    
    # Драйвер для сбора ссылок в каталоге (Фаза 1)
    catalog_driver = create_driver() 
    all_product_urls = []
    seen_product_urls = set()

    # --- ФАЗА 1: Сбор ссылок ---
    try:
        for page_num in range(1, MAX_PAGES_TO_PARSE + 1):
            if page_num == 1:
                page_url = BASE_URL_FULL
            else:
                separator = "&" if "?" in BASE_URL else "?"
                page_url = f"{BASE_URL_FULL}{separator}{PAGINATION_PARAM}{page_num}"

            print(f"Парсинг страницы {page_num} каталога...")
            catalog_driver.get(page_url)
            time.sleep(3.0) # Небольшая пауза после загрузки страницы каталога
            
            smart_scroll(catalog_driver)

            time.sleep(3.0)
            
            items = parse_cards(catalog_driver)
            # print('items', items)
            if not items:
                print(f"На странице {page_num} не найдено товаров. Остановка.")
                break
            
            new_urls_on_page = []
            for item in items:
                product_url = item.get("url")
                if product_url and product_url not in seen_product_urls:
                    seen_product_urls.add(product_url)
                    new_urls_on_page.append(product_url)
                    
            # print('new_urls_on_page', new_urls_on_page)
            if not new_urls_on_page:
                print("Найдено только дубликаты. Остановка сбора ссылок.")
                break
                
            all_product_urls.extend(new_urls_on_page)
            # print('all_product_urls', all_product_urls)

    finally:
        catalog_driver.quit()


    # --- ФАЗА 2: Детальный парсинг (ПАРАЛЛЕЛЬНО) ---
    print(f"Начинаю детальный парсинг {len(all_product_urls)} товаров в {MAX_WORKERS} потоках...")
    
    all_items = []
    
    # ⚡️ Ускорение 2: Использование ThreadPoolExecutor для параллельной работы
    
    # 1. Создаем пул драйверов, по одному на каждый поток
    drivers = [create_driver() for _ in range(MAX_WORKERS)] 
    
    # Оберточная функция, чтобы передать драйвер из пула
    def worker_wrapper(url, driver):
        return parse_product_details(driver, url)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Запускаем задачи, используя zip для распределения ссылок по драйверам
        # (Каждый поток получит свой драйвер для работы)
        futures = []
        for i, url in enumerate(all_product_urls):
            driver = drivers[i % MAX_WORKERS] # Распределяем драйверы по кругу
            futures.append(executor.submit(worker_wrapper, url, driver))
        
        for i, future in enumerate(futures):
            try:
                result = future.result()
                if result:
                    all_items.append(result)
                    if (i + 1) % 10 == 0:
                         print(f"Спарсено: {i + 1}/{len(all_product_urls)} товаров.")
            except Exception as e:
                print(f"Ошибка при выполнении потока для товара {i+1}: {e}")

    # 2. Обязательно закрываем все драйверы
    for driver in drivers:
        driver.quit()
        
    # --- ФАЗА 3: Сохранение результатов ---
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f" Завершено. Всего собрано {len(all_items)} товаров. Сохранено в {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
import asyncio
from time import time
import os
import random
import ctypes

from patchright.async_api import async_playwright
from loguru import logger
from dotenv import load_dotenv
from proxystr import Proxy
import cv2
import numpy as np
import pyautogui
import platform
from .source import Singleton
from .models import CaptchaTask

load_dotenv()


class WindowGridManager:
    def __init__(self, window_width=500, window_height=200, vertical_overlap=60):
        self.window_width = window_width
        self.window_height = window_height
        self.vertical_step = window_height - vertical_overlap

        screen_width, screen_height = self.get_screen_size()
        self.cols = screen_width // window_width
        self.rows = screen_height // self.vertical_step

        self.grid = []
        self._generate_grid()

    @staticmethod
    def get_screen_size():
        system = platform.system()

        if system == "Windows":
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            screen_width = user32.GetSystemMetrics(0)
            screen_height = user32.GetSystemMetrics(1)
            return screen_width, screen_height

        elif system == "Darwin":  # macOS
            try:
                import AppKit
                screen = AppKit.NSScreen.mainScreen()
                frame = screen.frame()
                return int(frame.size.width), int(frame.size.height)
            except ImportError:
                raise RuntimeError("AppKit is required on macOS to get screen size. Install with `pip install pyobjc`.")

        elif system == "Linux":
            try:
                import subprocess
                output = subprocess.check_output("xdpyinfo | grep dimensions", shell=True).decode()
                dims = output.strip().split()[1]
                width, height = map(int, dims.split('x'))
                return width, height
            except Exception as e:
                raise RuntimeError("Failed to get screen size on Linux: " + str(e))

        else:
            raise NotImplementedError(f"Screen size detection not supported on {system}")

    def _generate_grid(self):
        index = 0
        for row in range(self.rows):
            for col in range(self.cols):
                self.grid.append({
                    "id": index,
                    "x": col * self.window_width,
                    "y": row * self.vertical_step,
                    "is_occupied": False
                })
                index += 1

    def get_free_position(self):
        for pos in self.grid:
            if not pos["is_occupied"]:
                pos["is_occupied"] = True
                return pos
        raise RuntimeError("Нет свободных мест для окон.")

    def release_position(self, pos_id):
        for pos in self.grid:
            if pos["id"] == pos_id:
                pos["is_occupied"] = False
                return
        raise ValueError(f"Позиция {pos_id} не найдена.")

    def reset(self):
        for pos in self.grid:
            pos["is_occupied"] = False


class BrowserHandler(metaclass=Singleton):
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.proxy = self.read_proxy()
        self.window_manager = WindowGridManager()

    @staticmethod
    def read_proxy():
        if proxy := os.getenv('PROXY'):
            return Proxy(proxy).playwright

    async def launch(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=False,
            channel='chrome',
            args=[
                '--disable-blink-features=AutomationControlled',
                "--window-size=500,200",
                "--window-position=0,0"],
            proxy=self.proxy
        )

    async def get_page(self):
        if not self.playwright or not self.browser:
            await self.launch()

        context = await self.browser.new_context(viewport={"width": 500, "height": 100})
        # context = await self.browser.new_context(no_viewport=True)

        logger.debug(f"open page")
        page = await context.new_page()
        position = self.window_manager.get_free_position()
        await self.set_window_position(page, position["x"], position["y"])
        page._grid_position_id = position["id"]
        return page

    async def get_pages(self, amount: int = 1):
        if not self.playwright or not self.browser:
            await self.launch()

        pages = []
        for i in range(amount):
            context = await self.browser.new_context(viewport={"width": 500, "height": 100})
            logger.debug(f"open page {i}")
            pages.append(await context.new_page())
        return pages

    @staticmethod
    async def set_window_position(page, x, y):
        session = await page.context.new_cdp_session(page)
        # Получаем windowId
        result = await session.send("Browser.getWindowForTarget")
        window_id = result["windowId"]
        # Устанавливаем позицию
        await session.send("Browser.setWindowBounds", {
            "windowId": window_id,
            "bounds": {
                "left": x,
                "top": y,
                "width": 500,
                "height": 200
            }
        })

    async def close(self):
        try:
            await self.browser.close()
        except Exception:
            pass
        try:
            await self.playwright.stop()
        except Exception:
            pass

    async def close_page(self, page):
        self.window_manager.release_position(page._grid_position_id)
        await page.close()
        await page.context.close()


class Browser:
    def __init__(self, page=None):
        self.page = page
        self.lock = asyncio.Lock()

    async def solve_captcha(self, task: CaptchaTask):
        if not self.page:
            self.page = await BrowserHandler().get_page()

        async with self.lock:
            try:
                await self.block_rendering()
                await self.page.goto(task.websiteURL)
                await self.unblock_rendering()
                await self.load_captcha(websiteKey=task.websiteKey)
                return await self.wait_for_turnstile_token()
            finally:
                await BrowserHandler().close_page(self.page)
                self.page = None

    async def antishadow_inject(self):
        await self.page.add_init_script("""
          (function() {
            const originalAttachShadow = Element.prototype.attachShadow;
            Element.prototype.attachShadow = function(init) {
              const shadow = originalAttachShadow.call(this, init);
              if (init.mode === 'closed') {
                window.__lastClosedShadowRoot = shadow;
              }
              return shadow;
            };
          })();
        """)

    async def load_captcha(self, websiteKey: str = '0x4AAAAAAA0SGzxWuGl6kriB', action: str = ''):
        script = f"""
        // 🧹 Удаляем предыдущую капчу, если есть
        const existing = document.querySelector('#captcha-overlay');
        if (existing) existing.remove();  // очистка предыдущего

        // 🔳 Создаём overlay
        const overlay = document.createElement('div');
        overlay.id = 'captcha-overlay';
        overlay.style.position = 'absolute';
        overlay.style.top = '0';
        overlay.style.left = '0';
        overlay.style.width = '100vw';
        overlay.style.height = '100vh';
        overlay.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
        overlay.style.display = 'block';
        overlay.style.justifyContent = 'center';
        overlay.style.alignItems = 'center';
        overlay.style.zIndex = '1000';

        // 🧩 Добавляем капчу
        const captchaDiv = document.createElement('div');
        captchaDiv.className = 'cf-turnstile';
        captchaDiv.setAttribute('data-sitekey', '{websiteKey}');
        captchaDiv.setAttribute('data-callback', 'onCaptchaSuccess');
        captchaDiv.setAttribute('data-action', '');

        overlay.appendChild(captchaDiv);
        document.body.appendChild(overlay);

        // 📜 Загружаем Cloudflare Turnstile
        const script = document.createElement('script');
        script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
        script.async = true;
        script.defer = true;
        document.head.appendChild(script);
        """

        # Выполняем скрипт в браузере через Selenium
        await self.page.evaluate(script)

    async def wait_for_turnstile_token(self) -> str | None:
        locator = self.page.locator('input[name="cf-turnstile-response"]')

        token = ""
        t = time()
        while not token:
            await asyncio.sleep(0.5)
            try:
                token = await locator.input_value(timeout=500)
                if await self.check_for_checkbox():
                    logger.debug('click checkbox')
            except Exception as er:
                logger.error(er)
                pass
            if token:
                logger.debug(f'got captcha token: {token}')
            if t + 15 < time():
                logger.warning('token not found')
                return None
        return token

    @staticmethod
    def get_coords_to_click(page, x, y):
        id_ = page._grid_position_id
        pos = BrowserHandler().window_manager.grid[id_]
        _x, _y = pos['x'], pos['y']
        return _x + x + random.randint(5, 10), _y + y + random.randint(75, 85)

    async def check_for_checkbox(self):
        # 📸 Скриншот без сохранения в файл
        image_bytes = await self.page.screenshot(full_page=True)

        # 🧠 Преобразуем для OpenCV
        screen_np = np.frombuffer(image_bytes, dtype=np.uint8)
        screen = cv2.imdecode(screen_np, cv2.IMREAD_COLOR)

        # 📥 Загружаем шаблон (из файла)
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(BASE_DIR, "screens", "checkbox.png")
        template = cv2.imread(template_path)
        # template = cv2.imread("screens/checkbox.png")

        # 🔍 Поиск
        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val > 0.9:
            logger.debug(f"Найден checkbox! Точность: {max_val}")
            h, w = template.shape[:2]
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            # await self.page.mouse.click(center_x, center_y)
            x, y = self.get_coords_to_click(self.page, center_x, center_y)
            pyautogui.click(x, y)
            # await self.human_click(center_x, center_y)
            # await self.cdp_click(center_x, center_y)
            return True

    @staticmethod
    async def human_like_mouse_move(page, start_x: int, start_y: int, end_x: int, end_y: int, steps: int = 25):
        """Двигает мышь по кривой с шумом"""
        await page.mouse.move(start_x, start_y)
        for i in range(1, steps + 1):
            progress = i / steps
            x_noise = random.uniform(-1, 1)
            y_noise = random.uniform(-1, 1)
            x = start_x + (end_x - start_x) * progress + x_noise
            y = start_y + (end_y - start_y) * progress + y_noise
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.005, 0.02))

    async def human_click(self, x: int, y: int):
        page = self.page
        """Реалистичный человекоподобный клик по координатам (x, y)"""
        # Получим текущую позицию мыши (грубо, начнем с (0,0) если не знаем)
        try:
            # Эвристика — просто двигай мышь в левый верхний угол перед началом
            await page.mouse.move(0, 0)
        except Exception:
            pass

        # Подобие дрожащей руки: движение к цели с флуктуациями
        await self.human_like_mouse_move(page, 0, 0, x, y, steps=random.randint(15, 30))

        # Маленькая задержка перед нажатием (реакция человека)
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # Клик: нажатие, задержка и отпускание
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.05, 0.12))
        await page.mouse.up()

        # После клика мышь может немного дрогнуть
        if random.random() < 0.4:
            await page.mouse.move(x + random.randint(-3, 3), y + random.randint(-3, 3))

    async def route_handler(browser, route):
        blocked_extensions = ['.js', '.css', '.png', '.jpg', '.svg', '.gif', '.woff', '.ttf']

        # print(route, request)
        if any(route.request.url.endswith(ext) for ext in blocked_extensions):
            await route.abort()
        else:
            await route.continue_()

    async def block_rendering(self):
        await self.page.route("**/*", self.route_handler)

    async def unblock_rendering(self):
        await self.page.unroute("**/*", self.route_handler)

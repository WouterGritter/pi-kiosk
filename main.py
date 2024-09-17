import subprocess
import time
import requests
import asyncio
import websockets
import json

from threading import Thread
from typing import Optional
from websockets import WebSocketClientProtocol
from gpiozero import Button


urls = [
    'https://grafana.local.gritter.me/d/edpk6qvizery8f/cameras?kiosk&autofitpanels',
    'https://grafana.local.gritter.me/d/cdno9t1gxk9vkd/rb-solar?refresh=5s&kiosk&autofitpanels',
    'https://grafana.local.gritter.me/d/bdo2oeh94rlz4e/serverroom?refresh=5s&kiosk&autofitpanels',
    'https://grafana.local.gritter.me/d/fdnvp8t2xi4g0b/smart-meters-energy?kiosk&autofitpanels',
    'https://grafana.local.gritter.me/d/cdno60x6ejpxcf/smart-meters-power?kiosk&autofitpanels',
    'https://grafana.local.gritter.me/d/adnvmj8skb7r4f/temperature-sensors-instantaneous?kiosk&autofitpanels',
]
playlist_delay = 60 * 2
button_pin = 17
no_cursor_extension_location = '/home/wouter/kiosk_server/no_cursor_extension'

remote_debugging_port = 9222

ws: Optional[WebSocketClientProtocol] = None
chrome_page_id: Optional[str] = None

current_url = 0
playlist_running = True

button_active_since: Optional[float] = None


async def connect_ws():
    global ws
    ws = await websockets.connect(f'ws://127.0.0.1:{remote_debugging_port}/devtools/page/{chrome_page_id}')


async def _navigate_to_page(url):
    await ws.send(json.dumps({
        'id': 0,
        'method': 'Page.navigate',
        'params': {
            'url': url
        }
    }))


async def navigate_to_page(url):
    print(f'Navigating to {url}')
    try:
        await _navigate_to_page(url)
    except:
        await connect_ws()
        await _navigate_to_page(url)


async def next_page():
    global current_url
    current_url += 1
    if current_url >= len(urls):
        current_url = 0
    url = urls[current_url]
    print(f'Changing url to #{current_url}')
    await navigate_to_page(url)


def start_chromium():
    subprocess.run([
        'chromium-browser',
        '--noerrdialogs',
        '--disable-infobars',
        '--display=:0',
        '--kiosk', urls[current_url],
        f'--remote-debugging-port={remote_debugging_port}',
        f'--load-extension={no_cursor_extension_location}',
    ])


def chromium_thread():
    while True:
        start_chromium()
        print('Re-running chromium-browser after delay...')
        time.sleep(5)


def get_chrome_page_id():
    pages = requests.request('GET', 'http://127.0.0.1:9222/json').json()
    for page in pages:
        if page['type'] == 'page':
            return page['id']


def on_button_press():
    global button_active_since
    button_active_since = time.time()


def on_button_release():
    global button_active_since, playlist_running
    if button_active_since is None:
        return
    active_time = time.time() - button_active_since
    if active_time < 0.01:
        return

    print(f'{active_time=:.2f}')

    if active_time < 1:
        print('Next page, disabling playlist')
        asyncio.run(next_page())
        playlist_running = False
    else:
        print('Enabling playlist')
        playlist_running = True

    button_active_since = None


async def main():
    global chrome_page_id, current_url

    Thread(target=chromium_thread).start()

    while chrome_page_id is None:
        try:
            chrome_page_id = get_chrome_page_id()
        except Exception as ex:
            print(f'Error while fetching page ID, Chromium is not running yet ({ex})')
            await asyncio.sleep(1)

    print(f'{chrome_page_id=}')

    button = Button(button_pin)
    button.when_activated = on_button_press
    button.when_deactivated = on_button_release

    while True:
        if not playlist_running:
            await asyncio.sleep(1)
            continue

        await asyncio.sleep(playlist_delay)

        await next_page()


if __name__ == '__main__':
    asyncio.run(main())

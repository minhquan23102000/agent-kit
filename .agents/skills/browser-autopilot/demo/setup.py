# Shared setup for both demo takes: open the shop in a tab named "shop" at the size record.py
# composes (960x1080, the left half of a 1920x1080 video; the terminal is the right half).
# In the Python eval kernel:  exec(read("setup.py")); tab = await open_shop()
# `browser` is the eval kernel's global.
SHOP_URL = "http://127.0.0.1:8765/shop.html"

async def open_shop():
    # persist: an idle tab is frozen at turn settle and reloaded on next use; keep it live instead.
    # deviceScaleFactor 1: the same size record.py sets when it records this page, so the agent's
    # page and the recording never disagree about the layout.
    tab = await browser.open(name="shop", url=SHOP_URL, persist=True,  # noqa: F821
                             viewport={"width": 960, "height": 1080, "deviceScaleFactor": 1})
    print("shop tab ready:", await tab.title())
    return tab

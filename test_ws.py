import asyncio
import websockets

async def test():
    try:
        async with websockets.connect(
            "ws://192.168.4.1:81", 
            ping_interval=None, 
            compression=None,
            open_timeout=15
        ) as ws:
            print("SUCCESS! Handshake complete.")
            await asyncio.sleep(2)
    except Exception as e:
        print(f"FAILED: {e}")

asyncio.run(test())

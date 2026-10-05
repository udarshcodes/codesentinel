import asyncio

async def my_generator():
    print("Generator start")
    yield 1
    print("Generator sleeping")
    try:
        await asyncio.sleep(10)
    except asyncio.CancelledError:
        print("Generator cancelled internally!")
        raise
    yield 2

async def main():
    gen = my_generator()
    
    print("First next:")
    v = await anext(gen)
    print("Got", v)
    
    print("Second next with timeout:")
    try:
        await asyncio.wait_for(anext(gen), timeout=1.0)
    except asyncio.TimeoutError:
        print("Timeout!")
        
    print("Third next:")
    try:
        v = await anext(gen)
        print("Got", v)
    except StopAsyncIteration:
        print("StopAsyncIteration!")
    except Exception as e:
        print("Exception:", type(e), e)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio

import run


class MockWriter:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data += [data]

    async def drain(self):
        pass

def test_relay_to_client():
    async def test_write(reader):
        reader.feed_data(b"foo\r\n\r\n")
        reader.feed_data(b"bar")
        reader.feed_eof()

    async def _relay(loop):
        reader = asyncio.StreamReader(loop=loop)
        writer = MockWriter()

        await asyncio.wait([
            loop.create_task(run.relay_to_client(reader, writer)),
            loop.create_task(test_write(reader)),
        ])

        assert writer.data == [b"foo\r\n", b"\r\n", b"bar"]

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_relay(loop))
    # loop.close()


def test_relay_to_remote():
    async def test_write(reader):
        reader.feed_data(b"foo")
        reader.feed_data(b"bar")
        reader.feed_eof()

    async def _relay(loop):
        reader = asyncio.StreamReader(loop=loop)
        writer = MockWriter()

        await asyncio.wait([
            loop.create_task(run.relay_to_remote(reader, writer)),
            loop.create_task(test_write(reader)),
        ])

        assert writer.data == [b"foobar"]  # Not 2 because of only one write().

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_relay(loop))
    # loop.close()

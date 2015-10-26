import asyncio

import proxy


class MockWriter:
    def __init__(self):
        self.data = []

    def write(self, data):
        self.data += [data]

    async def drain(self):
        pass


def test_relay_to_client():
    async def test_write(reader):
        reader.feed_data(b"HTTP/1.1 200 OK\r\n")
        reader.feed_data(b"Bar: baz")
        reader.feed_eof()

    async def _relay(loop):
        remote = asyncio.StreamReader(loop=loop)
        client = MockWriter()

        await asyncio.wait([
            loop.create_task(proxy.relay_to_client(
                remote, client, proxy.Stats())),
            loop.create_task(test_write(remote)),
        ])

        assert client.data == [b"HTTP/1.1 200 OK\r\n", b"Bar: baz", b"\r\n"]

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
            loop.create_task(proxy.relay_to_remote(reader, writer)),
            loop.create_task(test_write(reader)),
        ])

        assert writer.data == [b"foobar"]  # Not 2 because of only one write().

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_relay(loop))
    # loop.close()

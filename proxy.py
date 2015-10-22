#!/usr/bin/env python

import asyncio
import functools
import json
import time
import urllib.parse
import werkzeug


async def relay_to_client(reader, writer, stats, bytes_ranges=None):
    # Relay headers.
    while True:
        try:
            line = await asyncio.wait_for(reader.readline(), 0.5)
        except asyncio.TimeoutError:
            break

        if not line or line == b"\r\n":
            break

        writer.write(line)
        await writer.drain()

    writer.write(b"\r\n")

    if bytes_ranges is None:
        bytes_ranges = [(0, None)]
    else:
        bytes_ranges = list(bytes_ranges.ranges)

    # TODO: Ranging machinery only if "Content-Range" not in incoming reponse
    #       headers.
    # TODO: bytes=-N ranges - buffer N last bytes and send.
    b_start = 0  # Incoming data pointer [bytes].
    current_range = bytes_ranges.pop(0)
    i = 0
    while True:
        if current_range is None:
            break

        try:
            buf = await asyncio.wait_for(reader.read(1024), 0.5)
        except asyncio.TimeoutError:
            break

        if len(buf) == 0:
            break

        b_end = b_start + len(buf)  # b_end - like in slice notation.

        while True:
            if current_range is None:
                break

            i += 1

            range_ended = False  # Whether got to the end of the range.
            buffer_ended = False  # Whether got to the end of the buffer.
            # All comments should also include "or is at the beginning/end of the
            # buffer" - hence ">=" and "<=" operators, not ">" and "<".
            if b_start <= current_range[0] and b_end >= current_range[0] and \
                    current_range[1] is None:
                # Range's start is within the buffer and range's end is None.
                data = buf[current_range[0] - b_start:]
                buffer_ended = True
            elif b_start >= current_range[0] and current_range[1] is None:
                data = buf
                buffer_ended = True
                # Range's start is before the buffer and range's end is None.
            elif b_start <= current_range[0] and b_end >= current_range[0] and \
                    b_end <= current_range[1]:
                # Range's start is within buffer and range's end is beyond the
                # buffer.
                data = buf[current_range[0] - b_start:]
                buffer_ended = True
            elif b_start <= current_range[0] and b_end >= current_range[1]:
                # Whole range is within the buffer.
                data = buf[current_range[0] - b_start:current_range[1] - b_start]
                range_ended = True
            elif b_start >= current_range[0] and b_start <= current_range[1] and \
                    b_end >= current_range[1]:
                # Range's start is before the buffer and range's end is within the
                # buffer
                data = buf[:current_range[1] - b_start]
                range_ended = True
            elif b_start >= current_range[0] and b_end <= current_range[1]:
                # Buffer is within the range.
                data = buf
                buffer_ended = True
            else:
                b_start = b_end
                break

            stats.total_bytes_transferred += len(data)
            writer.write(data)
            await writer.drain()

            if range_ended:
                if bytes_ranges:
                    current_range = bytes_ranges.pop(0)
                else:
                    current_range = None

            if buffer_ended:
                b_start = b_end
                break

        b_start = b_end
        i += 1


async def relay_to_remote(reader, writer):
    while True:
        try:
            buf = await asyncio.wait_for(reader.read(1024), 0.5)
        except asyncio.TimeoutError:
            break

        if len(buf) == 0:
            break

        writer.write(buf)
        await writer.drain()


async def on_connected(client_reader, client_writer, listen_on, stats):
    address = client_writer.get_extra_info("peername")

    headers = ""
    host = None
    port = 80
    bytes_ranges = None

    line = await client_reader.readline()

    if not line:
        client_writer.close()
        return

    # For GET /stats.
    line = line.decode()
    data = line.split()
    if data[0].lower() == "get" \
            and urllib.parse.urlparse(data[1]).path == "/stats":
        data = json.dumps(stats.dictionary).encode()
        client_writer.write(b"HTTP/1.1 200 OK\r\n")
        client_writer.write(b"Content-Length: %d\r\n" % len(data))
        client_writer.write(b"Content-Type: application/json\r\n\r\n")
        client_writer.write(data)
        client_writer.write(b"\r\n")
        client_writer.close()
        return

    headers += line

    while True:
        line = await client_reader.readline()

        if not line or line == b"\r\n":
            break

        line = line.decode()

        key, value = line.split(":", maxsplit=1)
        key = key.lower().strip()
        value = value.strip()

        if key == "host":
            if ":" in value:
                host, port = value.split(":")
                port = int(port)
            else:
                host = value
        elif key == "range":
            bytes_ranges = werkzeug.http.parse_range_header(value)
        headers += line

    if not host or listen_on == (host, port) \
            or host in ("127.0.0.1", "localhost") and port == listen_on[1]:
        # Close connections without (or with circular) Host header right away.
        client_writer.close()
        print("Invalid")
        return

    try:
        remote_reader, remote_writer = await asyncio.open_connection(
            host=host,
            port=port,
            loop=loop,
        )
    except OSError as e:
        client_writer.close()
        return

    headers += "\r\n"
    remote_writer.write(headers.encode())
    await remote_writer.drain()

    # Relay bodies.
    await asyncio.wait([
            loop.create_task(relay_to_client(remote_reader,
                                             client_writer,
                                             stats,
                                             bytes_ranges)),
            loop.create_task(relay_to_remote(client_reader,
                                             remote_writer)),
        ],
        loop=loop)

    await client_writer.drain()
    client_writer.close()
    remote_writer.close()


class Stats:
    def __init__(self):
        self.total_bytes_transferred = 0
        self.start_time = time.time()

    @property
    def dictionary(self):
        uptime = time.time() - self.start_time
        days, remainder = divmod(uptime, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours, minutes, seconds

        return {
            "total_bytes_transferred": self.total_bytes_transferred,
            "uptime": {
                "days": int(days),
                "hours": int(hours),
                "minutes": int(minutes),
                "seconds": int(seconds),
            }
        }


if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    host = "127.0.0.1"
    port = 8001

    stats = Stats()
    on_connected = functools.partial(on_connected,
                                     listen_on=(host, port),
                                     stats=stats,
                                     )

    server = loop.run_until_complete(asyncio.start_server(
        on_connected,
        host,
        port,
        loop=loop,
    ))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()

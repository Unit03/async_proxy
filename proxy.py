import asyncio
import functools
import json
import os
import time
import urllib.parse
import werkzeug


# Names of environment variables for configuration.
PROXY_HOST_ENV = "PROXY_HOST"
PROXY_PORT_ENV = "PROXY_PORT"

# Size of read buffers [bytes].
READ_BUFFER_SIZE = 1024

# Read timeout time [s].
READ_TIMEOUT = 0.5


async def _relay_ranged_body_to_client(remote, client, stats, bytes_ranges):
    """Relay response body with handling ranges of bytes.

    :param asyncio.StreamReader remote: remote server's reader stream
    :param asyncio.StreamWriter client: proxy's client writer stream
    :param Stats stats: stats object
    :param werkzeug.datastructures.Ranges bytes_ranges: optional ranges
                                                        specification

    """

    b_start = 0  # Incoming data "pointer" (along whole response body) [bytes].
    bytes_ranges = list(bytes_ranges.ranges)  # Get ranges list.
    current_range = bytes_ranges.pop(0)  # Get first range specified by client.
    last_bytes_buffer = b""  # May be needed for "last N bytes" range.
    while True:
        # If run out of ranges.
        if current_range is None:
            break

        # Try to read from remote server with timeout.
        # Would need changes for Keep-Alive handling.
        try:
            buf = await asyncio.wait_for(remote.read(READ_BUFFER_SIZE),
                                         READ_TIMEOUT)
        except asyncio.TimeoutError:
            break

        # Empty buffer read - no more data.
        if len(buf) == 0:
            # If last range is "last N bytes", send that buffer to the client.
            if current_range[0] < 0:
                # Update stats.
                stats.total_bytes_transferred += len(last_bytes_buffer)

                # Send data to the client, wait for the writer to flush.
                client.write(last_bytes_buffer)
                await client.drain()

            break

        # "Pointer" for a place in whole response body just after this buffer.
        b_end = b_start + len(buf)

        if current_range[0] < 0:
            # "last N bytes" range needs content buffering.
            if - current_range[0] > len(buf):
                last_bytes_buffer = (
                    last_bytes_buffer[current_range[0] + len(buf):] + buf)
            else:
                last_bytes_buffer = buf[current_range[0]:]
        else:
            while True:
                # If run out of ranges (second clause - that's not an error).
                if current_range is None:
                    break

                range_ended = False  # Whether got to the end of the range.
                buffer_ended = False  # Whether got to the end of the buffer.

                # All comments should also include "or is at the beginning/end
                # of# the buffer" - hence ">=" and "<=" operators, not ">" and
                # "<".
                if b_start <= current_range[0] and b_end >= current_range[0] \
                        and current_range[1] is None:
                    # Range's start is within the buffer and range's end is
                    # None.
                    data = buf[current_range[0] - b_start:]
                    buffer_ended = True
                elif b_start >= current_range[0] and current_range[1] is None:
                    data = buf
                    buffer_ended = True
                    # Range's start is before the buffer and range's end is
                    # None.
                elif b_start <= current_range[0] and b_end >= current_range[0] \
                        and b_end <= current_range[1]:
                    # Range's start is within buffer and range's end is beyond
                    # the buffer.
                    data = buf[current_range[0] - b_start:]
                    buffer_ended = True
                elif b_start <= current_range[0] and b_end >= current_range[1]:
                    # Whole range is within the buffer.
                    data = buf[current_range[0] - b_start
                               :current_range[1] - b_start]
                    range_ended = True
                elif b_start >= current_range[0] \
                        and b_start <= current_range[1] \
                        and b_end >= current_range[1]:
                    # Range's start is before the buffer and range's end is
                    # within the buffer
                    data = buf[:current_range[1] - b_start]
                    range_ended = True
                elif b_start >= current_range[0] and b_end <= current_range[1]:
                    # Buffer is within the range.
                    data = buf
                    buffer_ended = True
                else:
                    # Buffer does not overlap current range.
                    b_start = b_end
                    break

                # Update stats.
                stats.total_bytes_transferred += len(data)

                # Send data to the client, wait for the writer to flush.
                client.write(data)
                await client.drain()

                # Whether we got to the end of current range.
                if range_ended:
                    # If any ranges left, pop the next one.
                    if bytes_ranges:
                        current_range = bytes_ranges.pop(0)
                    else:
                        current_range = None

                # Whether we got to the end of current buffer.
                if buffer_ended:
                    b_start = b_end
                    break

    b_start = b_end


async def _relay_body_to_client(remote, client, stats):
    """Relay response body without handling ranges.

    :param asyncio.StreamReader remote: remote server's reader stream
    :param asyncio.StreamWriter client: proxy's client writer stream
    :param Stats stats: stats object

    """

    while True:
        # Try to read from remote with timeout.
        # Would need changes for Keep-Alive handling.
        try:
            data = await asyncio.wait_for(remote.read(READ_BUFFER_SIZE),
                                          READ_TIMEOUT)
        except asyncio.TimeoutError:
            break

        # Empty buffer read - no more data.
        if len(data) == 0:
            break

        # Update stats.
        stats.total_bytes_transferred += len(data)

        # Send data to the client, wait for the writer to flush.
        client.write(data)
        await client.drain()


async def relay_to_client(remote, client, stats, bytes_ranges=None):
    """Relay response from remote server to client.

    Relay response headers, checking whether remote server handled ranges for
    us, then relay body of the response accordingly.

    :param asyncio.StreamReader remote: remote server's reader stream
    :param asyncio.StreamWriter client: proxy's client writer stream
    :param Stats stats: stats object
    :param werkzeug.datastructures.Ranges bytes_ranges: optional ranges
                                                        specification

    """

    line = await remote.readline()
    http_version, status_code, *description = line.decode().split()

    # Checking, if we got 206 Partial Content.
    if int(status_code) == 206:
        # Remote server handled Range header for us.
        bytes_ranges = None

    # If client requested range(s), rewrite status code.
    if bytes_ranges:
        line = "{} 206 Partial Content".format(http_version).encode()

    # Update stats.
    stats.total_bytes_transferred += len(line)

    # Send data to the client, wait for the writer to flush.
    client.write(line)
    await client.drain()

    # Relay headers.
    while True:
        try:
            line = await asyncio.wait_for(remote.readline(), READ_TIMEOUT)
        except asyncio.TimeoutError:
            break

        # When no proper line - either end of headers or premature end of the
        # response.
        if not line or line == b"\r\n":
            break

        # Basic headers parsing.
        data = line.decode()
        key, value = data.split(":", maxsplit=1)
        key = key.lower().strip()

        # Update stats.
        stats.total_bytes_transferred += len(data)

        # Send data to the client, wait for the writer to flush.
        client.write(line)
        await client.drain()

    # Update stats, ut CRLF after the headers.
    stats.total_bytes_transferred += len(b"\r\n")
    client.write(b"\r\n")

    # Relay body of the response, with or without ranges handling.
    if bytes_ranges is not None:
        await _relay_ranged_body_to_client(remote, client, stats, bytes_ranges)
    else:
        await _relay_body_to_client(remote, client, stats)


async def relay_to_remote(client, remote):
    """Relay request body from client to remote server.

    :param asyncio.StreamReader remote: remote server's reader stream
    :param asyncio.StreamWriter client: proxy's client writer stream

    """

    while True:
        # Try to read from client with timeout.
        try:
            buf = await asyncio.wait_for(client.read(READ_BUFFER_SIZE),
                                         READ_TIMEOUT)
        except asyncio.TimeoutError:
            break

        # Empty buffer read - no more data.
        if len(buf) == 0:
            break

        # Send data to the remote server, wait for the writer to flush.
        remote.write(buf)
        await remote.drain()


async def on_connected(client_reader, client_writer, listen_on, stats):
    # Try to read first line of the HTTP request.
    line = await client_reader.readline()

    # If request prematurely ended.
    if not line:
        client_writer.close()
        return

    # For GET /stats. Since it's the only endpoint, basic parsing should
    # suffice (instead of more sophisticated routing).
    line = line.decode()
    data = line.split()
    url = urllib.parse.urlparse(data[1])
    # If GET /stats, return JSON-ed stats dict, wait for writer to flush
    # and close the connection.
    if data[0].lower() == "get" and url.path == "/stats":
        # Get statistics from stats object, serialize it to JSON, encode to
        # bytes, send as minimal HTTP response and close the stream.
        data = json.dumps(stats.dictionary).encode()
        client_writer.write(b"HTTP/1.1 200 OK\r\n")
        client_writer.write(b"Content-Length: %d\r\n" % len(data))
        client_writer.write(b"Content-Type: application/json\r\n\r\n")
        client_writer.write(data)
        client_writer.write(b"\r\n")
        await client_writer.drain()
        client_writer.close()
        return

    # Parse the query part for range handling.
    query = urllib.parse.parse_qs(url.query)
    query_ranges = None
    # If "range" param in query, parse the value to Ranges object.
    if "range" in query:
        query_ranges = werkzeug.http.parse_range_header(query["range"][0])

    # Relay request headers, checking for Host and Range header.
    headers = line
    host = None
    port = 80
    bytes_ranges = None
    while True:
        line = await client_reader.readline()

        # If line's empty or only CRLF - headers (or whole request) ended.
        if not line or line == b"\r\n":
            break

        line = line.decode()

        # Most basic parsing of headers.
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

    if query_ranges and bytes_ranges:
        # If ranges specified both in query and headers and they don't match.
        # Note that werkzeug.datastructures.Ranges stores ranges a bit
        # differently than they are defined in header/query!
        # In header/query - the last byte of each range is passed
        # werkzeug stores that as first byte *after* the end of the range.
        # Thus both are werkzeug.datastructures.Ranges objects.
        if query_ranges.ranges != bytes_ranges.ranges:
            client_writer.write(
                b"HTTP/1.1 416 Requested Range Not Satisfiable\r\n")
            await client_writer.drain()
            client_writer.close()
            return
    elif query_ranges:
        # If ranges specified only in query.
        bytes_ranges = query_ranges

    if not host or listen_on == (host, port) \
            or host in ("127.0.0.1", "localhost") and port == listen_on[1]:
        # Close connections without (or with recursive) Host header right away.
        client_writer.close()
        return

    try:
        # Open connection to remote server.
        remote_reader, remote_writer = await asyncio.open_connection(
            host=host,
            port=port,
            loop=loop,
        )
    except OSError as e:
        # That spans ConnectionRefusedError, too.
        client_writer.close()
        return

    # Relay request headers to remote server.
    headers += "\r\n"
    remote_writer.write(headers.encode())
    await remote_writer.drain()

    # Relay bodies of both request and response.
    await asyncio.wait(
        [loop.create_task(relay_to_client(remote_reader,
                                          client_writer,
                                          stats,
                                          bytes_ranges)),
         loop.create_task(relay_to_remote(client_reader,
                                          remote_writer)),
         ],
        loop=loop)

    # Wait for client's stream to flush, then close both connections.
    await client_writer.drain()
    client_writer.close()
    remote_writer.close()


class Stats:
    def __init__(self):
        self.total_bytes_transferred = 0
        self.start_time = time.time()

    @property
    def dictionary(self):
        "Statistics as dictionary with structured uptime."

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

    host = "0.0.0.0"
    port = 8000

    # Get hostname and port from environment variables, if available.
    if PROXY_HOST_ENV in os.environ and os.environ[PROXY_HOST_ENV]:
        host = os.environ[PROXY_HOST_ENV]

    if PROXY_PORT_ENV in os.environ and os.environ[PROXY_PORT_ENV]:
        port = int(os.environ[PROXY_PORT_ENV])

    stats = Stats()
    # "Initialize" callback with listen-on info and statistics object.
    on_connected = functools.partial(on_connected,
                                     listen_on=(host, port),
                                     stats=stats,
                                     )

    # Run the server.
    server = loop.run_until_complete(asyncio.start_server(
        on_connected,
        host,
        port,
        loop=loop,
    ))

    # Stop the server by ^C.
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    # Cleanup.
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()

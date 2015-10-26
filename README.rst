HTTP proxy
==========

Based on Python 3.5 and ``asyncio``.

Install and run using Docker Compose::

   docker-compose up

or Python + ``pip`` alone::

   pip install -e .
   python proxy.py


Configuration
-------------

You can use environment variables to configure the proxy::

   export PROXY_HOST=host
   export PROXY_PORT=8888

HTTP proxy
==========

Based on Python 3.5 and ``asyncio``.

Install and run using Docker Compose:

.. code-block:: console

   $ docker-compose up

or Python + ``pip`` alone:

.. code-block:: console

   $ pip install -e .
   $ python proxy.py


Configuration
-------------

You can use environment variables to configure the proxy:

.. code-block:: console

   $ export PROXY_HOST=host
   $ export PROXY_PORT=8888

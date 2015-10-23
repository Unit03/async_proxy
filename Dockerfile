FROM python:3.5

RUN mkdir -p /var/proxy
COPY proxy.py setup.py /var/proxy/

WORKDIR /var/proxy

RUN pip install -e .

ENV PROXY_HOST 0.0.0.0
ENV PROXY_PORT 8000

CMD ["python", "proxy.py"]

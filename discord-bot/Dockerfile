FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
RUN uv pip install --system -e .

COPY *.py ./

RUN useradd -m -u 1000 discordbot && chown -R discordbot:discordbot /app
USER discordbot

EXPOSE 8080
CMD ["python", "app.py"]

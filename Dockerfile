FROM python:3.13-slim

WORKDIR /app

COPY . .

RUN pip install flask werkzeug

EXPOSE 5000

CMD ["python", "app.py"]
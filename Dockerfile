FROM python:3.11-slim

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY . .

EXPOSE 3000

CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120 app:app

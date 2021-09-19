FROM python:3.9.7-slim-buster
COPY . ./megalohobot
RUN pip install -r requirements.txt
CMD ["python", "./megalohobot/app.py"]

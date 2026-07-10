FROM gcr.io/google.com/cloudsdktool/google-cloud-cli:slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless google-cloud-cli-firestore-emulator \
    && rm -rf /var/lib/apt/lists/*

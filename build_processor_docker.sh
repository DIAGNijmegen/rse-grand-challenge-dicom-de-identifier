#!/usr/bin/env bash
docker build -f processor/Dockerfile --tag=your-username/your-project-name:processor --build-arg GIT_COMMIT_ID=$(git rev-parse --abbrev-ref HEAD | sed "s/[^[a-zA-Z0-9]]//") .

#!/bin/bash

echo "Starting Nginx with Streamlit proxy..."
echo "current directory: $(pwd)"

# Check if the SSL and conf.d directory exists, if not terminate
if [ ! -d "ssl" ]; then
  echo "SSL directory not found. Please create the ssl directory and add your certificates."
  exit 1
fi
if [ ! -d "conf.d" ]; then
  echo "conf.d directory not found. Please create the conf.d directory and add your Nginx configuration files."
  exit 1
fi


docker run -d \
  --name ai-contract-interview-proxy \
  -p 8143:8143 \
  -v $(pwd)/conf.d:/etc/nginx/conf.d \
  -v $(pwd)/ssl:/etc/nginx/ssl \
  --add-host=host.docker.internal:host-gateway \
  nginx
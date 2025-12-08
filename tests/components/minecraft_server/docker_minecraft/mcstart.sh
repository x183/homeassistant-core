docker compose up -d

# replace "happy" with your container name
# docker network connect docker-minecraft_mcnet $(docker ps --filter "name=happy" -q)
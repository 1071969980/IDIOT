from redis.asyncio import Redis

CLIENT = Redis(host="redis", port=6379)
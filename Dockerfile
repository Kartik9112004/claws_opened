# Use the official oven/bun image as the base
FROM oven/bun:1.2.5-alpine AS base
WORKDIR /app

# Install git since it is often needed for git-based dependencies or operations
RUN apk add --no-cache git

# Copy package configuration files
COPY package.json bun.lock ./

# Install dependencies (frozen-lockfile ensures exact versions)
RUN bun install --frozen-lockfile

# Copy the rest of the application files
COPY . .

# Run type check to make sure the app compiles successfully
RUN bun run type-check

# Set production environment defaults
ENV NODE_ENV=production

# The bot doesn't listen on a port by default because it uses polling,
# but we document this in case webhooks are configured.
# EXPOSE 3000

# Default command runs the Telegram bot
CMD ["bun", "run", "index.ts", "telegram"]

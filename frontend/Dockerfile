# NOTE: This Dockerfile produces a static build served by `serve`.
# In production, API calls to /api/* require an nginx reverse proxy
# (see docker-compose.yml + nginx.conf) to route them to the backend.
# This Dockerfile is NOT intended for standalone use without a reverse proxy.

FROM node:18-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .
RUN npm run build

# Production stage — serve with lightweight static server
FROM node:18-alpine

WORKDIR /app

RUN npm install -g serve

COPY --from=build /app/dist ./dist

EXPOSE 5173

CMD ["serve", "-s", "dist", "-l", "5173"]

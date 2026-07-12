FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json /app/
COPY web/package.json /app/web/package.json
COPY shared/package.json /app/shared/package.json

RUN npm ci

FROM node:20-alpine AS builder

WORKDIR /app

ENV NODE_ENV=production

COPY --from=deps /app/node_modules /app/node_modules
COPY . /app

RUN npm --workspace web run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

COPY --from=builder /app /app

EXPOSE 3000

CMD ["npm", "--workspace", "web", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]

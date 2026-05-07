FROM node:20-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json /app/
COPY apps/web/package.json /app/apps/web/package.json
COPY packages/shared/package.json /app/packages/shared/package.json

RUN npm ci

FROM node:20-alpine AS builder

WORKDIR /app

ENV NODE_ENV=production

COPY --from=deps /app/node_modules /app/node_modules
COPY . /app

RUN npm --workspace apps/web run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

COPY --from=builder /app /app

EXPOSE 3000

CMD ["npm", "--workspace", "apps/web", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]

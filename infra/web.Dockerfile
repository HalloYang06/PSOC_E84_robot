FROM node:20-alpine

WORKDIR /app

COPY apps/web/package.json /app/package.json
RUN npm install

COPY apps/web /app

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0", "-p", "3000"]

